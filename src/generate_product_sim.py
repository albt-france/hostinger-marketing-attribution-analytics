"""Generate the SIMULATED product dataset used in the product part of the case study (seed 42).

Nothing in this file is Hostinger data. It reads the customers simulated by src/generate_sim.py
(same user_id, country, device, order date and acquisition channel) and adds what they do
in three products, in an Amplitude-like event format:

- Hostinger Reach (AI e-mail marketing): onboarding funnel, campaigns, AI copy, upgrades.
- Hostinger Mail (business e-mail with AI replies): daily inbox use, messages sent, AI replies.
- Customer referral programme: links shared, friends who sign up and buy.

Public facts used (hostinger.com, read 13 Nov 2026, see data/SOURCES.md): Reach Starter plan limited
to 100 recipients, referral reward 20% of the friend's purchase, friend gets 20% off, reward paid after
45 days. Every other number is an assumption, listed in data/ASSUMPTIONS.md ("Product simulation").

Deliberate mechanisms (so the analysis has something real to find):
- Users who send their first Reach campaign within 7 days stay much longer. Part of that gap is
  causal (built-in), part comes from an unobserved "intent" that also makes them faster.
- A/B test on Reach onboarding (AI-prefilled first campaign vs blank editor): real but modest effect,
  and on one day a release bug sends every mobile user to control (sample ratio mismatch).
- AI replies in Mail raise engagement for mobile users only (staggered rollout by country).
- Some referrals come from customers who refer themselves (second account, same card or device).

Usage:  python src/generate_product_sim.py      (after src/generate_sim.py)
Output: data/clean/sim_product_events.parquet, sim_experiments.parquet, sim_referrals.parquet (+ .csv
        for the two small tables)
"""
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
CLEAN = Path(__file__).resolve().parents[1] / "data" / "clean"

DAY_NS = 86_400 * 10**9
HOUR_NS = 3_600 * 10**9
MIN_NS = 60 * 10**9
END = pd.Timestamp("2026-10-31 23:59:59").value          # same observation date as the marketing data
WINDOW_START = pd.Timestamp("2025-05-01").value          # product analytics window (assumption)

def ns(ts): return pd.Timestamp(ts).value
def sig(x): return 1 / (1 + np.exp(-x))
def logit(p): return np.log(p / (1 - p))
def days(n_days): return (np.asarray(n_days) * DAY_NS).astype("int64")

# ================================================================== 0. customers (from generate_sim.py)
orders = pd.read_parquet(CLEAN / "sim_orders.parquet")
refunds = pd.read_parquet(CLEAN / "sim_refunds.parquet")
tp = pd.read_parquet(CLEAN / "sim_touchpoints.parquet", columns=["user_id", "ts", "channel"])

# acquisition channel = first click in the 30 days before the order (same rule as sql/00_staging.sql)
w = tp.merge(orders[["user_id", "ts"]].rename(columns={"ts": "order_ts"}), on="user_id")
w = w[(w["ts"] <= w["order_ts"]) & (w["ts"] >= w["order_ts"] - pd.Timedelta(days=30))]
first_click = w.sort_values(["user_id", "ts"]).groupby("user_id")["channel"].first()

cust = orders[["user_id", "order_id", "ts", "product", "plan_months", "paid_amount_eur", "coupon_code",
               "country", "device"]].rename(columns={"ts": "order_ts"}).reset_index(drop=True)
cust["channel"] = cust["user_id"].map(first_click).fillna("Unattributed")
cust["refunded"] = cust["order_id"].isin(refunds["order_id"])
N = len(cust)
order_ns = cust["order_ts"].values.astype("int64")
product = cust["product"].values
country = cust["country"].values
device = cust["device"].values
channel = cust["channel"].values
refunded = cust["refunded"].values
# unobserved intent: how serious the customer is about marketing their business. Customers who came
# through creators and content sites are more often small-business owners; coupon hunters less (assumption)
INTENT_SHIFT = {"Influencers": .30, "Affiliates - Content": .15, "SEO": .10, "Email": .10, "Direct": 0.0,
                "PPC Brand": 0.0, "Unattributed": 0.0, "PPC Non-brand": -.15, "Affiliates - Coupon": -.35}
intent = rng.normal(size=N) + np.array([INTENT_SHIFT[c] for c in channel])
device_id = np.char.add("dv", rng.integers(16**8, 16**9, N).astype(str))
fingerprint = np.char.add("pf", rng.integers(10**9, 10**10, N).astype(str))
PLATFORM = np.where(device == "mobile", "Web - mobile", "Web - desktop")

event_frames = []

def add_events(idx, name, prod, t, props=None, dev=None):
    """idx: customer row index per event; t: event time in ns. Events after the observation date are dropped."""
    idx, t = np.asarray(idx), np.asarray(t, dtype="int64")
    keep = t <= END
    props = np.full(len(idx), "{}", dtype=object) if props is None else np.asarray(props, dtype=object)
    dev = device_id[idx] if dev is None else np.asarray(dev)
    event_frames.append(pd.DataFrame({
        "user_id": cust["user_id"].values[idx[keep]], "device_id": dev[keep], "event_name": name,
        "event_time": pd.to_datetime(t[keep]), "product": prod, "platform": PLATFORM[idx[keep]],
        "country": country[idx[keep]], "event_properties": props[keep]}))

def jprop(key, values):
    """JSON event properties, e.g. {"contacts": 250}."""
    v = np.asarray(values)
    if v.dtype.kind in "iu":
        return np.char.add(np.char.add('{"' + key + '": ', v.astype(str)), "}")
    if v.dtype.kind == "b":
        return np.where(v, '{"' + key + '": true}', '{"' + key + '": false}')
    return np.char.add(np.char.add('{"' + key + '": "', v.astype(str)), '"}')

# ================================================================== 1. Reach: who starts onboarding
BASE = {"builder": .60, "shared": .48, "cloud": .34, "vps": .20}           # small-business products first
CH_MULT = {"Influencers": 1.20, "Affiliates - Content": 1.10, "Email": 1.10, "SEO": 1.0, "Direct": 1.0,
           "PPC Brand": 1.0, "Unattributed": 1.0, "PPC Non-brand": .80, "Affiliates - Coupon": .75}
p_start = (np.array([BASE[p] for p in product]) * np.array([CH_MULT[c] for c in channel])
           * np.exp(.25 * intent) * np.where(refunded, .3, 1.0)).clip(0, .9)
new = order_ns >= WINDOW_START
existing = ~new & ~refunded
start = np.full(N, -1, dtype="int64")
r = rng.random(N)
m = new & (r < p_start)                                   # new customers: a few days after buying
start[m] = order_ns[m] + days(np.minimum(rng.exponential(2.0, m.sum()), 60))
m = existing & (r < .55 * p_start)                         # older customers: any time in the window
start[m] = WINDOW_START + rng.integers(0, END - WINDOW_START, m.sum())
NEWSLETTER = ns("2026-07-14")                              # Reach featured in the customer newsletter
pool = np.nonzero(existing & (start < 0))[0]
m = rng.choice(pool, 1_100, replace=False)
start[m] = NEWSLETTER + 8 * HOUR_NS + np.minimum(rng.exponential(3 * HOUR_NS, len(m)), 15 * HOUR_NS).astype("int64")
source = np.where(new, "post_purchase", "hpanel").astype(object)
source[m] = "newsletter"
start[start > END] = -1
R = np.nonzero(start >= 0)[0]                              # Reach users (row index into cust)
nR = len(R)
s0 = start[R]
z = intent[R]

# ================================================================== 2. A/B test on onboarding
TEST_START, TEST_END = ns("2026-05-04"), ns("2026-08-23 23:59:59")
BUG_DAY = ns("2026-07-14")                                 # release bug: every mobile user sent to control
in_test = (s0 >= TEST_START) & (s0 <= TEST_END)
treat = in_test & (rng.random(nR) < .5)
bug = in_test & (s0 >= BUG_DAY) & (s0 < BUG_DAY + DAY_NS) & (device[R] == "mobile")
treat[bug] = False
experiments = pd.DataFrame({
    "experiment_id": "reach_onboarding_ai_prefill",
    "user_id": cust["user_id"].values[R[in_test]],
    "variant": np.where(treat[in_test], "treatment", "control"),
    "assigned_ts": pd.to_datetime(s0[in_test]),
    "platform": PLATFORM[R[in_test]]}).sort_values("assigned_ts").reset_index(drop=True)

# ================================================================== 3. Reach onboarding funnel
small_mkt = np.isin(country[R], ["IN", "ID"])
u_tmpl = rng.random(nR)
t_tmpl = s0 + days(rng.exponential(.3, nR))
u_cont = rng.random(nR)
t_cont = t_tmpl + days(rng.exponential(1.0, nR))
contacts = np.exp(rng.normal(np.log(180), 1.0, nR)).round().clip(5, 20_000).astype(int)
u_send = rng.random(nR)
e_first = rng.standard_exponential(nR)                     # delay to the first campaign, before scaling

def funnel(treated):
    """Funnel outcomes for a given assignment, with the same random draws (used for the true effect)."""
    tm = (u_tmpl < sig(logit(.74) + .5 * z + .35 * treated)) & (t_tmpl <= END)
    tf = t_cont + days(e_first * (6.0 * np.exp(-.35 * z) * np.where(treated, .75, 1.0)))
    co = tm & (u_cont < sig(logit(.62) + .5 * z - .35 * small_mkt)) & (t_cont <= END)
    se = co & (u_send < sig(logit(.68) + .6 * z)) & (tf <= END)
    return tm, co, se, tf

tmpl, cont, send, t_first = funnel(treat)
act7 = send & (t_first - s0 <= 7 * DAY_NS)                 # "aha" moment: first campaign within 7 days
# true effect of the AI-prefilled campaign on 7-day activation: everyone in the test treated vs nobody
act7_if = [(lambda o: o[2] & (o[3] - s0 <= 7 * DAY_NS))(funnel(np.full(nR, v))) for v in (True, False)]
true_effect = (act7_if[0] & in_test).sum() / in_test.sum() - (act7_if[1] & in_test).sum() / in_test.sum()

add_events(R, "reach_onboarding_started", "Reach", s0, jprop("source", source[R]))
add_events(R[tmpl], "reach_template_chosen", "Reach", t_tmpl[tmpl],
           jprop("template", np.where(treat[tmpl], "ai_prefilled", "blank")))
add_events(R[cont], "reach_contacts_imported", "Reach", t_cont[cont], jprop("contacts", contacts[cont]))
recip = np.minimum(contacts, 100)                          # free Starter: 100 recipients (public limit)
add_events(R[send], "reach_campaign_sent", "Reach", t_first[send], jprop("recipients", recip[send]))
first_ai = send & (rng.random(nR) < np.where(treat, .80, .40))
add_events(R[first_ai], "reach_ai_copy_used", "Reach", t_first[first_ai] - days(rng.uniform(.001, .02, first_ai.sum())))

# ================================================================== 4. Reach usage after onboarding (weekly)
WEEKS = 78
BETA = .9                                                  # built-in causal effect of the aha moment on churn
U = rng.random((nR, WEEKS))                                # churn draws
V = rng.random((nR, WEEKS))                                # activity draws

def weekly_alive(beta):
    h = sig(-1.5 - .7 * z - beta * act7)[:, None]
    surv = np.ones((nR, WEEKS), dtype=bool)
    surv[:, 1:] = np.cumprod(U[:, 1:] >= h, axis=1).astype(bool)   # week 0 always alive
    return surv

alive = weekly_alive(BETA)
week_start = s0[:, None] + np.arange(WEEKS)[None, :] * 7 * DAY_NS
week_first = np.where(send, (t_first - s0) // (7 * DAY_NS), 10**6)
k = np.arange(WEEKS)[None, :]
sending = k > week_first[:, None]                          # weeks after the first campaign
drafting = (k < week_first[:, None]) & (k >= 1)            # came back but has not sent yet
active_send = alive & sending & (V < .80)
active_draft = alive & drafting & (V < .35)
in_obs = week_start <= END

ui, wk = np.nonzero(active_send & in_obs)
n_camp = 1 + rng.poisson(.3, len(ui))
ui, wk = np.repeat(ui, n_camp), np.repeat(wk, n_camp)
t_c = week_start[ui, wk] + rng.integers(0, 7 * DAY_NS, len(ui))
add_events(R[ui], "reach_campaign_sent", "Reach", t_c, jprop("recipients", recip[ui]))
ai = rng.random(len(ui)) < np.where(treat[ui], .60, .40)
add_events(R[ui[ai]], "reach_ai_copy_used", "Reach", t_c[ai] - rng.integers(MIN_NS, 30 * MIN_NS, ai.sum()))
ui, wk = np.nonzero(active_draft & in_obs)
t_d = week_start[ui, wk] + rng.integers(0, 7 * DAY_NS, len(ui))
is_ai = rng.random(len(ui)) < .5
add_events(R[ui[is_ai]], "reach_ai_copy_used", "Reach", t_d[is_ai])
add_events(R[ui[~is_ai]], "reach_template_chosen", "Reach", t_d[~is_ai], jprop("template", np.full((~is_ai).sum(), "library")))

# upgrade to a paid plan: mostly users whose list is above the free 100-recipient limit
upg = send & (rng.random(nR) < np.where(contacts > 100, .30, .03) * np.exp(.2 * z))
t_up = t_first + days(rng.exponential(5, nR))
upg &= t_up <= END
add_events(R[upg], "reach_upgrade", "Reach", t_up[upg], jprop("to_plan", np.where(contacts[upg] > 500, "Pro", "Grow")))

# built-in causal part of the day-30 retention gap (same random draws, aha effect switched off)
def d30(surv):
    return (surv[:, 4] & ((sending[:, 4] & (V[:, 4] < .80)) | (drafting[:, 4] & (V[:, 4] < .35))))
mature = s0 + 35 * DAY_NS <= END
causal_gap = (d30(alive) & act7 & mature).sum() / (act7 & mature).sum() - (d30(weekly_alive(0)) & act7 & mature).sum() / (act7 & mature).sum()

# ================================================================== 5. Mail: daily use, AI replies (staggered rollout)
MAIL_START, MAIL_DAYS = ns("2026-03-02"), 238                # 2 Mar - 25 Oct 2026, 34 full weeks
WAVE = {"US": ns("2026-06-01"), "FR": ns("2026-06-01"), "ES": ns("2026-06-01"),
        "BR": ns("2026-08-03"), "IN": ns("2026-08-03"), "ID": ns("2026-08-03")}
P_MAIL = {"builder": .16, "shared": .13, "cloud": .10, "vps": .05}
mail = np.nonzero(~refunded & (order_ns < MAIL_START) & (rng.random(N) < np.array([P_MAIL[p] for p in product])))[0]
nM = len(mail)
p_day = (.33 * rng.lognormal(0, .45, nM)).clip(.03, .95)
msg_mean = rng.lognormal(np.log(2.0), .6, nM)
wave = np.array([WAVE[c] for c in country[mail]])
mobile = device[mail] == "mobile"
small_biz = np.isin(product[mail], ["builder", "shared"])
adopter = rng.random(nM) < np.where(mobile, .40, .30) * np.where(small_biz, 1.1, 1.0)
adopt_ts = wave + days(rng.exponential(10, nM))
# effect of AI replies once adopted: mobile users open more days and send more; desktop small-business
# users send slightly more; desktop cloud / VPS users: no change (assumption)
lift_day = np.where(mobile, 1.15, 1.0)
lift_msg = np.where(mobile, 1.15, np.where(small_biz, 1.04, 1.0))
day_ns = MAIL_START + np.arange(MAIL_DAYS) * DAY_NS
on = adopter[:, None] & (day_ns[None, :] >= adopt_ts[:, None])
active = rng.random((nM, MAIL_DAYS)) < np.where(on, (p_day * lift_day)[:, None], p_day[:, None]).clip(0, .97)
msgs = rng.poisson(np.where(on, (msg_mean * lift_msg)[:, None], msg_mean[:, None])) * active
ai_day = active & on & (rng.random((nM, MAIL_DAYS)) < .45)
ui, di = np.nonzero(active)
t_open = day_ns[di] + rng.integers(6 * HOUR_NS, 22 * HOUR_NS, len(ui))
add_events(mail[ui], "mail_inbox_opened", "Mail", t_open, jprop("sessions", 1 + rng.poisson(1.5, len(ui))))
s = msgs[ui, di] > 0
add_events(mail[ui[s]], "mail_message_sent", "Mail", t_open[s] + rng.integers(MIN_NS, HOUR_NS, s.sum()),
           jprop("count", msgs[ui[s], di[s]]))
ui, di = np.nonzero(ai_day)
add_events(mail[ui], "mail_ai_reply_used", "Mail", day_ns[di] + rng.integers(7 * HOUR_NS, 22 * HOUR_NS, len(ui)),
           jprop("count", 1 + rng.poisson(1.0, len(ui))))

# ================================================================== 6. referral programme
REWARD_RATE, FRIEND_DISCOUNT, HOLD_DAYS = .20, .20, 45     # public: 20% reward, 20% off, paid after 45 days
REWARD_CAP_EUR = 450 * .87                                 # "up to 450 USD", converted like the prices
sharer = np.nonzero(~refunded & (order_ns < END - 30 * DAY_NS) & (rng.random(N) < .05 * np.exp(.3 * intent)))[0]
share_ts = np.maximum(order_ns[sharer], WINDOW_START) + days(rng.exponential(60, len(sharer)))
ok = share_ts <= END - 7 * DAY_NS
sharer, share_ts = sharer[ok], share_ts[ok]
n_more = rng.poisson(.7, len(sharer))
more_idx = np.repeat(np.arange(len(sharer)), n_more)
more_ts = share_ts[more_idx] + days(rng.exponential(30, len(more_idx)))
add_events(sharer, "referral_link_shared", "Referral", share_ts, jprop("channel", rng.choice(["whatsapp", "email", "social", "copy_link"], len(sharer))))
add_events(sharer[more_idx], "referral_link_shared", "Referral", more_ts, jprop("channel", rng.choice(["whatsapp", "email", "social", "copy_link"], len(more_idx))))

# referred friends: buyers in the window who arrived by brand search, organic or direct, without a promo code
cand = np.nonzero((order_ns >= WINDOW_START + 14 * DAY_NS) & cust["coupon_code"].isna().values
                  & np.isin(channel, ["Direct", "PPC Brand", "SEO"]))[0]
cand = rng.permutation(cand)
genuine = cand[:3_200]
self_ref = cand[3_200:]
self_ref = self_ref[channel[self_ref] == "Direct"][:420]    # second accounts arrive by typing the URL
order_sharers = np.argsort(share_ts)
st_sorted = share_ts[order_sharers]

def pick_referrer(i, same_country_only):
    """A customer who shared a link before this order, from the same country 80% of the time."""
    n_ok = np.searchsorted(st_sorted, order_ns[i] - HOUR_NS)
    if n_ok == 0:
        return -1
    pool = order_sharers[:n_ok]
    same = pool[country[sharer[pool]] == country[i]]
    if len(same) and (same_country_only or rng.random() < .8):
        return rng.choice(same)
    return -1 if same_country_only else rng.choice(pool)

rows = []
for kind, group in (("genuine", genuine), ("self", self_ref)):
    for i in group:
        j = pick_referrer(i, kind == "self")
        if j < 0 or sharer[j] == i:
            continue
        ref_idx = sharer[j]
        if kind == "genuine":
            # friend signs up hours or days after the first share, and buys later
            sig_ts = order_ns[i] - int(rng.exponential(1.5) * DAY_NS) - MIN_NS
            sig_ts = min(max(sig_ts, share_ts[j] + int(rng.uniform(16, 600) * MIN_NS)), order_ns[i] - MIN_NS)
            quick = rng.random() < .05                      # 5%: link re-shared in a chat, friend signs up at once
            link_ts = sig_ts - int(rng.uniform(2, 12) * MIN_NS) if quick else share_ts[j]
            household = rng.random() < .03                  # same computer at home
            same_pf = rng.random() < .005                   # family card
        else:                                               # second account: share, sign up and buy in minutes
            quick = True
            link_ts = order_ns[i] - int(rng.uniform(4, 40) * MIN_NS)
            sig_ts = link_ts + int(rng.uniform(1, 3) * MIN_NS)
            household = rng.random() < .85
            same_pf = rng.random() < .75
        rows.append((ref_idx, i, link_ts, sig_ts, household, same_pf, quick, kind))
ref = pd.DataFrame(rows, columns=["ref_idx", "fr_idx", "link_ts", "signup_ts", "same_device", "same_pf", "new_share", "kind"])
ref = ref.drop_duplicates("fr_idx").sort_values("signup_ts").reset_index(drop=True)
ri, fi = ref["ref_idx"].values, ref["fr_idx"].values
fr_device = np.where(ref["same_device"], device_id[ri], device_id[fi])
fr_pf = np.where(ref["same_pf"], fingerprint[ri], fingerprint[fi])
paid = cust["paid_amount_eur"].values[fi]
reward = np.minimum(REWARD_RATE * paid, REWARD_CAP_EUR).round(2)
status = np.where(refunded[fi], "voided (refunded)",
                  np.where(order_ns[fi] + HOLD_DAYS * DAY_NS > END, "pending", "paid"))
referrals = pd.DataFrame({
    "referral_id": np.arange(1, len(ref) + 1) + 900_000,
    "referrer_user_id": cust["user_id"].values[ri], "referee_user_id": cust["user_id"].values[fi],
    "referee_order_id": cust["order_id"].values[fi],
    "link_shared_ts": pd.to_datetime(ref["link_ts"].values), "signup_ts": pd.to_datetime(ref["signup_ts"].values),
    "purchase_ts": pd.to_datetime(order_ns[fi]), "country": country[fi],
    "referrer_device_id": device_id[ri], "referee_device_id": fr_device,
    "referrer_payment_fingerprint": fingerprint[ri], "referee_payment_fingerprint": fr_pf,
    "reward_rate": REWARD_RATE, "friend_discount_rate": FRIEND_DISCOUNT,
    "reward_eur": reward, "reward_status": status})
# extra share event right before a quick signup (same link, shared in a chat)
ns_ = ref["new_share"].values
add_events(ri[ns_], "referral_link_shared", "Referral", ref["link_ts"].values[ns_], jprop("channel", np.full(ns_.sum(), "whatsapp")))
add_events(fi, "referral_signup", "Referral", ref["signup_ts"].values, jprop("referral_id", referrals["referral_id"].values), dev=fr_device)
add_events(fi, "referral_purchase", "Referral", order_ns[fi], jprop("referral_id", referrals["referral_id"].values), dev=fr_device)

# ================================================================== 7. write
events = pd.concat(event_frames, ignore_index=True).sort_values(["event_time", "user_id"]).reset_index(drop=True)
events.insert(0, "event_id", np.arange(1, len(events) + 1))
for c in ("event_name", "product", "platform", "country"):
    events[c] = events[c].astype("category")
events.to_parquet(CLEAN / "sim_product_events.parquet", index=False)
for name, df in (("experiments", experiments), ("referrals", referrals)):
    df.to_parquet(CLEAN / f"sim_{name}.parquet", index=False)
    df.to_csv(CLEAN / f"sim_{name}.csv", index=False)
print(f"sim_product_events {len(events):>10,} rows")
print(f"sim_experiments    {len(experiments):>10,} rows")
print(f"sim_referrals      {len(referrals):>10,} rows")

# ================================================================== 8. plausibility checks
print("\n--- product plausibility (see data/ASSUMPTIONS.md) ---")
print("events by name:", events["event_name"].value_counts().to_dict())
print(f"Reach users: {nR:,} ({nR / N:.1%} of customers); new customers who start: {new[R].sum() / new.sum():.1%}")
print(f"funnel: template {tmpl.mean():.1%}, contacts {cont.mean():.1%}, first campaign {send.mean():.1%}, within 7 days {act7.mean():.1%}")
c, t = in_test & ~treat, treat
print(f"A/B: control {c.sum():,} / treatment {t.sum():,}; activation 7d {act7[c].mean():.1%} vs {act7[t].mean():.1%}; "
      f"true effect built in {true_effect * 100:+.1f} pts")
ok_day = in_test & ~((s0 >= BUG_DAY) & (s0 < BUG_DAY + DAY_NS))
y1, y0 = act7_if
print(f"A/B without the bug day: true effect {(y1[ok_day].mean() - y0[ok_day].mean()) * 100:+.1f} pts; chance imbalance "
      f"(treatment minus control, both without the feature) {(y0[ok_day & treat].mean() - y0[ok_day & ~treat].mean()) * 100:+.1f} pts")
print(f"newsletter day starts: {((s0 >= NEWSLETTER) & (s0 < NEWSLETTER + DAY_NS)).sum():,}; bug-day mobile users sent to control: {bug.sum():,}")
d30_obs = d30(alive)
print(f"day-30 retention: aha {d30_obs[act7 & mature].mean():.1%} vs no aha {d30_obs[~act7 & mature].mean():.1%}; built-in causal part {causal_gap:.1%}")
print(f"upgrades: {upg.sum():,} ({upg[send].mean():.1%} of users who sent a campaign)")
print(f"Mail users: {nM:,}; AI adopters {adopter.mean():.1%}")
print(f"referrals: {len(referrals):,}, planted self-referrals {(ref['kind'] == 'self').sum():,}; rewards EUR {reward.sum():,.0f}")
