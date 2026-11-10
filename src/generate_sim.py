"""Generate the SIMULATED marketing dataset used in this case study (seed 42).

Nothing in this file is Hostinger data. Public facts (prices, 30-day refund window,
40% affiliate commission, 30-day cookie) come from hostinger.com and are listed in
data/SOURCES.md. Every other number is an assumption, listed in data/ASSUMPTIONS.md.

How the simulation works, in plain words:
1. Prospects arrive every day through an "origin" (what really brought them):
   paid non-brand search, SEO, an influencer video, a content affiliate, word of mouth, ...
2. Each prospect then makes a few more visits (touchpoints) through other channels
   before buying or leaving: brand search, direct, coupon sites, e-mail, ...
3. Some prospects buy (orders). Their plan, refund and renewal depend on their origin.
4. Spend is built from the same events (clicks x CPC, video fees, affiliate commissions).

Deliberate mechanisms (so the analysis has something real to find):
- Influencer videos drive later brand searches; most viewers never click the tracked link.
- Codes of 3 creators leak to coupon sites from a given date.
- Coupon-site visits happen mostly right before checkout (buyer already decided),
  and coupon buyers refund more and renew less.
- Brand ads are weakly incremental: when they are switched off (geo test) most brand
  searchers click the organic result instead.
- SEO brings long plans that renew well. Paid channels show diminishing returns.
- One day of duplicated tracking events, one day of missing PPC cost, ~2% of orders with
  no touchpoint (consent declined).

Usage:  python src/generate_sim.py
Output: data/clean/*.parquet (+ .csv for every table except touchpoints)
"""
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
OUT = Path(__file__).resolve().parents[1] / "data" / "clean"
OUT.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------ calendar
START = pd.Timestamp("2024-05-01")
END = pd.Timestamp("2026-10-31 23:59:59")          # observation date: end of data
DAYS = pd.date_range(START, "2026-10-31", freq="D", unit="ns")   # nanoseconds everywhere
ND = len(DAYS)
DAY_NS = 86_400 * 10**9
MONTH_DAYS = 30.4375                                # average month length, in days
END_NS = END.value

month = DAYS.month.values
season = np.ones(ND)                                # light seasonality (assumption)
season[month == 1] = 1.25                           # new-year projects
season[month == 9] = 1.15                           # back to school / work
season[(month == 7) | (month == 8)] = 0.90          # summer
season[month == 12] = 0.85
season[(month == 11) & (DAYS.day.values >= 20)] = 1.35   # Black Friday weeks
month_idx = (DAYS.year.values - 2024) * 12 + month - 5   # 0..29

# ------------------------------------------------------------------ countries
COUNTRIES = np.array(["US", "FR", "ES", "BR", "IN", "ID"])
C_WEIGHT = np.array([.30, .13, .09, .15, .18, .15])   # share of demand (assumption)
C_PRICE = np.array([1.0, 1.0, 1.0, .60, .50, .50])    # regional price index (assumption)
C_CPC = np.array([1.10, .90, .80, .35, .25, .25])      # brand CPC in EUR (assumption)
NC = len(COUNTRIES)

# Geo test: brand ads switched off in 3 countries for 12 weeks
TEST_COUNTRIES = np.array([0, 2, 5])                  # US, ES, ID (54% of demand) vs FR, BR, IN
TEST_START = pd.Timestamp("2026-03-02").value
TEST_END = pd.Timestamp("2026-05-24 23:59:59").value

# ------------------------------------------------------------------ channels
CHANNELS = ["PPC Brand", "PPC Non-brand", "SEO", "Affiliates - Content",
            "Affiliates - Coupon", "Influencers", "Email", "Direct"]
PPC_BRAND, PPC_NB, SEO, AFF_CONTENT, AFF_COUPON, INFLU, EMAIL, DIRECT = range(8)
BRAND_SEARCH = 8      # temporary code: "searched the brand", resolved later to ad or organic

ORIGINS = ["ppc_nb", "seo", "inf_click", "inf_hidden", "aff_content", "word_of_mouth", "direct", "coupon"]

# ================================================================== 1. creators & affiliates
N_CR = 40
cr_platform = rng.choice(["YouTube", "TikTok", "Instagram"], N_CR, p=[.60, .25, .15])
cr_niche = rng.choice(["web development", "small business", "freelancing", "tech reviews", "design"], N_CR)
cr_audience = np.round(np.exp(rng.normal(np.log(150_000), 0.9, N_CR)), -3).clip(20_000, 2_500_000)
cr_country = rng.choice(NC, N_CR, p=C_WEIGHT)
cr_fee_model = rng.choice(["flat", "CPA", "hybrid"], N_CR, p=[.60, .20, .20])
plat_reach = {"YouTube": 1.0, "TikTok": 0.6, "Instagram": 0.5}
plat_cost = {"YouTube": 1.0, "TikTok": 0.7, "Instagram": 0.8}
cr_reach = np.array([plat_reach[p] for p in cr_platform])
# flat fee per video grows ~linearly with audience; prospects grow slower (audience^0.8)
# -> bigger creators cost more per prospect = diminishing returns (assumption)
cr_flat_fee = np.round(0.03 * cr_audience * np.array([plat_cost[p] for p in cr_platform])
                       * np.sqrt(C_PRICE[cr_country]) * rng.lognormal(0, .25, N_CR), -1)
cr_flat_fee = np.where(cr_fee_model == "CPA", 0, np.where(cr_fee_model == "hybrid", 0.4 * cr_flat_fee, cr_flat_fee))
cr_cpa_fee = np.where(cr_fee_model == "CPA", 25.0, np.where(cr_fee_model == "hybrid", 12.0, 0.0))
cr_quality = rng.lognormal(0, .35, N_CR)             # how well the audience responds
cr_code = np.array([f"CR{i+1:02d}" for i in range(N_CR)])

# videos: each creator publishes 2 to 9 sponsored videos at random dates.
# No sponsored video from 8 weeks before to the end of the geo test (clean baseline and test read).
test_days = (DAYS.values >= np.datetime64(pd.Timestamp(TEST_START) - pd.Timedelta(weeks=8))) & (DAYS.values <= np.datetime64(pd.Timestamp(TEST_END)))
allowed_days = np.nonzero(~test_days[:ND - 10])[0]
videos = []
for c in range(N_CR):
    for d in np.sort(rng.choice(allowed_days, rng.integers(2, 10), replace=False)):
        videos.append((len(videos), c, d))
videos = np.array(videos)                            # columns: video_id, creator, day index

# 3 big YouTube creators see their code leak to coupon sites from a given date
big_yt = [c for c in np.argsort(-cr_audience) if cr_platform[c] == "YouTube"][:3]
LEAKS = {big_yt[0]: pd.Timestamp("2025-06-15").value,
         big_yt[1]: pd.Timestamp("2025-11-24").value,
         big_yt[2]: pd.Timestamp("2026-04-01").value}

# affiliates: 15 content sites, 7 review sites, 8 coupon sites
aff_type = np.array(["content"] * 15 + ["review"] * 7 + ["coupon"] * 8)
N_AFF = len(aff_type)
aff_size = rng.lognormal(0, .8, N_AFF)
aff_country = rng.choice(NC, N_AFF, p=C_WEIGHT)
aff_rate = rng.choice([.40, .45, .50], N_AFF, p=[.7, .2, .1])   # "starts at 40% and grows with volume"
aff_code = np.array([f"AF{j+1:02d}" for j in range(N_AFF)])
content_ids = np.where(aff_type != "coupon")[0]
coupon_ids = np.where(aff_type == "coupon")[0]

# ================================================================== 2. prospects by origin
frames = []

def add_users(day_country_counts, origin, creator=None, affiliate=None, video=None):
    """Turn a (day x country) matrix of counts into one row per prospect."""
    d_idx, c_idx = np.nonzero(day_country_counts)
    reps = day_country_counts[d_idx, c_idx]
    d = np.repeat(d_idx, reps)
    c = np.repeat(c_idx, reps)
    n = len(d)
    frames.append(pd.DataFrame({
        "origin": origin, "day": d, "country": c,
        "creator": -1 if creator is None else creator,
        "affiliate": -1 if affiliate is None else affiliate,
        "video": -1 if video is None else video}))

country_share = np.broadcast_to(C_WEIGHT, (ND, NC))

# 2a. PPC non-brand: budget changes month to month (same plan for every country, +/-15% by country);
#     prospects = k * spend^0.65 (saturation). Budgets are frozen during the geo test.
nb_month_factor = rng.uniform(.55, 1.5, size=(30, 1)) * rng.uniform(.85, 1.15, size=(30, NC))
nb_month_factor[20:25] = 1.0                          # Jan-May 2026: frozen for the geo test baseline and test
nb_spend = (2_600 * C_WEIGHT[None, :] * nb_month_factor[month_idx] * np.sqrt(season)[:, None]
            * rng.lognormal(0, .08, size=(ND, NC)))
nb_users = rng.poisson(1.9 * nb_spend ** 0.65 * np.sqrt(season)[:, None])
add_users(nb_users, "ppc_nb")

# 2b. SEO: grows slowly over two years (more content indexed)
seo_trend = np.linspace(.85, 1.20, ND)
add_users(rng.poisson(330 * country_share * (season * seo_trend)[:, None]), "seo")

# 2c. word of mouth (first touch is a brand search) and direct type-ins
add_users(rng.poisson(75 * country_share * season[:, None]), "word_of_mouth")
add_users(rng.poisson(65 * country_share * season[:, None]), "direct")
# 2d. people who start on a coupon site
add_users(rng.poisson(14 * country_share * season[:, None]), "coupon")

# 2e. content and review affiliates: steady organic traffic to their articles
for a in content_ids:
    share = np.full(NC, .2 / (NC - 1)); share[aff_country[a]] = .8
    lam = 3.5 * aff_size[a] * share[None, :] * season[:, None]
    add_users(rng.poisson(lam), "aff_content", affiliate=a)

# 2f. influencer videos: viewers become prospects over the following days.
#     35% click the tracked link; the others come back later through brand search,
#     direct or a coupon site -> click-based attribution cannot see the video.
for vid, c, d in videos:
    n = rng.poisson(0.07 * cr_audience[c] ** 0.8 * cr_reach[c] * cr_quality[c])
    offs = np.minimum(rng.exponential(4, n).astype(int), 30)
    days_ = np.minimum(d + offs, ND - 1)
    share = np.full(NC, .2 / (NC - 1)); share[cr_country[c]] = .8
    ctry = rng.choice(NC, n, p=share)
    clicked = rng.random(n) < .35
    m = np.zeros((ND, NC), dtype=int)
    for org, mask in (("inf_click", clicked), ("inf_hidden", ~clicked)):
        m[:] = 0
        np.add.at(m, (days_[mask], ctry[mask]), 1)
        add_users(m, org, creator=c, video=vid)

users = pd.concat(frames, ignore_index=True)
N = len(users)
users["user_id"] = rng.permutation(N) + 1_000_000
origin = users["origin"].map({o: i for i, o in enumerate(ORIGINS)}).values
country = users["country"].values
# arrival time: day + random time of day
start_ns = DAYS.values[users["day"].values].astype("int64") + rng.integers(0, DAY_NS, N)
device = np.where(rng.random(N) < .55, "mobile", "desktop")
print(f"prospects: {N:,}")

# ================================================================== 3. touchpoint paths
T = 8                                    # max touchpoints per prospect
ch = np.full((N, T), -1)                 # channel code per position (-1 = none)
ts = np.zeros((N, T), dtype="int64")

FIRST = {"ppc_nb": PPC_NB, "seo": SEO, "inf_click": INFLU, "aff_content": AFF_CONTENT,
         "word_of_mouth": BRAND_SEARCH, "direct": DIRECT, "coupon": AFF_COUPON}
for o, code in FIRST.items():
    ch[origin == ORIGINS.index(o), 0] = code
hidden = origin == ORIGINS.index("inf_hidden")
ch[hidden, 0] = rng.choice([BRAND_SEARCH, DIRECT, AFF_COUPON], hidden.sum(), p=[.55, .25, .20])
ts[:, 0] = start_ns

# follow-up visits: which channel comes next, given the origin (assumption)
FOLLOW_CODES = [BRAND_SEARCH, SEO, DIRECT, AFF_CONTENT, AFF_COUPON, EMAIL, PPC_NB]
FOLLOW = {"ppc_nb":        [.30, .12, .25, .10, .06, .12, .05],
          "seo":           [.22, .25, .28, .08, .05, .12, .00],
          "inf_click":     [.40, .08, .25, .04, .10, .08, .05],
          "inf_hidden":    [.40, .08, .30, .04, .10, .08, .00],
          "aff_content":   [.25, .12, .35, .10, .05, .13, .00],
          "word_of_mouth": [.25, .15, .40, .05, .05, .10, .00],
          "direct":        [.25, .15, .40, .05, .05, .10, .00],
          "coupon":        [.30, .05, .45, .00, .10, .10, .00]}
n_extra = np.minimum(rng.geometric(.5, N) - 1, T - 2)    # 0..6 extra visits, mean ~1
for j in range(1, T - 1):
    active = n_extra >= j
    for i, o in enumerate(ORIGINS):
        m = active & (origin == i)
        ch[m, j] = rng.choice(FOLLOW_CODES, m.sum(), p=FOLLOW[o])
    ts[active, j] = ts[active, j - 1] + (rng.exponential(2.5, active.sum()) * DAY_NS).astype("int64")

# conversion: depends on origin and on the number of visits (assumption)
BASE_CONV = {"ppc_nb": .050, "seo": .062, "inf_click": .10, "inf_hidden": .11, "aff_content": .11,
             "word_of_mouth": .16, "direct": .13, "coupon": .18}
p_conv = np.array([BASE_CONV[o] for o in ORIGINS])[origin] * (1 + .30 * n_extra)
converts = rng.random(N) < np.minimum(p_conv, .65)

# coupon-site visit right before checkout (buyer already decided): mostly converters
P_COUPON_END = {"ppc_nb": .10, "seo": .08, "inf_click": .22, "inf_hidden": .22, "aff_content": .06,
                "word_of_mouth": .15, "direct": .12, "coupon": .05}
p_ce = np.where(converts, np.array([P_COUPON_END[o] for o in ORIGINS])[origin], .03)
coupon_end = rng.random(N) < p_ce
last_pos = n_extra.copy()
pos = last_pos + 1
ch[coupon_end, pos[coupon_end]] = AFF_COUPON
ts[coupon_end, pos[coupon_end]] = ts[coupon_end, last_pos[coupon_end]] + rng.integers(60, 20 * 60, coupon_end.sum()) * 10**9
last_pos = np.where(coupon_end, pos, last_pos)

# resolve brand searches: paid ad (60%) or organic result (40%) when ads run.
# During the geo test (ads off) almost everyone clicks the organic result;
# 15% of would-be ad clickers are lost to competitors' ads on the brand name (assumption).
is_bs = ch == BRAND_SEARCH
in_test = np.isin(country, TEST_COUNTRIES)[:, None] & (ts >= TEST_START) & (ts <= TEST_END)
r = rng.random((N, T))
organic_brand = is_bs & ((r >= .60) | in_test)
ch[is_bs] = PPC_BRAND
ch[organic_brand] = SEO
lost = is_bs & in_test & (r < .60 * .15)
ch[lost] = -1                                   # they clicked a competitor's ad instead
converts &= ~lost.any(axis=1)

# drop visits after the observation date
ch[ts > END_NS] = -1
valid = ch >= 0
last_valid = T - 1 - np.argmax(valid[:, ::-1], axis=1)
order_ns = ts[np.arange(N), last_valid] + rng.integers(2, 60, N) * 60 * 10**9
converts &= (order_ns <= END_NS) & valid.any(axis=1)   # no visit left = no order

# visit where the cart was started (used for "already in cart" analysis)
cart = np.zeros((N, T), dtype=bool)
cart[converts, last_valid[converts]] = True
pre = converts & coupon_end & (last_pos >= 1)
cart_pre = pre & (rng.random(N) < .80)
cart[cart_pre, last_pos[cart_pre] - 1] = True
cart[~converts] = valid[~converts] & (rng.random(((~converts).sum(), T)) < .03)

# ------------------------------------------------------------------ long touchpoint table
ui, pj = np.nonzero(valid)
tch = ch[ui, pj]
tp = pd.DataFrame({"user_id": users["user_id"].values[ui],
                   "ts": pd.to_datetime(ts[ui, pj]),
                   "channel": np.array(CHANNELS)[tch],
                   "country": COUNTRIES[country[ui]],
                   "device": device[ui],
                   "cart_started": cart[ui, pj]})
n_tp = len(tp)
sub = np.empty(n_tp, dtype=object)
camp = np.full(n_tp, None, dtype=object)
creator_id = np.full(n_tp, None, dtype=object)
affiliate_id = np.full(n_tp, None, dtype=object)
cty = COUNTRIES[country[ui]]

m = tch == PPC_BRAND
sub[m] = "Google Ads - brand"; camp[m] = "brand_" + cty[m]
m = tch == PPC_NB
sub[m] = "Google Ads - generic"
camp[m] = rng.choice(["nb_web_hosting", "nb_wordpress", "nb_website_builder", "nb_vps"], m.sum(), p=[.4, .25, .2, .15]) + "_" + cty[m]
m = tch == SEO
sub[m] = np.where(organic_brand[ui[m], pj[m]], "Organic - brand", "Organic - tutorials")
m = tch == AFF_CONTENT
own = users["affiliate"].values[ui] >= 0
aff_pick = np.where(own & (pj == 0), users["affiliate"].values[ui],
                    rng.choice(content_ids, n_tp, p=aff_size[content_ids] / aff_size[content_ids].sum()))
affiliate_id[m] = aff_code[aff_pick[m]]
sub[m] = np.where(aff_type[aff_pick[m]] == "review", "Review site", "Content site")
m = tch == AFF_COUPON
cp_pick = rng.choice(coupon_ids, n_tp, p=aff_size[coupon_ids] / aff_size[coupon_ids].sum())
affiliate_id[m] = aff_code[cp_pick[m]]; sub[m] = "Coupon site"
m = tch == INFLU
cr = users["creator"].values[ui[m]]
creator_id[m] = cr_code[cr]; sub[m] = cr_platform[cr]
camp[m] = "video_" + pd.Series(users["video"].values[ui[m]]).astype(str).values
m = tch == EMAIL
sub[m] = rng.choice(["Onboarding e-mail", "Newsletter"], m.sum(), p=[.6, .4])
m = tch == DIRECT
sub[m] = "Direct"
tp["sub_channel"] = sub
tp["campaign_id"] = camp
tp["creator_id"] = creator_id
tp["affiliate_id"] = affiliate_id

# ================================================================== 4. orders
buy = np.nonzero(converts)[0]
NB = len(buy)
o_origin = np.array(ORIGINS)[origin[buy]]
o_country = country[buy]

# what the buyer saw last (needed for coupon codes, CPA fees and commissions)
lp = last_valid[buy]
last_ch = ch[buy, lp]
last_coupon = last_ch == AFF_COUPON

PRODUCTS = np.array(["shared", "builder", "cloud", "vps"])
PROD_P = {"seo": [.55, .10, .15, .20], "inf_click": [.45, .35, .08, .12], "inf_hidden": [.45, .35, .08, .12],
          "ppc_nb": [.55, .20, .12, .13]}
PLAN_P = {"seo": [.06, .17, .22, .55], "word_of_mouth": [.08, .22, .25, .45], "direct": [.08, .22, .25, .45],
          "aff_content": [.07, .20, .25, .48], "inf_click": [.08, .20, .22, .50], "inf_hidden": [.08, .20, .22, .50],
          "ppc_nb": [.18, .32, .20, .30], "coupon": [.04, .16, .25, .55]}
product = np.empty(NB, dtype=object)
plan = np.zeros(NB, dtype=int)
for o in ORIGINS:
    m = o_origin == o
    product[m] = rng.choice(PRODUCTS, m.sum(), p=PROD_P.get(o, [.58, .18, .12, .12]))
    plan[m] = rng.choice([1, 12, 24, 48], m.sum(), p=PLAN_P[o])
plan[(product == "vps") & (plan == 48)] = 24          # VPS is sold up to 24 months

# intro price per month (USD). 48m (24m for VPS) and renewal prices come from hostinger.com;
# shorter-term prices are assumptions. Converted at 0.87 EUR/USD, then regional index.
INTRO = {"shared": {1: 10.99, 12: 2.99, 24: 2.49, 48: 1.99},
         "builder": {1: 10.99, 12: 2.99, 24: 2.49, 48: 1.99},
         "cloud": {1: 25.99, 12: 11.99, 24: 9.99, 48: 7.99},
         "vps": {1: 11.99, 12: 7.99, 24: 6.49}}
RENEW = {"shared": 10.99, "builder": 10.99, "cloud": 25.99, "vps": 11.99}
USD_EUR = 0.87
price_m = np.array([INTRO[p][t] for p, t in zip(product, plan)])
list_price = np.round(price_m * plan * USD_EUR * C_PRICE[o_country], 2)

# coupon codes: influencer buyers often type the creator's code; coupon-site buyers use the
# site's own code, or a leaked creator code once it circulates on coupon sites
coupon_code = np.full(NB, None, dtype=object)
o_creator = users["creator"].values[buy]
inf_buyer = np.isin(o_origin, ["inf_click", "inf_hidden"])
m = inf_buyer & ~last_coupon & (rng.random(NB) < .55)
coupon_code[m] = cr_code[o_creator[m]]
o_ns = order_ns[buy]
for k in np.nonzero(last_coupon)[0]:
    active_leaks = [c for c, t0 in LEAKS.items() if o_ns[k] >= t0]
    if inf_buyer[k] and rng.random() < .5:
        coupon_code[k] = cr_code[o_creator[k]]                        # own creator's code, found on a coupon site
    elif active_leaks and rng.random() < .45:
        w = np.array([3.0 if cr_country[c] == o_country[k] else 1.0 for c in active_leaks])
        coupon_code[k] = cr_code[rng.choice(active_leaks, p=w / w.sum())]
discount = np.where(coupon_code != None, np.round(.10 * list_price, 2), 0.0)   # codes give 10% off (assumption)
paid = np.round(list_price - discount, 2)

orders = pd.DataFrame({
    "order_id": np.arange(1, NB + 1) + 500_000,
    "user_id": users["user_id"].values[buy],
    "ts": pd.to_datetime(o_ns),
    "product": product, "plan_months": plan,
    "list_price": list_price, "discount": discount, "paid_amount_eur": paid,
    "coupon_code": coupon_code,
    "country": COUNTRIES[o_country], "device": device[buy]})
# coupon-site code of the last coupon site visited (for buyers who used the site's own code)
last_tp = tp.sort_values("ts").groupby("user_id").tail(1).set_index("user_id")
no_code = last_coupon & (orders["coupon_code"].isna().values)
orders.loc[no_code, "coupon_code"] = last_tp.loc[orders.loc[no_code, "user_id"], "affiliate_id"].values
orders.loc[no_code, "discount"] = np.round(.10 * orders.loc[no_code, "list_price"], 2)
orders["paid_amount_eur"] = np.round(orders["list_price"] - orders["discount"], 2)
orders = orders.sort_values("ts").reset_index(drop=True)
orders["order_id"] = np.arange(1, NB + 1) + 500_000
o_origin = pd.Series(o_origin, index=pd.Index(users["user_id"].values[buy])).loc[orders["user_id"]].values
last_coupon = pd.Series(last_coupon, index=pd.Index(users["user_id"].values[buy])).loc[orders["user_id"]].values

# ================================================================== 5. refunds (30-day guarantee)
REFUND_P = {"seo": .04, "word_of_mouth": .045, "direct": .045, "aff_content": .06, "inf_click": .075,
            "inf_hidden": .075, "ppc_nb": .08, "coupon": .12}
p_ref = np.array([REFUND_P[o] for o in o_origin]) + .05 * last_coupon + .04 * (orders["plan_months"].values == 1)
refunded = rng.random(NB) < p_ref
ref_ts = orders["ts"].values + (np.minimum(rng.exponential(6, NB), 29.9) * DAY_NS).astype("timedelta64[ns]")
refunded &= ref_ts <= np.datetime64(END)
refunds = pd.DataFrame({"order_id": orders["order_id"].values[refunded],
                        "refund_ts": ref_ts[refunded],
                        "amount": orders["paid_amount_eur"].values[refunded]})

# ================================================================== 6. renewals
RENEW_P = {"shared": .55, "builder": .45, "cloud": .65, "vps": .60}
ORIGIN_MULT = {"seo": 1.20, "word_of_mouth": 1.10, "direct": 1.10, "aff_content": 1.0, "inf_click": .85,
               "inf_hidden": .85, "ppc_nb": .85, "coupon": .75}
mult = np.array([ORIGIN_MULT[o] for o in o_origin]) * np.where(last_coupon, .85, 1.0)
o_prod = orders["product"].values
o_plan = orders["plan_months"].values
o_ts = orders["ts"].values.astype("int64")
o_cidx = pd.Series(range(NC), index=COUNTRIES).loc[orders["country"]].values
renew_m = np.array([RENEW[p] for p in o_prod]) * USD_EUR * C_PRICE[o_cidx]
rows = []
# 1-month plans: renewed (or not) every month until the customer stops
monthly = (o_plan == 1) & ~refunded
alive = monthly.copy()
q = np.minimum(.78 * np.sqrt(mult), .93)
for k in range(1, 25):
    due = o_ts + int(k * MONTH_DAYS * DAY_NS)
    m = alive & (due <= END_NS)
    if not m.any():
        break
    ok = rng.random(NB) < q
    rows.append(pd.DataFrame({"order_id": orders["order_id"].values[m], "renewal_ts": pd.to_datetime(due[m]),
                              "renewed": ok[m], "amount": np.where(ok[m], np.round(renew_m[m], 2), 0.0)}))
    alive = m & ok
# 12/24/48-month plans: one renewal decision at the end of the term (renewed for 12 months)
due = o_ts + (o_plan * MONTH_DAYS * DAY_NS).astype("int64")
m = (o_plan > 1) & ~refunded & (due <= END_NS)
p_ren = np.minimum(np.array([RENEW_P[p] for p in o_prod]) * mult, .92)
ok = rng.random(NB) < p_ren
rows.append(pd.DataFrame({"order_id": orders["order_id"].values[m], "renewal_ts": pd.to_datetime(due[m]),
                          "renewed": ok[m], "amount": np.where(ok[m], np.round(renew_m[m] * 12, 2), 0.0)}))
renewals = pd.concat(rows, ignore_index=True).sort_values(["order_id", "renewal_ts"]).reset_index(drop=True)

# ================================================================== 7. spend
spend_rows = []
day_str = DAYS.normalize()

# 7a. PPC non-brand: planned daily budget split across 4 campaigns; clicks from touchpoints
nb_tp = tp[tp["channel"] == "PPC Non-brand"]
nb_clicks = nb_tp.groupby([nb_tp["ts"].dt.normalize(), "campaign_id"]).size()
CAMP_SPLIT = {"nb_web_hosting": .4, "nb_wordpress": .25, "nb_website_builder": .2, "nb_vps": .15}
for c in range(NC):
    for cp, share in CAMP_SPLIT.items():
        cid = f"{cp}_{COUNTRIES[c]}"
        df = pd.DataFrame({"date": day_str, "campaign_id": cid, "country": COUNTRIES[c],
                           "spend_eur": np.round(nb_spend[:, c] * share, 2)})
        df["clicks"] = nb_clicks.reindex(pd.MultiIndex.from_arrays([df["date"], df["campaign_id"]])).fillna(0).astype(int).values
        df["clicks"] = (df["clicks"] * 1.25).round().astype(int)   # returning visitors click too
        df["impressions"] = (df["clicks"] / .045).round().astype(int)
        df["channel"], df["sub_channel"] = "PPC Non-brand", "Google Ads - generic"
        spend_rows.append(df)

# 7b. PPC brand: spend follows brand-search demand (clicks x CPC)
br = tp[tp["channel"] == "PPC Brand"]
br = br.groupby([br["ts"].dt.normalize().rename("date"), "country"]).size().rename("clicks").reset_index()
cpc = pd.Series(C_CPC, index=COUNTRIES).loc[br["country"]].values
br["spend_eur"] = np.round(br["clicks"] * cpc * rng.lognormal(0, .1, len(br)), 2)
br["impressions"] = (br["clicks"] / .30).round().astype(int)
br["campaign_id"] = "brand_" + br["country"]
br["channel"], br["sub_channel"] = "PPC Brand", "Google Ads - brand"
spend_rows.append(br)

# 7c. influencers: flat fee on the video date, CPA fee for each sale with the code or the link
vid_df = pd.DataFrame(videos, columns=["video_id", "creator", "day"])
vid_df["date"] = DAYS[vid_df["day"].values]
inf_flat = pd.DataFrame({"date": vid_df["date"], "creator_id": cr_code[vid_df["creator"]],
                         "campaign_id": "video_" + vid_df["video_id"].astype(str),
                         "country": COUNTRIES[cr_country[vid_df["creator"]]],
                         "spend_eur": cr_flat_fee[vid_df["creator"]],
                         "impressions": (cr_audience[vid_df["creator"]] * rng.uniform(.15, .45, len(vid_df))).round().astype(int)})
inf_clicks = tp[tp["channel"] == "Influencers"].groupby("campaign_id").size()
inf_flat["clicks"] = inf_clicks.reindex(inf_flat["campaign_id"]).fillna(0).astype(int).values
inf_flat = inf_flat[inf_flat["spend_eur"] > 0]

# last touchpoint of each buyer within 30 days before the order (same rule as the affiliate cookie)
tp_o = tp.merge(orders[["order_id", "user_id", "ts"]].rename(columns={"ts": "order_ts"}), on="user_id")
tp_o = tp_o[(tp_o["ts"] <= tp_o["order_ts"]) & (tp_o["ts"] >= tp_o["order_ts"] - pd.Timedelta(days=30))]
last_touch = tp_o.sort_values("ts").groupby("order_id").tail(1).set_index("order_id")
orders_lt = orders.join(last_touch[["channel", "creator_id", "affiliate_id"]], on="order_id")
refunded_ids = set(refunds["order_id"])
not_ref = ~orders_lt["order_id"].isin(refunded_ids)

code_cr = orders_lt["coupon_code"].where(orders_lt["coupon_code"].isin(cr_code))
cpa_creator = code_cr.fillna(orders_lt["creator_id"])                 # code first, then link
cpa_fee = pd.Series(cr_cpa_fee, index=cr_code)
cpa = orders_lt[cpa_creator.notna()].assign(creator_id=cpa_creator.dropna())
cpa["spend_eur"] = cpa_fee.reindex(cpa["creator_id"]).values
cpa = cpa[cpa["spend_eur"] > 0]
cpa = cpa.groupby([cpa["ts"].dt.normalize().rename("date"), "creator_id", "country"])["spend_eur"].sum().reset_index()
cpa["campaign_id"] = "cpa_" + cpa["creator_id"]
cpa["impressions"], cpa["clicks"] = 0, 0
for df in (inf_flat, cpa):
    df["channel"] = "Influencers"
    df["sub_channel"] = pd.Series(cr_platform, index=cr_code).reindex(df["creator_id"]).values
    spend_rows.append(df)

# 7d. affiliates: commission on sales where the affiliate is the last click within 30 days,
#     plans of 12 months or more, not refunded, capped at $300 (hostinger.com agreement)
aff = orders_lt[orders_lt["affiliate_id"].notna() & orders_lt["channel"].str.startswith("Affiliates", na=False)
                & (orders_lt["plan_months"] >= 12) & not_ref].copy()
rate = pd.Series(aff_rate, index=aff_code).reindex(aff["affiliate_id"]).values
aff["spend_eur"] = np.minimum(aff["paid_amount_eur"] * rate, 300 * USD_EUR).round(2)
aff = aff.groupby([aff["ts"].dt.normalize().rename("date"), "channel", "affiliate_id", "country"])["spend_eur"].sum().reset_index()
aff_sub = pd.Series(np.where(aff_type == "coupon", "Coupon site", np.where(aff_type == "review", "Review site", "Content site")), index=aff_code)
aff["sub_channel"] = aff_sub.reindex(aff["affiliate_id"]).values
aff["campaign_id"] = "aff_" + aff["affiliate_id"]
aff["impressions"], aff["clicks"] = 0, 0
spend_rows.append(aff)

# 7e. SEO content team and e-mail tooling: fixed monthly cost, spread per day and country
for chan, sub_, monthly_eur, cid in (("SEO", "Content team & tools", 24_000, "seo_content"),
                                     ("Email", "CRM & e-mail tooling", 6_000, "crm_lifecycle")):
    days_in_month = DAYS.days_in_month.values
    for c in range(NC):
        spend_rows.append(pd.DataFrame({"date": day_str, "channel": chan, "sub_channel": sub_, "campaign_id": cid,
                                        "country": COUNTRIES[c], "impressions": 0, "clicks": 0,
                                        "spend_eur": np.round(monthly_eur / days_in_month * C_WEIGHT[c], 2)}))

spend = pd.concat(spend_rows, ignore_index=True)
for col in ("creator_id", "affiliate_id"):
    if col not in spend:
        spend[col] = None
spend = spend[["date", "channel", "sub_channel", "campaign_id", "creator_id", "affiliate_id",
               "country", "spend_eur", "impressions", "clicks"]]
spend = spend[spend["spend_eur"] != 0].sort_values(["date", "channel"]).reset_index(drop=True)

# invoices = what finance pays (true cost), monthly per paid channel
spend["month"] = spend["date"].dt.to_period("M").dt.to_timestamp()
invoices = spend.groupby(["month", "channel"])["spend_eur"].sum().reset_index()
invoices["invoiced_eur"] = np.round(invoices["spend_eur"] * (1 + rng.normal(0, .002, len(invoices))), 2)
invoices = invoices.drop(columns="spend_eur")
spend = spend.drop(columns="month")

# ================================================================== 8. tracking anomalies
# 8a. a cost import failed: PPC non-brand cost missing for one day (still invoiced)
spend = spend[~((spend["channel"] == "PPC Non-brand") & (spend["date"] == pd.Timestamp("2025-08-14")))]
# 8b. a few PPC rows lose their campaign id
idx = spend.index[(spend["channel"] == "PPC Non-brand")]
spend.loc[rng.choice(idx, 60, replace=False), "campaign_id"] = None
# 8c. ~2% of buyers declined cookies: their touchpoints are not tracked
no_track = rng.choice(orders["user_id"].values, int(.02 * NB), replace=False)
tp = tp[~tp["user_id"].isin(no_track)]
# 8d. one day of duplicated tracking events (tag fired twice), like the Taap.it click gap
dup_day = tp["ts"].dt.normalize() == pd.Timestamp("2025-06-18")
tp = pd.concat([tp, tp[dup_day].assign(ts=lambda d: d["ts"] + pd.Timedelta(milliseconds=300))])
tp = tp.sort_values(["user_id", "ts"]).reset_index(drop=True)
tp.insert(0, "touch_id", np.arange(1, len(tp) + 1))

# ================================================================== 9. dimension tables
creators = pd.DataFrame({"creator_id": cr_code, "creator_name": [f"{p} creator {i+1:02d}" for i, p in enumerate(cr_platform)],
                         "platform": cr_platform, "niche": cr_niche, "audience_size": cr_audience.astype(int),
                         "main_country": COUNTRIES[cr_country], "fee_model": cr_fee_model,
                         "flat_fee_per_video_eur": cr_flat_fee, "cpa_fee_eur": cr_cpa_fee, "promo_code": cr_code})
video_dates = pd.DataFrame({"video_id": vid_df["video_id"], "creator_id": cr_code[vid_df["creator"]],
                            "video_date": vid_df["date"]})
affiliates = pd.DataFrame({"affiliate_id": aff_code, "type": aff_type, "main_country": COUNTRIES[aff_country],
                           "commission_rate": aff_rate, "promo_code": aff_code})
weeks = pd.date_range("2024-04-29", "2026-10-26", freq="W-MON")
geo_test = pd.DataFrame([(c, w) for c in COUNTRIES for w in weeks], columns=["country", "week"])
geo_test["group"] = np.where(geo_test["country"].isin(COUNTRIES[TEST_COUNTRIES]), "test", "control")
in_window = (geo_test["week"] >= pd.Timestamp(TEST_START)) & (geo_test["week"] <= pd.Timestamp(TEST_END))
geo_test["brand_ads_on"] = ~((geo_test["group"] == "test") & in_window)

# ================================================================== 10. write
tables = {"touchpoints": tp, "orders": orders, "refunds": refunds, "renewals": renewals, "spend": spend,
          "invoices": invoices, "creators": creators, "video_dates": video_dates, "affiliates": affiliates,
          "geo_test": geo_test}
for name, df in tables.items():
    df.to_parquet(OUT / f"sim_{name}.parquet", index=False)
    if name != "touchpoints":
        df.to_csv(OUT / f"sim_{name}.csv", index=False)
    print(f"sim_{name:12s} {len(df):>10,} rows")

# ================================================================== 11. plausibility checks
print("\n--- plausibility (see data/ASSUMPTIONS.md) ---")
print(f"prospect -> order conversion: {NB / N:.1%}")
print(f"orders: {NB:,}   gross paid: EUR {orders['paid_amount_eur'].sum():,.0f}   avg order: EUR {orders['paid_amount_eur'].mean():.0f}")
print(f"total spend: EUR {spend['spend_eur'].sum():,.0f}   blended CAC: EUR {spend['spend_eur'].sum() / NB:.0f}")
print(f"refund rate (30 days): {len(refunds) / NB:.1%}")
print("plan mix:", orders["plan_months"].value_counts(normalize=True).sort_index().round(3).to_dict())
print("spend by channel (EUR k):", (spend.groupby("channel")["spend_eur"].sum() / 1000).round(0).to_dict())
print("true origin of buyers:", pd.Series(o_origin).value_counts(normalize=True).round(3).to_dict())
print("leaked creators:", {cr_code[c]: str(pd.Timestamp(t).date()) for c, t in LEAKS.items()})
