"""Generate the Power BI report pages (PBIR format) for powerbi/HostingerAttribution.Report.

Same page grammar as the Rovio case study: title = conclusion, grey subtitle, data tag top right,
4 to 6 visuals, grey footer with sources. Pages 1-5 = marketing part, pages 6-9 = product part, then a data-model annex. Every number written in a title or text box is read from
data/output (SQL and notebook results), never typed by hand.

Usage:  python src/build_report_pages.py
Close Power BI Desktop first (or let it reload): every page is rewritten from this script.
"""
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "output"
REPORT = ROOT / "powerbi" / "HostingerAttribution.Report"
PAGES = REPORT / "definition" / "pages"
VC_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json"
PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json"
M = "_Measures"

# ink & palette (same as the Rovio and PlayersBest reports)
INK, INK2, MUTED = "#0B0B0B", "#52514E", "#898781"
BLUE, GREY, LIGHT = "#2A78D6", "#B4B2A9", "#D3D1C7"
SEQ = {"100": "#CDE2FB", "250": "#86B6EF", "350": "#5598E7", "450": "#2A78D6", "650": "#104281"}
NEUTRAL, RED, RED_TINT, BLUE_TINT = "#F0EFEC", "#D03B3B", "#F4C7C6", "#B7D3F6"
AUTHOR = "Independent case study for Hostinger's Marketing and Product Data Analyst roles · Not affiliated with Hostinger, no Hostinger data"
SRC_SIM = "SIMULATED data (seed 42), calibrated on public hostinger.com prices, refund and affiliate terms (data/SOURCES.md) - not Hostinger data"
SRC_PROD = "SIMULATED product events (seed 42), same simulated customers, calibrated on public hostinger.com terms (data/SOURCES.md) - not Hostinger data"

# ---------------------------------------------------------------- numbers from the analysis
H = pd.read_csv(OUT / "headline.csv", index_col=0)["value"]
def h(key): return float(H[key])
geo = pd.read_csv(OUT / "geo_result.csv").set_index("metric")
quality = pd.read_csv(OUT / "channel_quality.csv").set_index("channel")
creators = pd.read_csv(OUT / "creator_scorecard.csv")
halo = pd.read_csv(OUT / "influencer_halo.csv").set_index("metric")["value"]
realloc = pd.read_csv(OUT / "reallocation.csv")
inc_cost = pd.read_csv(OUT / "incremental_cost.csv").set_index("channel")
spend = pd.read_csv(ROOT / "data" / "clean" / "sim_spend.csv")
credits = pd.read_csv(OUT / "attribution_credits.csv")
orders = pd.read_csv(OUT / "order_value.csv", usecols=["order_id", "expected_value_12m"])
mk = credits[credits.model == "Markov (data-driven)"].merge(orders, on="order_id")
mk_orders = mk.groupby("channel").credit.sum()
mk_value = (mk.credit * mk.expected_value_12m).groupby(mk.channel).sum()
ch_spend = spend.groupby("channel").spend_eur.sum()

N_ORDERS = len(orders)
tp_users = pd.read_parquet(ROOT / "data" / "clean" / "sim_touchpoints.parquet", columns=["user_id"]).user_id
N_TOUCH, N_VISITORS = len(tp_users), tp_users.nunique()
NB_SPEND_SHARE = ch_spend["PPC Non-brand"] / ch_spend.sum()
NB_ROAS12 = mk_value["PPC Non-brand"] / ch_spend["PPC Non-brand"]
NB_CAC = ch_spend["PPC Non-brand"] / mk_orders["PPC Non-brand"]
SEO_ROAS12 = mk_value["SEO"] / ch_spend["SEO"]
INCR = geo.loc["Brand ads incrementality (clicks)"]
RECAP = geo.loc["Ad clicks recaptured by the organic result"]
LEAKED = int(creators.leaked_code_orders.sum())
LEAK_SHARE = LEAKED / creators.code_orders.sum()
HALO = halo["Halo multiplier"] - 1
MOVED = realloc.loc[realloc.move.str.contains("Creators"), "budget_change_eur_12m"].iloc[0]
NET = realloc.loc[realloc.move.str.startswith("Net"), "incremental_orders_12m"].iloc[0]

# product part (sql/08-11 and notebooks/product_analysis.ipynb)
P = pd.read_csv(OUT / "product_headline.csv", index_col=0)["value"]
def ph(key): return float(P[key])
N_REACH = len(pd.read_csv(OUT / "reach_users.csv", usecols=["user_id"]))
N_EVENTS = int(pd.read_csv(OUT / "product_daily.csv", usecols=["events"]).events.sum())
N_REF = int(ph("referrals"))

N_MEASURES = (ROOT / "powerbi" / "HostingerAttribution.SemanticModel" / "definition" / "tables" / "_Measures.tmdl").read_text(encoding="utf-8").count("	measure ")

def pct(x, d=0): return f"{100 * x:.{d}f}%"
def eur(x): return f"€{x:,.0f}"
def eur_k(x): return f"€{x / 1000:,.0f}k"


# ---------------------------------------------------------------- expression helpers
def raw(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, int):
        s = f"{v}L"
    elif isinstance(v, float):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"Literal": {"Value": s}}

def lit(v):
    if isinstance(v, int) and not isinstance(v, bool):
        v = float(v)
    return {"expr": raw(v)}

def color(hexv):
    return {"solid": {"color": lit(hexv)}}

def col(table, column):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}}

def meas(name):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": M}}, "Property": name}}

def agg(table, column, fn=0):          # 0 = sum, 1 = average
    return {"Aggregation": {"Expression": col(table, column), "Function": fn}}

def qref(field):
    if "Column" in field:
        c = field["Column"]
        return f'{c["Expression"]["SourceRef"]["Entity"]}.{c["Property"]}'
    if "Measure" in field:
        return f'{M}.{field["Measure"]["Property"]}'
    c = field["Aggregation"]["Expression"]["Column"]
    fn = "Sum" if field["Aggregation"]["Function"] == 0 else "Avg"
    return f'{fn}({c["Expression"]["SourceRef"]["Entity"]}.{c["Property"]})'

def proj(field, label=None):
    p = {"field": field, "queryRef": qref(field)}
    if "Column" in field:
        p["nativeQueryRef"] = field["Column"]["Property"]
    elif "Measure" in field:
        p["nativeQueryRef"] = field["Measure"]["Property"]
    else:
        p["nativeQueryRef"] = field["Aggregation"]["Expression"]["Column"]["Property"]
        p["displayName"] = field["Aggregation"]["Expression"]["Column"]["Property"]
    if label:
        p["displayName"] = label
    return p

def C(t, c): return col(t, c)
def Ms(*names): return [meas(n) for n in names]

def series_color(field, hexv):
    return {"properties": {"fill": color(hexv)}, "selector": {"metadata": qref(field)}}

def value_color(table, column, value, hexv):
    """Colour of one category / series value (e.g. the 'Markov' series)."""
    return {"properties": {"fill": color(hexv)},
            "selector": {"data": [{"scopeId": {"Comparison": {"ComparisonKind": 0, "Left": col(table, column),
                                                               "Right": raw(value)}}}]}}

def ref_line(value, label, hexv=INK2, selector_id="1"):
    v = {"expr": value} if isinstance(value, dict) else lit(value)
    return {"properties": {"show": lit(True), "value": v, "displayName": lit(label), "lineColor": color(hexv),
                           "style": lit("dashed"), "dataLabelShow": lit(True), "dataLabelColor": color(hexv)},
            "selector": {"id": selector_id}}

def bg_rule(field, lo, hi, mid=None, mid_value=None):
    """Background-colour scale (conditional formatting) on a table/matrix value column."""
    rule = {"min": {"color": raw(lo)}, "max": {"color": raw(hi)},
            "nullColoringStrategy": {"strategy": raw("asZero")}}
    key = "linearGradient2"
    if mid:
        key = "linearGradient3"
        rule["mid"] = {"color": raw(mid)}
        if mid_value is not None:
            rule["mid"]["value"] = raw(float(mid_value))
    return {"properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {"Input": field, "FillRule": {key: rule}}}}}}},
            "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": qref(field)}}

def table_style(extra_values=(), matrix=False, font=12):
    """Readable table: 12pt text, no misleading total row/column."""
    fs = {"properties": {"fontSize": lit(font)}}
    objs = {"values": [fs, *extra_values], "columnHeaders": [{"properties": {"fontSize": lit(font), "fontColor": color(INK2)}}]}
    if matrix:
        objs["rowHeaders"] = [fs]
        objs["subTotals"] = [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}]
    else:
        objs["total"] = [{"properties": {"totals": lit(False)}}]
    return objs

def no_legend(extra=None):
    o = {"legend": [{"properties": {"show": lit(False)}}]}
    o.update(extra or {})
    return o

def data_labels(fmt_color=INK):
    return [{"properties": {"show": lit(True), "color": color(fmt_color)}}]

def flt(table, column, values, negate=False):
    """Visual-level filter: keep (or exclude) a list of values."""
    return (table, column, values, negate)

def slicer_selection(table, column, value):
    return {"filter": {"filter": {"Version": 2, "From": [{"Name": "s", "Entity": table, "Type": 0}],
                                  "Where": [{"Condition": {"In": {
                                      "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": column}}],
                                      "Values": [[raw(value)]]}}}]}}}


# ---------------------------------------------------------------- page / visual builders
class Page:
    def __init__(self, pid, name):
        self.pid, self.name, self.visuals, self.interactions, self.n = pid, name, [], [], 0

    def _add(self, vid, x, y, w, h, visual):
        self.n += 1
        self.visuals.append({"$schema": VC_SCHEMA, "name": vid,
                             "position": {"x": round(x), "y": round(y), "z": self.n * 1000,
                                          "height": round(h), "width": round(w), "tabOrder": self.n * 1000},
                             "visual": visual})
        return vid

    def chart(self, vid, vtype, x, y, w, h, roles, title=None, objects=None, labels=None, sort=None, filters=()):
        labels = labels or {}
        visual = {"visualType": vtype,
                  "query": {"queryState": {r: {"projections": [proj(f, labels.get(qref(f))) for f in fs]}
                                           for r, fs in roles.items() if fs}},
                  "drillFilterOtherVisuals": True}
        if sort:
            field, direction = sort
            visual["query"]["sortDefinition"] = {"sort": [{"field": field, "direction": direction}],
                                                 "isDefaultSort": False}
        if objects:
            visual["objects"] = objects
        vco = {"subTitle": [{"properties": {"show": lit(False)}}]}
        vco["title"] = [{"properties": {"show": lit(bool(title)), **({"text": lit(title)} if title else {})}}]
        visual["visualContainerObjects"] = vco
        vid = self._add(vid, x, y, w, h, visual)
        fl = []
        for i, (table, column, values, negate) in enumerate(filters):
            cond = {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                           "Values": [[raw(v)] for v in values]}}
            if negate:
                cond = {"Not": {"Expression": cond}}
            fl.append({"name": f"visualFilter{i}", "type": "Categorical", "field": col(table, column),
                       "filter": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                                  "Where": [{"Condition": cond}]}})
        if fl:
            self.visuals[-1]["filterConfig"] = {"filters": fl}
        return vid

    def text(self, vid, x, y, w, h, paragraphs, boxed=False):
        """paragraphs: list of paragraphs; each paragraph = list of (text, size, colour, bold) runs."""
        paras = [{"textRuns": [{"value": t, "textStyle": {"fontSize": f"{s}pt", "color": c,
                                                         **({"fontWeight": "bold"} if b else {})}}
                               for t, s, c, b in runs]} for runs in paragraphs]
        visual = {"visualType": "textbox",
                  "objects": {"general": [{"properties": {"paragraphs": paras}}]},
                  "visualContainerObjects": {"background": [{"properties": {"show": lit(boxed)}}],
                                             "border": [{"properties": {"show": lit(boxed)}}],
                                             **({"padding": [{"properties": {"top": lit(16), "bottom": lit(16),
                                                                             "left": lit(20), "right": lit(20)}}]}
                                                if boxed else {})}}
        return self._add(vid, x, y, w, h, visual)

    def header(self, title, conclusion, tag):
        self.text("title", 32, 20, 1500, 56, [[(title, 24, INK, True)]])
        self.text("tag", 1540, 28, 348, 40, [[(tag, 10, INK2, True)]])
        self.text("conclusion", 32, 76, 1856, 64, [[(conclusion, 13, INK2, False)]])

    def footer(self, source):
        self.text("footer", 32, 1040, 1856, 32, [[(source + "   ·   " + AUTHOR, 9, MUTED, False)]])

    def slicer(self, vid, x, y, w, h, field, title, dropdown=True, single=False, selected=None):
        objs = {"header": [{"properties": {"show": lit(False)}}]}
        if dropdown:
            objs["data"] = [{"properties": {"mode": lit("Dropdown")}}]
        if single:
            objs["selection"] = [{"properties": {"singleSelect": lit(True), "strictSingleSelect": lit(True)}}]
        if selected:
            objs["general"] = [{"properties": slicer_selection(*selected)}]
        return self.chart(vid, "slicer", x, y, w, h, {"Values": [field]}, title, objs)

    def card(self, vid, x, y, w, h, measure, title, filters=()):
        return self.chart(vid, "card", x, y, w, h, {"Values": [meas(measure)]}, title,
                          {"labels": [{"properties": {"color": color(INK), "fontSize": lit(28)}}],
                           "categoryLabels": [{"properties": {"show": lit(False)}}]}, filters=filters)

    def write(self):
        d = PAGES / self.pid
        if d.exists():
            shutil.rmtree(d)
        (d / "visuals").mkdir(parents=True)
        page = {"$schema": PAGE_SCHEMA, "name": self.pid, "displayName": self.name,
                "displayOption": "FitToPage", "height": 1080, "width": 1920}
        if self.interactions:
            page["visualInteractions"] = self.interactions
        (d / "page.json").write_text(json.dumps(page, indent=2, ensure_ascii=False), encoding="utf-8")
        for v in self.visuals:
            vd = d / "visuals" / v["name"]
            vd.mkdir()
            (vd / "visual.json").write_text(json.dumps(v, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- layout grid
L, R, TOP, BOT, GAP = 32, 1888, 156, 1028, 24
W = R - L

def cols(n, x0=L, x1=R):
    w = (x1 - x0 - (n - 1) * GAP) / n
    return [(x0 + i * (w + GAP), w) for i in range(n)]

def kpi_row(p, items, y=TOP, h=120, x0=L, x1=R):
    for (x, w), (m, t) in zip(cols(len(items), x0, x1), items):
        p.card("kpi_" + "".join(ch for ch in m if ch.isalnum())[:30], x, y, w, h, m, t)
    return y + h + GAP

NO_TRACK = flt("Channel", "channel", ["Unattributed"], negate=True)
SPENDING = flt("Channel", "channel", ["Direct", "Unattributed"], negate=True)
ACQ = flt("Channel", "channel", ["Email", "Unattributed"], negate=True)
MODEL_COLORS = {"Last click": INK, "First click": SEQ["250"], "Linear": LIGHT, "Time decay": GREY,
                "Position 40/20/40": MUTED, "Markov (data-driven)": BLUE}
pages = []

# ======================= Page 0 - Overview =======================
p = Page("a0000000000000000000", "Overview")
p.text("title", 32, 20, 1500, 56, [[("Hostinger marketing & product analytics: profitable channels, product adoption and experiments", 24, INK, True)]])
p.text("tag", 1540, 28, 348, 40, [[("OVERVIEW", 10, INK2, True)]])
p.text("conclusion", 32, 76, 1856, 64, [[(
    "Independent case study for Hostinger's Marketing and Product Data Analyst roles: seven questions for the Affiliates, Influencers, PPC, SEO, "
    "Product Marketing and product teams (Reach, Mail, referral programme), worked end to end with SQL (DuckDB), Python and Power BI "
    "on SIMULATED data calibrated on hostinger.com.", 13, INK2, False)]])
heroes = [
    (f"{pct(h('coupon_share_last_click'))} → {pct(h('coupon_share_markov'))}",
     f"of sales credited to coupon sites by last click vs data-driven attribution; {pct(h('coupon_cart_already'))} of their buyers already had a cart",
     "SIMULATED · PAGES 2-3"),
    (f"+{pct(HALO)}",
     f"more creator sales than links and codes show (brand searches after videos); {LEAKED:,} code uses came from leaks",
     "SIMULATED · PAGE 3"),
    (f"{eur(quality.loc['SEO', 'ltv_24m'])} vs {eur(quality.loc['PPC Non-brand', 'ltv_24m'])}",
     "net value of an SEO customer vs a PPC non-brand customer after 24 months (refunds and renewals included)",
     "SIMULATED · PAGE 4"),
    (pct(INCR["value"]),
     f"of brand-ad clicks are incremental: {pct(RECAP['value'])} come back through the organic result when ads are off (geo test)",
     "SIMULATED · PAGE 5"),
]
hh = 210
for i, ((x, w), (num, txt, tag)) in enumerate(zip(cols(4), heroes)):
    p.text(f"hero{i+1}", x, TOP, w, hh, [[(tag, 10, INK2, True)], [(num, 40, INK, True)], [(txt, 15, INK2, False)]],
           boxed=True)
y2 = TOP + hh + GAP
(x1, w1), (x2, w2) = cols(2)
BH = 430
p.text("questions", x1, y2, w1, BH, [
    [("Business questions", 20, INK, True), ("   marketing & product analytics", 15, INK2, False)],
    [("", 6, INK, False)],
    [("1 · Efficiency   ", 14, BLUE, True), ("What does a customer cost per channel, and which channel pays back?", 14, INK, False)],
    [("2 · Attribution   ", 14, BLUE, True), ("What changes when the attribution model changes?", 14, INK, False)],
    [("3 · Partners   ", 14, BLUE, True), ("Which creators and affiliates are really worth their price?", 14, INK, False)],
    [("4 · Quality   ", 14, BLUE, True), ("Do the customers of each channel stay and renew?", 14, INK, False)],
    [("5 · Budget   ", 14, BLUE, True), ("Does spend create sales, and where should the next euro go?", 14, INK, False)],
    [("6 · Adoption   ", 14, BLUE, True), ("Where do new Reach users drop out, and what is a successful adoption? (pages 6-7)", 14, INK, False)],
    [("7 · Experiments   ", 14, BLUE, True), ("Does the AI-prefilled campaign work, and is the referral reward worth it? (pages 8-9)", 14, INK, False)],
    [("", 6, INK, False)],
    [("Marketing: ", 13, INK, True),
     (f"steer budget on 12-month net value and incrementality, not last-click orders. Trim PPC non-brand by 20%, stop paying "
      f"coupon commission when the cart was already started, move the {eur_k(MOVED)} to creators "
      f"({NET:+,.0f} orders a year at the same budget).", 13, INK2, False)],
    [("Product: ", 13, INK, True),
     ("fix the contacts-import step, ship the AI-prefilled first campaign with a holdout, block self-referrals before touching the reward rate.", 13, INK2, False)],
], boxed=True)
p.text("data", x2, y2, w2, BH, [
    [("Data & methods", 20, INK, True)],
    [("", 6, INK, False)],
    [("SIMULATED   ", 12, INK2, True), (f"30 months, 6 countries, {N_VISITORS / 1e6:.1f}M visitors, {N_TOUCH / 1e6:.1f}M touchpoints, {N_ORDERS:,} orders; "
                                       f"for the same customers {N_EVENTS / 1e6:.1f}M product events (Amplitude format), {N_REACH:,} Reach users, "
                                       f"one A/B test, {N_REF:,} referrals (Python, seed 42). Not Hostinger data.", 13, INK, False)],
    [("PUBLIC   ", 12, INK2, True), ("Hostinger prices, 30-day money-back guarantee, affiliate terms (10 Nov 2026); Reach plans and referral terms (13 Nov 2026).", 13, INK, False)],
    [("SQL   ", 12, INK2, True), ("paths, 5 attribution models, censoring-safe customer value and retention, ordered funnels, test checks (window functions).", 13, INK, False)],
    [("Python   ", 12, INK2, True), ("Markov, geo-test and rollout difference-in-differences, A/B test (power, sample-ratio check, z-test, bootstrap), scenarios.", 13, INK, False)],
    [("Power BI   ", 12, INK2, True), (f"star schema shared by both parts, {N_MEASURES} DAX measures, an attribution-model switch.", 13, INK, False)],
    [("AI   ", 12, INK2, True), ("AI-assisted workflow: I used Claude, mainly to write scripts faster. I drove the project: I defined the questions, "
                               "chose and validated the data sources, made the analytical decisions and checked every result.", 13, INK2, False)],
], boxed=True)
y3 = y2 + BH + GAP
p.text("howto", L, y3, W, BOT - y3, [
    [("Hostinger context  ", 14, INK, True), ("public facts used to calibrate the simulation, hostinger.com", 12, INK2, False)],
    [("Customers  ", 12, INK2, True), ("5M+ in 150+ countries.   ", 13, INK, False),
     ("Plans  ", 12, INK2, True), ("paid upfront; Premium $1.99/mo for 48 months, renews at $10.99/mo.   ", 13, INK, False),
     ("Refunds  ", 12, INK2, True), ("30-day money-back guarantee.   ", 13, INK, False),
     ("Affiliates  ", 12, INK2, True), ("from 40% commission, 30-day cookie, none on 1-month plans or renewals.", 13, INK, False)],
    [("Reach  ", 12, INK2, True), ("AI e-mail marketing, Starter plan up to 100 recipients.   ", 13, INK, False),
     ("Mail  ", 12, INK2, True), ("business e-mail with AI replies.   ", 13, INK, False),
     ("Referrals  ", 12, INK2, True), ("referrer earns 20% of the friend's purchase, the friend gets 20% off, reward paid after 45 days.", 13, INK, False)],
    [("How to read  ", 12, INK2, True), ("titles state the conclusion · SIMULATED marks generated data · dashed lines mark a threshold · "
                                        "SQL, notebooks and Power BI project in the repository.", 13, INK, False)],
], boxed=True)
p.footer("Sources listed in data/SOURCES.md, assumptions in data/ASSUMPTIONS.md")
pages.append(p)

# ======================= Page 1 - Channel efficiency =======================
p = Page("a1000000000000000000", "1 · Channel efficiency")
p.header(f"Half the budget goes to PPC non-brand, which returns €{NB_ROAS12:.2f} per euro within 12 months",
         f"Under data-driven attribution PPC non-brand takes {pct(NB_SPEND_SHARE)} of spend at {eur(NB_CAC)} per order and does not pay back "
         f"within a year; SEO returns €{SEO_ROAS12:.1f}. Value = first payment net of refunds (Hostinger's 30-day guarantee) plus renewals, expected at 12 months. "
         "Change the attribution model (top right) to see how the ranking moves.",
         "SIMULATED DATA")
sw = 360
y = kpi_row(p, [("Total Spend", "Marketing spend, 30 months"), ("Credited Orders", "Orders"),
                ("CAC", "Blended cost per order"), ("ROAS 12m", "Blended 12-month ROAS")], x1=R - sw - GAP)
p.slicer("modelSlicer", R - sw, TOP, sw, 120, C("Attribution Model", "model"), "Attribution model",
         single=True, selected=("Attribution Model", "model", "Markov (data-driven)"))
h1 = 380
(xa, wa), (xb, wb) = cols(2)
r30, r12 = meas("ROAS 30d"), meas("ROAS 12m")
p.chart("roasByChannel", "clusteredBarChart", xa, y, wa, h1,
        {"Category": [C("Channel", "channel")], "Y": [r30, r12]},
        "ROAS by channel at 30 days and 12 months (dashed = break-even)",
        {"dataPoint": [series_color(r30, SEQ["250"]), series_color(r12, BLUE)],
         "y1AxisReferenceLine": [ref_line(1.0, "Break-even 100%")]},
        labels={qref(r30): "ROAS 30 days", qref(r12): "ROAS 12 months"}, sort=(r12, "Descending"), filters=[SPENDING])
p.chart("cacVsValue", "scatterChart", xb, y, wb, h1,
        {"Category": [C("Channel", "channel")], "X": [meas("CAC")], "Y": [meas("Value per Order 12m")]},
        "Cost per order vs 12-month value per order, EUR (red = costs more than it brings in)",
        {"dataPoint": [{"properties": {"fill": color(BLUE)}}],
         "categoryLabels": [{"properties": {"show": lit(True), "color": color(INK2)}}],
         "markers": [{"properties": {"markerSize": lit(8)}}],
         "plotAreaShading": [{"properties": {"show": lit(True), "displayName": lit("Break-even diagonal"),
                                              "upperShadingColor": color(BLUE_TINT),
                                              "lowerShadingColor": color(RED_TINT), "transparency": lit(40)}}],
         "categoryAxis": [{"properties": {"start": lit(0), "end": lit(240)}}],
         "valueAxis": [{"properties": {"start": lit(0), "end": lit(240)}}]},
        labels={"_Measures.CAC": "Cost per order (EUR)", "_Measures.Value per Order 12m": "12-month value per order (EUR)"},
        filters=[SPENDING])
y += h1 + GAP
tbl = [C("Channel", "channel")] + Ms("Total Spend", "Spend Share", "Credited Orders", "CAC", "Value per Order 12m", "ROAS 12m")
p.chart("scorecard", "tableEx", xa, y, wa, BOT - y, {"Values": tbl},
        "Channel scorecard under the selected model (red = below break-even)",
        table_style([bg_rule(meas("ROAS 12m"), RED_TINT, BLUE_TINT, NEUTRAL, 1)]),
        labels={"Channel.channel": "Channel", "_Measures.Credited Orders": "Orders", "_Measures.Total Spend": "Spend",
                "_Measures.Value per Order 12m": "Value / order 12m"},
        sort=(meas("Total Spend"), "Descending"), filters=[SPENDING])
p.chart("spendByMonth", "columnChart", xb, y, wb, BOT - y,
        {"Category": [C("Date", "Month")], "Y": [meas("Total Spend")], "Series": [C("Channel", "channel")]},
        "Spend by month and channel, EUR (affiliate and CPA creator fees follow sales)")
pages.append(p)
p.footer(SRC_SIM)

# ======================= Page 2 - Attribution =======================
p = Page("a2000000000000000000", "2 · Attribution")
p.header(f"Last click gives coupon sites {pct(h('coupon_share_last_click'))} of sales; data-driven attribution halves it",
         f"Same {N_ORDERS:,} orders, six ways to split the credit. Coupon sites and direct visits sit at the end of journeys, so last click "
         "flatters them; PPC non-brand and SEO start journeys. No click model sees a video that was watched but not clicked: "
         "influencers get 2-6% of credit under every model (page 3 measures them another way).",
         "SIMULATED DATA")
lw = W * 0.58
cs = meas("Credit Share by Model")
p.chart("creditByModel", "clusteredBarChart", L, TOP, lw, BOT - TOP,
        {"Category": [C("Channel", "channel")], "Y": [cs], "Series": [C("Attribution Model", "model")]},
        "Share of orders credited to each channel, by attribution model",
        {"dataPoint": [value_color("Attribution Model", "model", m, c) for m, c in MODEL_COLORS.items()],
         "legend": [{"properties": {"show": lit(True), "position": lit("Top")}}]},
        labels={qref(cs): "Credit share"}, filters=[NO_TRACK])
rx = L + lw + GAP
th = 440
p.chart("topPaths", "tableEx", rx, TOP, R - rx, th,
        {"Values": [C("Top Paths", "rank"), C("Top Paths", "path"), C("Top Paths", "orders"),
                    C("Top Paths", "share_of_orders"), C("Top Paths", "avg_days_to_convert")]},
        "Most frequent conversion paths (30-day window, repeats collapsed)", table_style(font=11),
        labels={"Top Paths.rank": "#", "Top Paths.path": "Path", "Top Paths.orders": "Orders",
                "Top Paths.share_of_orders": "Share", "Top Paths.avg_days_to_convert": "Days to buy"},
        sort=(C("Top Paths", "rank"), "Ascending"))
yb = TOP + th + GAP
(xc, wc), (xd, wd) = cols(2, rx, R)
p.chart("pathLength", "clusteredColumnChart", xc, yb, wc, BOT - yb,
        {"Category": [C("Path Length", "touchpoints")], "Y": [agg("Path Length", "share_of_orders")]},
        "Touchpoints before buying (share of orders)",
        no_legend({"dataPoint": [{"properties": {"fill": color(BLUE)}}], "labels": data_labels()}),
        labels={"Sum(Path Length.share_of_orders)": "Share of orders"})
p.chart("daysToConvert", "clusteredColumnChart", xd, yb, wd, BOT - yb,
        {"Category": [C("Days To Convert", "days_to_convert")], "Y": [agg("Days To Convert", "share_of_orders")]},
        "Time from first touch to purchase",
        no_legend({"dataPoint": [{"properties": {"fill": color(BLUE)}}], "labels": data_labels()}),
        labels={"Sum(Days To Convert.share_of_orders)": "Share of orders"})
p.footer(SRC_SIM + "   ·   Markov = removal effect on 1.3M journeys (buyers and non-buyers)")
pages.append(p)

# ======================= Page 3 - Influencers & affiliates =======================
p = Page("a3000000000000000000", "3 · Influencers & affiliates")
p.header(f"Creators drive {pct(HALO)} more sales than links and codes show, but 3 leaked codes inflate their numbers",
         f"Brand searches rise {pct(halo['Brand-search lift, 14 days after a video'])} in the 2 weeks after a video. "
         f"{LEAKED:,} creator-code orders ({pct(LEAK_SHARE)}) came through coupon sites with no recent video: leaked codes, "
         f"paid twice (Hostinger's 40%+ affiliate commission + creator fee). On coupon sites, {pct(h('coupon_cart_already'))} of buyers had already started a cart.",
         "SIMULATED DATA")
k4 = cols(4)
for (x, w), (m, t) in zip(k4[:3], [("Creator Cost", "Creator fees, 30 months"), ("Genuine Creator Orders", "Orders by link or genuine code"),
                                    ("Leaked Code Orders", "Code orders from leaks")]):
    p.card("kpi_" + m.replace(" ", ""), x, TOP, w, 120, m, t)
p.card("kpi_CartAlready", k4[3][0], TOP, k4[3][1], 120, "Cart Already Started Share",
       "Coupon-site buyers with a cart already started", filters=[flt("Affiliate", "type", ["coupon"])])
y = TOP + 120 + GAP
lw = W * 0.56
creator_cols = ["creator_id", "platform", "fee_model", "videos", "cost_eur", "link_orders", "code_orders",
                "leaked_share_of_code", "refund_rate_30d", "cost_per_genuine_order", "roi_12m"]
p.chart("creatorTable", "tableEx", L, y, lw, BOT - y - 250 - GAP,
        {"Values": [C("Creator", c) for c in creator_cols]},
        "Creator scorecard (red = leaked codes / negative 12-month ROI)",
        table_style([bg_rule(C("Creator", "leaked_share_of_code"), "#FCFCFB", RED_TINT),
                     bg_rule(C("Creator", "roi_12m"), RED_TINT, BLUE_TINT, NEUTRAL, 0)], font=11),
        labels={"Creator.creator_id": "Creator", "Creator.platform": "Platform", "Creator.fee_model": "Fee",
                "Creator.videos": "Videos", "Creator.cost_eur": "Cost", "Creator.link_orders": "Link orders",
                "Creator.code_orders": "Code orders", "Creator.leaked_share_of_code": "Leaked",
                "Creator.refund_rate_30d": "Refunds", "Creator.cost_per_genuine_order": "Cost / genuine order",
                "Creator.roi_12m": "ROI 12m"},
        sort=(C("Creator", "cost_eur"), "Descending"))
ya = BOT - 250
p.chart("affiliateTypes", "tableEx", L, ya, lw, 250,
        {"Values": [C("Affiliate", "type")] + Ms("Affiliate Orders", "Affiliate Commission", "Affiliate Refund Rate", "Cart Already Started Share")},
        "Affiliates by type (orders where the affiliate is the last click = what commission is paid on)",
        table_style([bg_rule(meas("Cart Already Started Share"), "#FCFCFB", RED_TINT)]),
        labels={"Affiliate.type": "Type", "_Measures.Affiliate Orders": "Orders", "_Measures.Affiliate Commission": "Commission",
                "_Measures.Affiliate Refund Rate": "Refunds", "_Measures.Cart Already Started Share": "Cart already started"},
        sort=(meas("Affiliate Commission"), "Descending"))
rx = L + lw + GAP
rh = (BOT - y - GAP) / 2
leak_cr = creators.sort_values("leaked_code_orders", ascending=False).creator_id.iloc[0]
vids, codes, leaks = meas("Videos Published"), meas("Weekly Genuine Code Orders"), meas("Weekly Leaked Code Orders")
p.chart("leakChart", "lineClusteredColumnComboChart", rx, y, R - rx, rh,
        {"Category": [C("Code Usage", "week")], "Y": [vids], "Y2": [codes, leaks]},
        f"{leak_cr}: weekly genuine code uses (black) and leaked uses (red); columns = videos published",
        {"dataPoint": [series_color(vids, GREY), series_color(codes, INK), series_color(leaks, RED)]},
        labels={qref(vids): "Videos", qref(codes): "Genuine code orders", qref(leaks): "Leaked code orders"},
        filters=[flt("Code Usage", "creator_id", [leak_cr])])
p.chart("eventStudy", "lineChart", rx, y + rh + GAP, R - rx, rh,
        {"Category": [C("Video Event Study", "day")], "Y": [meas("Brand Search Index")]},
        "Brand searches around a sponsored video, in the creator's country (100 = 2 weeks before; day 0 = video)",
        no_legend({"dataPoint": [{"properties": {"fill": color(BLUE)}}],
                   "y1AxisReferenceLine": [ref_line(100.0, "Baseline")],
                   "valueAxis": [{"properties": {"start": lit(80)}}]}),
        labels={"_Measures.Brand Search Index": "Brand searches (index)"})
p.footer(SRC_SIM + "   ·   Leak = creator code used after a coupon-site click with no video in the previous 21 days")
pages.append(p)

# ======================= Page 4 - Customer quality =======================
p = Page("a4000000000000000000", "4 · Customer quality")
q = quality
p.header(f"An SEO customer is worth {eur(q.loc['SEO', 'ltv_24m'])} after 24 months, a PPC non-brand customer {eur(q.loc['PPC Non-brand', 'ltv_24m'])}",
         f"Hostinger plans are prepaid at an intro price and renew higher, with a 30-day money-back guarantee, so refunds, plan length and renewals "
         f"drive value. PPC non-brand buyers refund {pct(q.loc['PPC Non-brand', 'refund_rate_30d'])} and choose a 1-month plan "
         f"{pct(q.loc['PPC Non-brand', 'share_plan_1m'])} of the time; SEO buyers refund {pct(q.loc['SEO', 'refund_rate_30d'])} and renew {pct(q.loc['SEO', 'renewal_rate'])}. "
         "By first-click channel; a cohort counts at month k only once k months have passed.",
         "SIMULATED DATA")
(xa, wa), (xb, wb) = cols(2)
h1 = 400
ltv, cac = meas("LTV 24m"), meas("CAC First Click")
p.chart("ltvVsCac", "clusteredBarChart", xa, TOP, wa, h1,
        {"Category": [C("Channel", "channel")], "Y": [ltv, cac]},
        "24-month net value per customer (blue) vs acquisition cost (grey), EUR",
        {"dataPoint": [series_color(ltv, BLUE), series_color(cac, GREY)], "labels": data_labels()},
        labels={qref(ltv): "Value after 24 months", qref(cac): "Cost per customer (first click)"},
        sort=(ltv, "Descending"), filters=[ACQ])
rr, ren = meas("Refund Rate First Click"), meas("Renewal Rate First Click")
p.chart("refundRenewal", "clusteredBarChart", xb, TOP, wb, h1,
        {"Category": [C("Channel", "channel")], "Y": [rr, ren]},
        "Refunded within 30 days (red) and renewed at the end of the term (blue)",
        {"dataPoint": [series_color(rr, RED), series_color(ren, BLUE)], "labels": data_labels()},
        labels={qref(rr): "Refund rate", qref(ren): "Renewal rate"}, sort=(rr, "Descending"), filters=[ACQ])
y = TOP + h1 + GAP
plans = [agg("Channel Quality", f"share_plan_{k}") for k in ("1m", "12m", "24m", "48m")]
p.chart("planMix", "hundredPercentStackedBarChart", xa, y, wa, BOT - y,
        {"Category": [C("Channel", "channel")], "Y": plans},
        "Plan length chosen at purchase (1 / 12 / 24 / 48 months)",
        {"dataPoint": [series_color(plans[0], RED_TINT), series_color(plans[1], LIGHT),
                       series_color(plans[2], SEQ["250"]), series_color(plans[3], BLUE)]},
        labels={qref(plans[0]): "1 month", qref(plans[1]): "12 months", qref(plans[2]): "24 months", qref(plans[3]): "48 months"},
        filters=[ACQ])
cv = meas("Cumulative Value per Order")
p.chart("valueCurve", "pivotTable", xb, y, wb, BOT - y,
        {"Rows": [C("Value Curve", "channel")], "Columns": [C("Value Curve", "months_since_order")], "Values": [cv]},
        "Cumulative net value per customer, EUR, by months since purchase",
        table_style([bg_rule(cv, "#FCFCFB", SEQ["350"])], matrix=True, font=11),
        labels={"Value Curve.channel": "Channel", "Value Curve.months_since_order": "Months"},
        filters=[flt("Value Curve", "months_since_order", [0, 3, 6, 9, 12, 15, 18, 21, 24]),
                 flt("Value Curve", "channel", ["Email", "Unattributed"], negate=True)])
p.footer(SRC_SIM)
pages.append(p)

# ======================= Page 5 - Incrementality & budget =======================
p = Page("a5000000000000000000", "5 · Incrementality & budget")
p.header(f"Brand ads are only {pct(INCR['value'])} incremental; moving {eur_k(MOVED)} to creators adds {NET:+,.0f} orders a year",
         f"Geo test: search ads on 'hostinger' paused for 12 weeks in US, ES and ID. {pct(RECAP['value'])} of ad clicks came back through the organic "
         f"brand result (95% CI {pct(RECAP['ci_low'])}-{pct(RECAP['ci_high'])}). At the margin a PPC non-brand order costs "
         f"{eur(inc_cost.loc['PPC Non-brand', 'cost_per_incremental_order'])}, a creator order {eur(inc_cost.loc['Influencers', 'cost_per_incremental_order'])}.",
         "SIMULATED DATA")
(xa, wa), (xb, wb) = cols(2)
h1 = 380
adc, orc = meas("Brand Ad Clicks"), meas("Organic Brand Clicks")
p.chart("geoClicks", "columnChart", xa, TOP, wa, h1,
        {"Category": [C("Geo Weekly", "week")], "Y": [adc, orc]},
        "Test countries: weekly brand-search clicks, paid ad (blue) vs organic result (grey). Ads off from 2 March",
        {"dataPoint": [series_color(adc, BLUE), series_color(orc, GREY)]},
        labels={qref(adc): "Paid brand ad", qref(orc): "Organic brand result"},
        filters=[flt("Geo Weekly", "group", ["test"])])
gi = meas("Brand Search Orders Index")
p.chart("geoIndex", "lineChart", xb, TOP, wb, h1,
        {"Category": [C("Geo Weekly", "week")], "Y": [gi], "Series": [C("Geo Weekly", "group")]},
        "Brand-search orders, index 100 = 8 weeks before the test: test (blue) vs control (grey)",
        {"dataPoint": [value_color("Geo Weekly", "group", "test", BLUE), value_color("Geo Weekly", "group", "control", GREY)],
         "y1AxisReferenceLine": [ref_line(100.0, "Baseline")]},
        labels={qref(gi): "Index"})
y = TOP + h1 + GAP
c3 = cols(3)
lpo, ipo = meas("Cost per Last-click Order"), meas("Cost per Incremental Order")
p.chart("incrementalCost", "clusteredBarChart", c3[0][0], y, c3[0][1], BOT - y,
        {"Category": [C("Incremental Cost", "channel")], "Y": [lpo, ipo]},
        "Cost per order as reported (grey) vs per incremental order (blue), EUR",
        {"dataPoint": [series_color(lpo, GREY), series_color(ipo, BLUE)], "labels": data_labels()},
        labels={qref(lpo): "Per last-click order", qref(ipo): "Per incremental order"}, sort=(ipo, "Descending"))
ro = meas("Reallocation Orders")
p.chart("reallocation", "waterfallChart", c3[1][0], y, c3[1][1], BOT - y,
        {"Category": [C("Reallocation", "move")], "Y": [ro]},
        f"Same budget, {eur_k(MOVED)} moved: incremental orders over 12 months",
        {"labels": data_labels(), "sentimentColors": [{"properties": {
            "increaseFill": color(BLUE), "decreaseFill": color(RED), "totalFill": color(INK)}}]},
        labels={qref(ro): "Orders"}, sort=(C("Reallocation", "move"), "Ascending"),
        filters=[flt("Reallocation", "move", ["Net, same total budget"], negate=True)])
p.text("recommendations", c3[2][0], y, c3[2][1], BOT - y, [
    [("Recommendations", 17, INK, True)],
    [("1 · ", 13, BLUE, True), ("Budget on 12-month net value, not last-click orders: trim PPC non-brand by 20% and fund creators.", 13, INK, False)],
    [("2 · ", 13, BLUE, True), ("Coupon sites: no commission when the cart was already started; one code per creator, revoked when it leaks.", 13, INK, False)],
    [("3 · ", 13, BLUE, True), ("Brand ads: keep them only where competitors bid on the brand name.", 13, INK, False)],
    [("", 8, INK, False)],
    [("Next quarter's test plan", 15, INK, True)],
    [("Geo holdout on creators (2 countries, 8 weeks) to replace the halo estimate with a measured lift; "
      "brand-ad test by country with competitor-bid monitoring; refund-rate alert per partner.", 13, INK2, False)],
], boxed=True)
p.footer(SRC_SIM + "   ·   DiD = difference-in-differences, bootstrap 5,000 resamples of weeks")
pages.append(p)


# ======================= Page 6 - Reach onboarding funnel =======================
p = Page("a6000000000000000000", "6 · Reach onboarding funnel")
lost_share = 1 - ph("contacts_step_conversion")
p.header(f"{pct(lost_share)} of Reach users who pick a template never import contacts: the biggest leak in onboarding",
         f"Of {ph('funnel_starters'):,.0f} users who started Hostinger Reach onboarding (30-day window over), {pct(ph('funnel_template_rate'))} chose a template, "
         f"{pct(ph('funnel_contacts_rate'))} imported contacts and {pct(ph('funnel_campaign_rate'))} sent a first campaign; contact import loses "
         f"{ph('contacts_step_lost'):,.0f} users, more in India and Indonesia. Marketing link: per 100 new customers, creators bring "
         f"{100 * ph('activated_per_customer_influencers'):.0f} users who reach the aha moment, PPC non-brand {100 * ph('activated_per_customer_ppc_nb'):.0f}, "
         f"coupon sites {100 * ph('activated_per_customer_coupon'):.0f}.",
         "SIMULATED DATA")
y = kpi_row(p, [("Reach Starters", "Started onboarding (30-day window over)"), ("Template Rate", "Chose a template"),
                ("Contacts Rate", "Imported contacts"), ("First Campaign Rate", "Sent a first campaign (30 days)"),
                ("Activation Rate 7d", "First campaign within 7 days")])
h1 = 400
(xa, wa), (xb, wb) = cols(2)
fu = agg("Reach Funnel", "users")
p.chart("funnel", "funnel", xa, y, wa, h1,
        {"Category": [C("Reach Funnel", "step")], "Y": [fu]},
        "Ordered funnel, 30-day conversion window (users at each step)",
        {"dataPoint": [{"properties": {"fill": color(BLUE)}}], "labels": data_labels(INK)},
        labels={qref(fu): "Users"})
apc = meas("Activated per 100 Customers")
p.chart("adoptionByChannel", "clusteredBarChart", xb, y, wb, h1,
        {"Category": [C("Channel", "channel")], "Y": [apc]},
        "Per 100 new customers of each acquisition channel: users who send a first Reach campaign within 7 days",
        no_legend({"dataPoint": [{"properties": {"fill": color(BLUE)}}], "labels": data_labels()}),
        labels={qref(apc): "Activated per 100 customers"}, sort=(apc, "Descending"),
        filters=[flt("Channel", "channel", ["Email", "Unattributed"], negate=True)])
y += h1 + GAP
p.chart("stepTable", "tableEx", xa, y, wa, BOT - y,
        {"Values": [C("Reach Funnel", "step"), C("Reach Funnel", "users"), C("Reach Funnel", "conversion_from_previous"),
                    C("Reach Funnel", "users_lost"), C("Reach Funnel", "median_hours_from_previous")]},
        "Step by step: conversion from the previous step and median time it takes",
        table_style([bg_rule(C("Reach Funnel", "conversion_from_previous"), RED_TINT, BLUE_TINT)]),
        labels={"Reach Funnel.step": "Step", "Reach Funnel.users": "Users", "Reach Funnel.conversion_from_previous": "From previous step",
                "Reach Funnel.users_lost": "Users lost", "Reach Funnel.median_hours_from_previous": "Median hours from previous"},
        sort=(C("Reach Funnel", "users"), "Descending"))
ctry = [C("Country", "country_name")] + Ms("Reach Starters", "Template Rate", "Contacts Rate", "First Campaign Rate", "Activation Rate 7d")
p.chart("countryTable", "tableEx", xb, y, wb, BOT - y, {"Values": ctry},
        "Funnel by country (red = weaker contact import)",
        table_style([bg_rule(meas("Contacts Rate"), RED_TINT, BLUE_TINT)]),
        labels={"Country.country_name": "Country", "_Measures.Reach Starters": "Starters", "_Measures.Template Rate": "Template",
                "_Measures.Contacts Rate": "Contacts", "_Measures.First Campaign Rate": "First campaign", "_Measures.Activation Rate 7d": "Within 7 days"},
        sort=(meas("Contacts Rate"), "Descending"))
p.footer(SRC_PROD + "   ·   sql/08")
pages.append(p)

# ======================= Page 7 - Defining product adoption =======================
p = Page("a7000000000000000000", "7 · Defining product adoption")
p.header(f"Adoption = first campaign within 7 days: {pct(ph('retention_d30_aha'))} still active at day 30, vs {pct(ph('retention_d30_late'))} for later senders",
         f"Day-30 retention is flat for a first campaign on day 0-1, 2-3 or 4-7 and falls after day 7, so adoption is defined there; "
         f"{pct(ph('activated_7d_rate'))} of starters reach it. The {100 * ph('aha_gap'):.0f}-point gap holds in every channel, platform and product, but it is a "
         f"correlation (motivated users are faster and more loyal): an encouragement test would measure the causal part. "
         f"Hostinger Mail: AI replies lift messages sent by {ph('mail_mobile_lift'):+.0%} for mobile users only.",
         "SIMULATED DATA")
y = kpi_row(p, [("Activation Rate 7d", "Adopted: first campaign within 7 days"), ("Retention D30", "Active at day 30, all starters"),
                ("Retention D30 Adopters", "Active at day 30, adopters"), ("Upgrade Rate 60d", "Upgraded within 60 days")])
h1 = 400
(xa, wa), (xb, wb) = cols(2)
ar = agg("Aha Retention", "retention_d30")
p.chart("ahaRetention", "clusteredColumnChart", xa, y, wa, h1,
        {"Category": [C("Aha Retention", "first_campaign")], "Y": [ar]},
        "Day-30 retention by the day of the first campaign (users with 35 days of history)",
        no_legend({"dataPoint": [{"properties": {"fill": color(BLUE)}}], "labels": data_labels()}),
        labels={qref(ar): "Day-30 retention"}, sort=(C("Aha Retention", "first_campaign"), "Ascending"))
rw = meas("Retention by Week")
p.chart("adoptionCurve", "lineChart", xb, y, wb, h1,
        {"Category": [C("Adoption Curve", "week")], "Y": [rw], "Series": [C("Adoption Curve", "adoption_group")]},
        "Share of users active each week after the start, by adoption group (censoring-safe)",
        {"dataPoint": [value_color("Adoption Curve", "adoption_group", "First campaign within 7 days", BLUE),
                       value_color("Adoption Curve", "adoption_group", "First campaign on days 8-30", GREY),
                       value_color("Adoption Curve", "adoption_group", "No campaign in 30 days", INK)],
         "legend": [{"properties": {"show": lit(True), "position": lit("Top")}}]},
        labels={qref(rw): "Active that week"})
y += h1 + GAP
p.text("definition", xa, y, wa, BOT - y, [
    [("Proposed definition of a successful Reach adoption", 16, INK, True)],
    [("Leading, week 1   ", 13, BLUE, True), ("first campaign within 7 days of the start: predicts retention, early enough to act on, moved by onboarding.", 13, INK, False)],
    [("Habit, week 5   ", 13, BLUE, True), ("a core action in days 28-34 (campaign, AI copy, template, contacts).", 13, INK, False)],
    [("Value, month 2   ", 13, BLUE, True), ("upgrade to a paid plan within 60 days (the free Starter plan stops at 100 recipients).", 13, INK, False)],
    [("", 6, INK, False)],
    [("Proving causality   ", 13, INK, True), ("randomise a strong push to the first campaign (contacts-import assistant + day-2 reminder) "
                                               "and compare retention by assigned group (intention to treat).", 13, INK2, False)],
], boxed=True)
ml = meas("Mail AI Lift")
p.chart("mailLift", "clusteredBarChart", xb, y, wb, BOT - y,
        {"Category": [C("Mail AI Lift", "segment")], "Y": [ml]},
        "Hostinger Mail: change in messages sent per user after AI replies (wave 1 vs wave 2, difference-in-differences)",
        no_legend({"dataPoint": [{"properties": {"fill": color(BLUE)}}], "labels": data_labels()}),
        labels={qref(ml): "Lift in messages sent"}, sort=(ml, "Descending"),
        filters=[flt("Mail AI Lift", "metric", ["Messages sent per week"])])
p.footer(SRC_PROD + "   ·   sql/09, product notebook §2-3")
pages.append(p)

# ======================= Page 8 - A/B test =======================
p = Page("a8000000000000000000", "8 · A/B test: AI-prefilled first campaign")
p.header(f"AI-prefilled first campaign: {100 * ph('ab_effect'):+.1f} pts of 7-day activation once a broken test day is removed",
         f"Plan fixed before launch: primary metric first campaign within 7 days, 16 weeks, minimum detectable effect {100 * ph('ab_mde'):.1f} pts. "
         f"The sample-ratio check failed (p < 0.001): on 14 July every mobile user went to control. Without that day (p = {ph('ab_srm_p_clean'):.2f}) "
         f"activation rises from {pct(ph('ab_control'), 1)} to {pct(ph('ab_treatment'), 1)} (95% CI {100 * ph('ab_ci_low'):+.1f} to {100 * ph('ab_ci_high'):+.1f} pts, "
         f"p = {ph('ab_p_value'):.3f}); keeping it would have reported {100 * ph('ab_effect_with_bad_day'):+.1f} pts. Upgrades dip {-100 * ph('ab_upgrade_diff'):.1f} pts "
         f"(p = {ph('ab_upgrade_p_holm'):.2f} after correction): ship with a holdout.",
         "SIMULATED DATA")
y = kpi_row(p, [("Test Users", "Users in the test (14 July removed)"), ("Control Activation", "Control: blank editor"),
                ("Treatment Activation", "Treatment: AI-prefilled campaign"), ("Test Effect", "Effect, points")])
h1 = 390
lw = W * 0.6
cu, tu = meas("Control Users per Day"), meas("Treatment Users per Day")
p.chart("dailyAssignment", "clusteredColumnChart", L, y, lw, h1,
        {"Category": [C("AB Daily", "assigned_date")], "Y": [cu, tu]},
        "Users assigned per day: on 14 July (newsletter day) every mobile user went to control",
        {"dataPoint": [series_color(cu, GREY), series_color(tu, BLUE)],
         "legend": [{"properties": {"show": lit(True), "position": lit("Top")}}]},
        labels={qref(cu): "Control", qref(tu): "Treatment"})
rx = L + lw + GAP
p.text("plan", rx, y, R - rx, h1, [
    [("Test plan, written before launch", 16, INK, True)],
    [("Hypothesis   ", 12, BLUE, True), ("an AI draft removes the blank page, so more users send a first campaign.", 12, INK, False)],
    [("Primary   ", 12, BLUE, True), ("first campaign within 7 days.   ", 12, INK, False),
     ("Guardrails   ", 12, BLUE, True), ("day-30 retention, upgrades in 60 days.", 12, INK, False)],
    [("Power   ", 12, BLUE, True), (f"{ph('ab_n_available_per_arm'):,.0f} users per arm in 16 weeks: {100 * ph('ab_mde'):.1f} pts detectable at 80% power.", 12, INK, False)],
    [("Rules   ", 12, BLUE, True), ("sample-ratio check first; one reading at the end, no peeking; segments exploratory (Holm).", 12, INK, False)],
    [("", 6, INK, False)],
    [("Decision", 16, INK, True)],
    [("Ship to all new Reach users, keep a 5% holdout for 8 weeks to confirm the effect and watch upgrades and novelty "
      f"(weeks 1-8 vs 9-16: interaction p ≥ {ph('ab_interaction_p_min'):.2f}). Add a daily automatic SRM alert.", 12, INK2, False)],
], boxed=True)
y += h1 + GAP
res = [C("AB Result", c) for c in ("metric", "control", "treatment", "diff", "ci_low", "ci_high", "p_value", "p_holm")]
p.chart("results", "tableEx", L, y, lw, BOT - y, {"Values": res},
        "Results on the clean sample (95% CI; p_holm = corrected for the 4 secondary metrics)",
        table_style([bg_rule(C("AB Result", "diff"), RED_TINT, BLUE_TINT, NEUTRAL, 0)], font=11),
        labels={"AB Result.metric": "Metric", "AB Result.control": "Control", "AB Result.treatment": "Treatment",
                "AB Result.diff": "Effect", "AB Result.ci_low": "CI low", "AB Result.ci_high": "CI high",
                "AB Result.p_value": "p", "AB Result.p_holm": "p (Holm)"},
        sort=(C("AB Result", "metric"), "Ascending"))
un = meas("Users per Arm Needed")
p.chart("power", "lineChart", rx, y, R - rx, BOT - y,
        {"Category": [C("AB Power", "mde_points")], "Y": [un]},
        "Users per arm needed vs effect to detect, in points (dashed = 16 weeks of traffic)",
        no_legend({"dataPoint": [{"properties": {"fill": color(BLUE)}}],
                   "y1AxisReferenceLine": [ref_line(float(round(ph("ab_n_available_per_arm"))), "16 weeks")]}),
        labels={qref(un): "Users per arm"})
p.footer(SRC_PROD + "   ·   sql/10, product notebook §1")
pages.append(p)

# ======================= Page 9 - Referral programme economics =======================
p = Page("a9000000000000000000", "9 · Referral programme economics")
gain = ph("referral_net_controls") - ph("referral_net_no_controls")
p.header(f"Self-referrals take {pct(ph('self_referral_cost_share'))} of the referral budget: block them before touching the reward rate",
         f"{N_REF:,} referrals cost {eur_k(ph('referral_cost_eur'))}: 20% reward to the referrer plus the friend's 20% discount (public terms). It pays back only "
         f"if {pct(ph('referral_break_even_incrementality'))} of referred friends would not have bought otherwise. {ph('self_referrals_flagged'):,.0f} referrals "
         f"({pct(ph('self_referral_share'), 1)}) look like customers referring a second account (same card, or same device and sign-up 2 minutes after the link). "
         f"Scenario (labelled assumptions): blocking them adds {eur_k(gain)} a year; the best reward rate needs a reward test.",
         "SIMULATED DATA")
y = kpi_row(p, [("Referral Count", "Referrals, May 2025 - Oct 2026"), ("Referral Programme Cost", "Rewards + friend discounts"),
                ("Break-even Incrementality", "Friends who must be truly new"), ("Self-referral Share", "Flagged as self-referrals")])
h1 = 400
(xa, wa), (xb, wb) = cols(2)
bc, bv = meas("Band Programme Cost"), meas("Band Value 12m")
p.chart("bands", "clusteredColumnChart", xa, y, wa, h1,
        {"Category": [C("Referral Bands", "reward_band")], "Y": [bc, bv]},
        "By reward size: programme cost (grey) vs 12-month value of genuine friends (blue), EUR",
        {"dataPoint": [series_color(bc, GREY), series_color(bv, BLUE)], "labels": data_labels(),
         "legend": [{"properties": {"show": lit(True), "position": lit("Top")}}]},
        labels={qref(bc): "Programme cost", qref(bv): "12-month value (genuine friends)"},
        sort=(C("Referral Bands", "reward_band"), "Ascending"))
sn = meas("Scenario Net Value")
p.chart("scenario", "lineChart", xb, y, wb, h1,
        {"Category": [C("Referral Scenarios", "reward_rate")], "Y": [sn], "Series": [C("Referral Scenarios", "controls")]},
        "Scenario: net value per year by reward rate (assumed: 50% of friends truly new, elasticity 0.5)",
        {"dataPoint": [value_color("Referral Scenarios", "controls", "Self-referral blocking", BLUE),
                       value_color("Referral Scenarios", "controls", "No controls", GREY)],
         "legend": [{"properties": {"show": lit(True), "position": lit("Top")}}],
         "y1AxisReferenceLine": [ref_line(0.0, "Break-even")]},
        labels={qref(sn): "Net value per year (EUR)"},
        filters=[flt("Referral Scenarios", "incrementality", [0.5]), flt("Referral Scenarios", "elasticity", [0.5])])
y += h1 + GAP
p.chart("fraudRules", "tableEx", xa, y, wa, BOT - y,
        {"Values": [C("Referrals", "fraud_check")] + Ms("Referral Count", "Referral Reward Cost", "Referral Programme Cost", "Median Minutes Link to Sign-up")},
        "Self-referral checks: what each rule catches",
        table_style(),
        labels={"Referrals.fraud_check": "Check", "_Measures.Referral Count": "Referrals", "_Measures.Referral Reward Cost": "Rewards",
                "_Measures.Referral Programme Cost": "Rewards + discounts", "_Measures.Median Minutes Link to Sign-up": "Median minutes link → sign-up"},
        sort=(meas("Referral Count"), "Descending"))
cr, sr = meas("Clean Referrals"), meas("Self-referral Count")
p.chart("monthly", "columnChart", xb, y, wb, BOT - y,
        {"Category": [C("Date", "Month")], "Y": [cr, sr]},
        "Referrals per month: clean (blue) and flagged self-referrals (red)",
        {"dataPoint": [series_color(cr, BLUE), series_color(sr, RED)],
         "legend": [{"properties": {"show": lit(True), "position": lit("Top")}}]},
        labels={qref(cr): "Clean", qref(sr): "Self-referral"})
p.footer(SRC_PROD + "   ·   sql/11, product notebook §4")
pages.append(p)

# ======================= Annex - Data model =======================
p = Page("aa000000000000000000", "A · Data model")
p.header("One star schema for both parts: shared Date, Channel and Country dimensions",
         "Annex. The Power BI model is written as code (src/build_tmdl.py, TMDL) and the pages as PBIR (src/build_report_pages.py). Facts read the CSV outputs of the "
         "SQL files and notebooks; small output tables feed single charts. The shared dimensions let a product metric be cut by the acquisition channel of the customer.",
         "ANNEX")
c3 = cols(3)
hb = 520
p.text("facts", c3[0][0], TOP, c3[0][1], hb, [
    [("Fact tables", 18, INK, True)],
    [("", 6, INK, False)],
    [("Marketing", 14, BLUE, True)],
    [("Orders  ", 13, INK, True), ("one row per order: paid, refunded, renewals, 30-day / 12-month value", 13, INK2, False)],
    [("Attribution Credits  ", 13, INK, True), ("order × model × channel credit (6 models)", 13, INK2, False)],
    [("Spend  ", 13, INK, True), ("day × channel × campaign", 13, INK2, False)],
    [("", 6, INK, False)],
    [("Product", 14, BLUE, True)],
    [("Reach Users  ", 13, INK, True), ("one row per Reach user: funnel steps, aha moment, retention, upgrade", 13, INK2, False)],
    [("Experiment Users  ", 13, INK, True), ("one row per user in the A/B test, with every test metric", 13, INK2, False)],
    [("Referrals  ", 13, INK, True), ("one row per referral: reward, discount, friend's value, fraud checks", 13, INK2, False)],
    [("Product Daily  ", 13, INK, True), (f"{N_EVENTS / 1e6:.1f}M Amplitude-style events rolled up by day, event, platform, country", 13, INK2, False)],
], boxed=True)
p.text("dims", c3[1][0], TOP, c3[1][1], hb, [
    [("Dimensions", 18, INK, True)],
    [("", 6, INK, False)],
    [("Shared by both parts", 14, BLUE, True)],
    [("Date  ", 13, INK, True), ("1 May 2024 - 31 Oct 2026, month sort key", 13, INK2, False)],
    [("Channel  ", 13, INK, True), ("8 acquisition channels + Unattributed, grouped", 13, INK2, False)],
    [("Country  ", 13, INK, True), ("6 countries, geo-test group", 13, INK2, False)],
    [("", 6, INK, False)],
    [("Marketing", 14, BLUE, True)],
    [("Attribution Model, Creator, Affiliate", 13, INK2, False)],
    [("", 6, INK, False)],
    [("Product", 14, BLUE, True)],
    [("Product  ", 13, INK, True), ("Reach, Mail, Referral", 13, INK2, False)],
    [("AB Variant  ", 13, INK, True), ("control, treatment", 13, INK2, False)],
], boxed=True)
p.text("rules", c3[2][0], TOP, c3[2][1], hb, [
    [("Modelling rules", 18, INK, True)],
    [("", 6, INK, False)],
    [("Single-direction ", 13, INK, True), ("relationships, dimension → fact, no many-to-many.", 13, INK2, False)],
    [("Censoring-safe ", 13, INK, True), ("rates: a user counts only once the window is over (funnel_complete, mature_d30, ...).", 13, INK2, False)],
    [("Test data ", 13, INK, True), ("A/B measures exclude 14 July, the day of the sample-ratio mismatch.", 13, INK2, False)],
    [("Measures ", 13, INK, True), (f"{N_MEASURES} DAX measures in display folders; product measures under Product\\Funnel, Adoption, A/B test, Referral.", 13, INK2, False)],
    [("Numbers in titles ", 13, INK, True), ("are read from the SQL and notebook outputs by the page script, never typed by hand.", 13, INK2, False)],
], boxed=True)
# relationships, read from the model builder so the list never drifts from the model
sys.path.insert(0, str(ROOT / "src"))
from build_tmdl import RELATIONSHIPS  # noqa: E402
rel = {}
for fact, _, dim, _ in RELATIONSHIPS:
    rel.setdefault(fact, []).append(dim)
items = [[(f"{f}  ", 12, INK, True), ("→ " + ", ".join(d) + "   ", 12, INK2, False)] for f, d in rel.items()]
half = (len(items) + 1) // 2
yr = TOP + hb + GAP
(xl, wl), (xr, wr) = cols(2)
p.text("relationships", xl, yr, wl, BOT - yr, [[(f"Relationships ({len(RELATIONSHIPS)}), fact → dimensions", 16, INK, True)]] + items[:half], boxed=True)
p.text("relationships2", xr, yr, wr, BOT - yr, [[("", 16, INK, True)]] + items[half:], boxed=True)
p.footer("Model: powerbi/HostingerAttribution.SemanticModel (TMDL) · Report: powerbi/HostingerAttribution.Report (PBIR)")
pages.append(p)

# ---------------------------------------------------------------- write
PAGES.mkdir(parents=True, exist_ok=True)
keep = {pg.pid for pg in pages}
for d in PAGES.iterdir():
    if d.is_dir() and d.name not in keep:
        shutil.rmtree(d)
for pg in pages:
    pg.write()
meta = {"$schema": PAGES_SCHEMA, "pageOrder": [pg.pid for pg in pages], "activePageName": pages[0].pid}
(PAGES / "pages.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print("pages:", [(pg.name.encode("ascii", "replace").decode(), len(pg.visuals)) for pg in pages])
for pg in pages:
    t = next(v for v in pg.visuals if v["name"] == "title")
    print(" -", t["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]["value"].encode("ascii", "replace").decode())
