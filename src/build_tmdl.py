"""Write the Power BI semantic model (TMDL) for powerbi/HostingerAttribution.SemanticModel.

Star schema:
  facts       Orders (one row per order: paid, refunded, renewals, value), Attribution Credits
              (order x model x channel), Spend (day x channel x campaign)
  dimensions  Date, Channel, Model, Country, Creator, Affiliate
  outputs     small tables written by SQL / the notebook (paths, value curve, geo test, ...)

Every table reads a CSV from the DataFolder parameter (default C:\\case-study-honstinger\\data\\).
Usage:  python src/build_tmdl.py
Close Power BI Desktop first: the model files are rewritten.
"""
import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SM = ROOT / "powerbi" / "HostingerAttribution.SemanticModel"
DEF = SM / "definition"
DATA_FOLDER = str(ROOT / "data") + "\\"


def tag(*parts):
    """Stable lineage tag, so Power BI sees the same object on every rebuild."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "hosting-attribution/" + "/".join(parts)))


def q(name):
    """Quote a TMDL name when it contains spaces or symbols."""
    return name if name.replace("_", "").isalnum() else "'" + name.replace("'", "''") + "'"


# ---------------------------------------------------------------- column types
# (csv column, power bi type, format string)
M_TYPE = {"int": "Int64.Type", "num": "type number", "text": "type text", "bool": "type logical", "date": "type date"}
TMDL_TYPE = {"int": "int64", "num": "double", "text": "string", "bool": "boolean", "date": "dateTime"}

EUR0, EUR2, PCT0, PCT1, INT = "€#,0", "€#,0.00", "0%", "0.0%", "#,0"


def csv_table(name, path, cols, extra_steps=None, hidden=()):
    return {"name": name, "path": path, "cols": cols, "extra": extra_steps or [], "hidden": set(hidden)}


TABLES = [
    csv_table("Orders", r"output\order_value.csv", [
        ("order_id", "int", "0"), ("order_date", "date", "dd mmm yyyy"), ("cohort_month", "date", "mmm yyyy"),
        ("country", "text", None), ("product", "text", None), ("plan_months", "int", "0"),
        ("coupon_code", "text", None), ("paid_amount_eur", "num", EUR2), ("refunded_eur", "num", EUR2),
        ("is_refunded", "bool", None), ("renewal_12m", "num", EUR2), ("has_renewal_decision", "bool", None),
        ("renewed_first_time", "bool", None), ("first_click_channel", "text", None),
        ("last_click_channel", "text", None), ("mature_30d", "bool", None), ("mature_12m", "bool", None),
        ("net_value_30d", "num", EUR2), ("net_value_12m", "num", EUR2), ("expected_value_12m", "num", EUR2)],
        extra_steps=['WithDate = Table.AddColumn(Promoted, "order_date", each Date.FromText(Text.Start([order_ts], 10), [Format="yyyy-MM-dd"]), type date)'],
        hidden=["order_id"]),
    csv_table("Attribution Credits", r"output\attribution_credits.csv", [
        ("order_id", "int", "0"), ("model", "text", None), ("channel", "text", None), ("credit", "num", "0.000")],
        hidden=["order_id"]),
    csv_table("Spend", r"clean\sim_spend.csv", [
        ("date", "date", "dd mmm yyyy"), ("channel", "text", None), ("sub_channel", "text", None),
        ("campaign_id", "text", None), ("creator_id", "text", None), ("affiliate_id", "text", None),
        ("country", "text", None), ("spend_eur", "num", EUR0), ("impressions", "int", INT), ("clicks", "int", INT)]),
    csv_table("Creator", r"output\creator_scorecard.csv", [
        ("creator_id", "text", None), ("creator_name", "text", None), ("platform", "text", None),
        ("niche", "text", None), ("main_country", "text", None), ("audience_size", "int", INT),
        ("fee_model", "text", None), ("videos", "int", INT), ("cost_eur", "num", EUR0),
        ("claimed_orders", "int", INT), ("link_orders", "int", INT), ("code_orders", "int", INT),
        ("leaked_code_orders", "int", INT), ("leaked_share_of_code", "num", PCT0), ("refund_rate_30d", "num", PCT1),
        ("genuine_orders", "int", INT), ("cost_per_genuine_order", "num", EUR0), ("value_12m_genuine", "num", EUR0),
        ("roi_12m", "num", PCT0)]),
    csv_table("Affiliate", r"output\affiliate_scorecard.csv", [
        ("affiliate_id", "text", None), ("type", "text", None), ("main_country", "text", None),
        ("commission_rate", "num", PCT0), ("last_click_orders", "int", INT), ("commission_eur", "num", EUR0),
        ("commission_per_order", "num", EUR2), ("refund_rate_30d", "num", PCT1),
        ("share_cart_already_started", "num", PCT0), ("share_with_earlier_channel", "num", PCT0),
        ("expected_value_12m_per_order", "num", EUR2)]),
    csv_table("Top Paths", r"output\top_paths.csv", [
        ("path", "text", None), ("orders", "int", INT), ("share_of_orders", "num", PCT1),
        ("avg_touchpoints", "num", "0.0"), ("avg_days_to_convert", "num", "0.0")],
        extra_steps=['Ranked = Table.AddIndexColumn(Typed, "rank", 1, 1, Int64.Type)']),
    csv_table("Path Length", r"output\path_length_dist.csv", [
        ("touchpoints", "text", None), ("orders", "int", INT), ("share_of_orders", "num", PCT0)]),
    csv_table("Days To Convert", r"output\days_to_convert_dist.csv", [
        ("days_to_convert", "text", None), ("orders", "int", INT), ("share_of_orders", "num", PCT0)]),
    csv_table("Value Curve", r"output\value_curve.csv", [
        ("channel", "text", None), ("months_since_order", "int", "0"), ("orders_observed", "int", INT),
        ("cumulative_value_per_order", "num", EUR0)]),
    csv_table("Channel Quality", r"output\channel_quality.csv", [
        ("channel", "text", None), ("orders", "int", INT), ("refund_rate_30d", "num", PCT1),
        ("share_plan_1m", "num", PCT0), ("share_plan_12m", "num", PCT0), ("share_plan_24m", "num", PCT0),
        ("share_plan_48m", "num", PCT0), ("avg_plan_months", "num", "0.0"), ("net_value_30d", "num", EUR0),
        ("expected_value_12m", "num", EUR0), ("renewal_rate", "num", PCT0), ("ltv_24m", "num", EUR0),
        ("orders_in_ltv_24m", "int", INT), ("spend_eur", "num", EUR0), ("cac_first_click", "num", EUR0),
        ("payback_month", "int", "0")]),
    csv_table("Code Usage", r"output\code_usage_weekly.csv", [
        ("creator_id", "text", None), ("week", "date", "dd mmm yyyy"), ("code_orders", "int", INT),
        ("leaked_code_orders", "int", INT), ("videos", "int", INT)]),
    csv_table("Geo Weekly", r"output\geo_did_weekly.csv", [
        ("week", "date", "dd mmm"), ("group", "text", None), ("phase", "text", None), ("orders", "int", INT),
        ("brand_search_orders", "int", INT), ("orders_index", "num", "0"), ("brand_clicks", "int", INT),
        ("brand_ad_clicks", "int", INT), ("organic_brand_clicks", "int", INT)]),
    csv_table("Geo Result", r"output\geo_result.csv", [
        ("metric", "text", None), ("value", "num", PCT0), ("ci_low", "num", PCT0), ("ci_high", "num", PCT0)],
        extra_steps=['Ranked = Table.AddIndexColumn(Typed, "rank", 1, 1, Int64.Type)']),
    csv_table("Video Event Study", r"output\video_event_study.csv", [
        ("day", "int", "0"), ("index", "num", "0")]),
    csv_table("Incremental Cost", r"output\incremental_cost.csv", [
        ("channel", "text", None), ("cost_per_last_click_order", "num", EUR0),
        ("cost_per_incremental_order", "num", EUR0), ("method", "text", None)]),
    csv_table("Reallocation", r"output\reallocation.csv", [
        ("move", "text", None), ("budget_change_eur_12m", "num", EUR0), ("incremental_orders_12m", "num", "+#,0;-#,0;0")],
        extra_steps=['Ranked = Table.AddIndexColumn(Typed, "rank", 1, 1, Int64.Type)']),
]

# static dimensions: (name, columns, rows)
CHANNELS = [("PPC Brand", 1, "Paid search"), ("PPC Non-brand", 2, "Paid search"), ("SEO", 3, "Organic"),
            ("Affiliates - Content", 4, "Partners"), ("Affiliates - Coupon", 5, "Partners"),
            ("Influencers", 6, "Partners"), ("Email", 7, "Owned"), ("Direct", 8, "Owned"),
            ("Unattributed", 9, "Not tracked")]
MODELS = [("Last click", 1), ("First click", 2), ("Linear", 3), ("Time decay", 4),
          ("Position 40/20/40", 5), ("Markov (data-driven)", 6)]
COUNTRIES = [("US", "United States", "test"), ("FR", "France", "control"), ("ES", "Spain", "test"),
             ("BR", "Brazil", "control"), ("IN", "India", "control"), ("ID", "Indonesia", "test")]
STATIC = [
    ("Channel", [("channel", "text"), ("channel_sort", "int"), ("channel_group", "text")], CHANNELS,
     {"channel": "channel_sort"}),
    ("Attribution Model", [("model", "text"), ("model_sort", "int")], MODELS, {"model": "model_sort"}),
    ("Country", [("country", "text"), ("country_name", "text"), ("geo_test_group", "text")], COUNTRIES, {}),
]

# ---------------------------------------------------------------- measures
# (name, DAX, format, folder). The model slicer drives every "credited" measure;
# without a selection they use Markov (data-driven).
SEL = """VAR m = SELECTEDVALUE ( 'Attribution Model'[model], "Markov (data-driven)" ) RETURN """
CR = "'Attribution Credits'"
MEASURES = [
    ("Total Spend", "SUM ( Spend[spend_eur] )", EUR0, "Spend"),
    ("Spend Share", "DIVIDE ( [Total Spend], CALCULATE ( [Total Spend], REMOVEFILTERS ( Channel ) ) )", PCT0, "Spend"),
    ("Order Count", "COUNTROWS ( Orders )", INT, "Orders"),
    ("Credited Orders", SEL + f"CALCULATE ( SUM ( {CR}[credit] ), 'Attribution Model'[model] = m )", INT, "Attribution"),
    ("Credit Share", "DIVIDE ( [Credited Orders], CALCULATE ( [Credited Orders], REMOVEFILTERS ( Channel ) ) )", PCT1, "Attribution"),
    ("Credit Share by Model", f"DIVIDE ( SUM ( {CR}[credit] ), CALCULATE ( SUM ( {CR}[credit] ), REMOVEFILTERS ( Channel ) ) )", PCT1, "Attribution"),
    ("Credited Value 30d", SEL + f"CALCULATE ( SUMX ( {CR}, {CR}[credit] * RELATED ( Orders[net_value_30d] ) ), 'Attribution Model'[model] = m )", EUR0, "Value"),
    ("Credited Value 12m", SEL + f"CALCULATE ( SUMX ( {CR}, {CR}[credit] * RELATED ( Orders[expected_value_12m] ) ), 'Attribution Model'[model] = m )", EUR0, "Value"),
    ("CAC", "DIVIDE ( [Total Spend], [Credited Orders] )", EUR0, "Efficiency"),
    ("ROAS 30d", "DIVIDE ( [Credited Value 30d], [Total Spend] )", PCT0, "Efficiency"),
    ("ROAS 12m", "DIVIDE ( [Credited Value 12m], [Total Spend] )", PCT0, "Efficiency"),
    ("Value per Order 12m", "DIVIDE ( [Credited Value 12m], [Credited Orders] )", EUR0, "Efficiency"),
    ("Net Return 12m", "[Credited Value 12m] - [Total Spend]", EUR0, "Efficiency"),
    ("Refund Rate", SEL + f"CALCULATE ( DIVIDE ( SUMX ( FILTER ( {CR}, RELATED ( Orders[mature_30d] ) && RELATED ( Orders[is_refunded] ) ), {CR}[credit] ), SUMX ( FILTER ( {CR}, RELATED ( Orders[mature_30d] ) ), {CR}[credit] ) ), 'Attribution Model'[model] = m )", PCT1, "Quality"),
    ("Long Plan Share", SEL + f"CALCULATE ( DIVIDE ( SUMX ( FILTER ( {CR}, RELATED ( Orders[plan_months] ) >= 24 ), {CR}[credit] ), SUM ( {CR}[credit] ) ), 'Attribution Model'[model] = m )", PCT0, "Quality"),
    ("Renewal Rate", SEL + f"CALCULATE ( DIVIDE ( SUMX ( FILTER ( {CR}, RELATED ( Orders[renewed_first_time] ) ), {CR}[credit] ), SUMX ( FILTER ( {CR}, RELATED ( Orders[has_renewal_decision] ) ), {CR}[credit] ) ), 'Attribution Model'[model] = m )", PCT0, "Quality"),
    ("LTV 24m", "SUM ( 'Channel Quality'[ltv_24m] )", EUR0, "Customer value"),
    ("CAC First Click", "SUM ( 'Channel Quality'[cac_first_click] )", EUR0, "Customer value"),
    ("Payback Month", "MIN ( 'Channel Quality'[payback_month] )", "0", "Customer value"),
    ("Refund Rate First Click", "AVERAGE ( 'Channel Quality'[refund_rate_30d] )", PCT1, "Customer value"),
    ("Renewal Rate First Click", "AVERAGE ( 'Channel Quality'[renewal_rate] )", PCT0, "Customer value"),
    ("Cumulative Value per Order", "AVERAGE ( 'Value Curve'[cumulative_value_per_order] )", EUR0, "Customer value"),
    ("Creator Cost", "SUM ( Creator[cost_eur] )", EUR0, "Creators & affiliates"),
    ("Genuine Creator Orders", "SUM ( Creator[genuine_orders] )", INT, "Creators & affiliates"),
    ("Leaked Code Orders", "SUM ( Creator[leaked_code_orders] )", INT, "Creators & affiliates"),
    ("Leaked Share of Code Orders", "DIVIDE ( [Leaked Code Orders], SUM ( Creator[code_orders] ) )", PCT0, "Creators & affiliates"),
    ("Weekly Code Orders", "SUM ( 'Code Usage'[code_orders] )", INT, "Creators & affiliates"),
    ("Weekly Leaked Code Orders", "SUM ( 'Code Usage'[leaked_code_orders] )", INT, "Creators & affiliates"),
    ("Weekly Genuine Code Orders", "[Weekly Code Orders] - [Weekly Leaked Code Orders]", INT, "Creators & affiliates"),
    ("Videos Published", "SUM ( 'Code Usage'[videos] )", INT, "Creators & affiliates"),
    ("Affiliate Commission", "SUM ( Affiliate[commission_eur] )", EUR0, "Creators & affiliates"),
    ("Affiliate Orders", "SUM ( Affiliate[last_click_orders] )", INT, "Creators & affiliates"),
    ("Affiliate Refund Rate", "DIVIDE ( SUMX ( Affiliate, Affiliate[refund_rate_30d] * Affiliate[last_click_orders] ), SUM ( Affiliate[last_click_orders] ) )", PCT1, "Creators & affiliates"),
    ("Cart Already Started Share", "DIVIDE ( SUMX ( Affiliate, Affiliate[share_cart_already_started] * Affiliate[last_click_orders] ), SUM ( Affiliate[last_click_orders] ) )", PCT0, "Creators & affiliates"),
    ("Brand Search Index", "AVERAGE ( 'Video Event Study'[index] )", "0", "Incrementality"),
    ("Brand Ad Clicks", "SUM ( 'Geo Weekly'[brand_ad_clicks] )", INT, "Incrementality"),
    ("Organic Brand Clicks", "SUM ( 'Geo Weekly'[organic_brand_clicks] )", INT, "Incrementality"),
    ("Brand Search Orders Index", "AVERAGE ( 'Geo Weekly'[orders_index] )", "0", "Incrementality"),
    ("Cost per Incremental Order", "SUM ( 'Incremental Cost'[cost_per_incremental_order] )", EUR0, "Incrementality"),
    ("Cost per Last-click Order", "SUM ( 'Incremental Cost'[cost_per_last_click_order] )", EUR0, "Incrementality"),
    ("Reallocation Orders", "SUM ( Reallocation[incremental_orders_12m] )", "+#,0;-#,0;0", "Incrementality"),
]

RELATIONSHIPS = [  # many side -> one side
    ("Orders", "order_date", "Date", "Date"),
    ("Orders", "country", "Country", "country"),
    ("Attribution Credits", "order_id", "Orders", "order_id"),
    ("Attribution Credits", "channel", "Channel", "channel"),
    ("Attribution Credits", "model", "Attribution Model", "model"),
    ("Spend", "date", "Date", "Date"),
    ("Spend", "channel", "Channel", "channel"),
    ("Spend", "country", "Country", "country"),
    ("Spend", "creator_id", "Creator", "creator_id"),
    ("Spend", "affiliate_id", "Affiliate", "affiliate_id"),
    ("Code Usage", "creator_id", "Creator", "creator_id"),
    ("Value Curve", "channel", "Channel", "channel"),
    ("Channel Quality", "channel", "Channel", "channel"),
    ("Incremental Cost", "channel", "Channel", "channel"),
]


# ---------------------------------------------------------------- writers
def column_block(table, name, kind, fmt=None, hidden=False, sort_by=None, is_key=False):
    lines = [f"\tcolumn {q(name)}", f"\t\tdataType: {TMDL_TYPE[kind]}"]
    if is_key:
        lines.append("\t\tisKey")
    if hidden:
        lines.append("\t\tisHidden")
    if fmt:
        lines.append(f"\t\tformatString: {fmt}")
    lines += [f"\t\tlineageTag: {tag(table, name)}", "\t\tsummarizeBy: none", f"\t\tsourceColumn: {name}"]
    if sort_by:
        lines.append(f"\t\tsortByColumn: {sort_by}")
    if kind == "date":
        lines += ["", "\t\tannotation UnderlyingDateTimeDataType = Date"]
    return "\n".join(lines) + "\n"


def m_block(lines):
    """Indent an M expression for a partition source."""
    return "\n".join("\t\t\t\t" + l for l in lines)


def write_csv_table(t):
    name, cols = t["name"], t["cols"]
    out = [f"table {q(name)}", f"\tlineageTag: {tag(name)}", ""]
    for c, kind, fmt in cols:
        out.append(column_block(name, c, kind, fmt, hidden=c in t["hidden"]))
    if any(s.startswith("Ranked") for s in t["extra"]):
        out.append(column_block(name, "rank", "int", "0"))
    csv_cols = [c for c, _, _ in cols]
    steps = [f'Source = Csv.Document(File.Contents(DataFolder & "{t["path"]}"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
             "Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),"]
    last = "Promoted"
    for s in t["extra"]:
        if s.startswith("WithDate"):
            steps.append(s + ",")
            last = "WithDate"
    types = ", ".join(f'{{"{c}", {M_TYPE[k]}}}' for c, k, _ in cols)
    steps.append(f"Selected = Table.SelectColumns({last}, {{{', '.join(json.dumps(c) for c in csv_cols)}}}),")
    steps.append(f'Typed = Table.TransformColumnTypes(Selected, {{{types}}}, "en-US")')
    final = "Typed"
    for s in t["extra"]:
        if s.startswith("Ranked"):
            steps[-1] += ","
            steps.append(s)
            final = "Ranked"
    out += [f"\tpartition {q(name)} = m", "\t\tmode: import", "\t\tsource =",
            m_block(["let"] + ["\t" + s for s in steps] + ["in", "\t" + final]), ""]
    return "\n".join(out)


def write_static(name, cols, rows, sort_by):
    out = [f"table {q(name)}", f"\tlineageTag: {tag(name)}", ""]
    for c, kind in cols:
        out.append(column_block(name, c, kind, hidden=c.endswith("_sort"), sort_by=sort_by.get(c)))
    typ = ", ".join(f"{c} = {'Int64.Type' if k == 'int' else 'text'}" for c, k in cols)
    vals = ", ".join("{" + ", ".join(json.dumps(v) for v in r) + "}" for r in rows)
    out += [f"\tpartition {q(name)} = m", "\t\tmode: import",
            f"\t\tsource = #table(type table [{typ}], {{{vals}}})", ""]
    return "\n".join(out)


def write_date():
    out = ["table Date", f"\tlineageTag: {tag('Date')}", "\tdataCategory: Time", ""]
    out.append(column_block("Date", "Date", "date", "dd mmm yyyy", is_key=True))
    out.append(column_block("Date", "Month", "text", sort_by="MonthKey"))
    out.append(column_block("Date", "MonthKey", "int", hidden=True))
    out.append(column_block("Date", "MonthStart", "date", "mmm yyyy"))
    out.append(column_block("Date", "Year", "int", "0"))
    out += ["\tpartition Date = m", "\t\tmode: import", "\t\tsource =", m_block([
        "let",
        "\tDates = List.Dates(#date(2024, 5, 1), Duration.Days(#date(2026, 10, 31) - #date(2024, 5, 1)) + 1, #duration(1, 0, 0, 0)),",
        "\tT = Table.FromList(Dates, Splitter.SplitByNothing(), type table [Date = date]),",
        '\tM = Table.AddColumn(T, "Month", each Date.ToText([Date], "MMM yyyy", "en-US"), type text),',
        '\tK = Table.AddColumn(M, "MonthKey", each Date.Year([Date]) * 100 + Date.Month([Date]), Int64.Type),',
        '\tS = Table.AddColumn(K, "MonthStart", each Date.StartOfMonth([Date]), type date),',
        '\tY = Table.AddColumn(S, "Year", each Date.Year([Date]), Int64.Type)',
        "in", "\tY"]), ""]
    return "\n".join(out)


def write_measures():
    out = ["table _Measures", f"\tlineageTag: {tag('_Measures')}", ""]
    for name, dax, fmt, folder in MEASURES:
        out += [f"\tmeasure {q(name)} = {dax}", f"\t\tformatString: {fmt}", f"\t\tdisplayFolder: {folder}",
                f"\t\tlineageTag: {tag('_Measures', name)}", ""]
    out.append(column_block("_Measures", "_", "text", hidden=True))
    out += ["\tpartition _Measures = m", "\t\tmode: import", "\t\tsource = #table(type table [_ = text], {})", ""]
    return "\n".join(out)


def main():
    if DEF.exists():
        shutil.rmtree(DEF)
    (DEF / "tables").mkdir(parents=True)
    (SM / "definition.pbism").write_text(json.dumps({"version": "4.2", "settings": {}}, indent=2), encoding="utf-8")

    names = []
    for t in TABLES:
        (DEF / "tables" / f"{t['name']}.tmdl").write_text(write_csv_table(t), encoding="utf-8")
        names.append(t["name"])
    for name, cols, rows, sort_by in STATIC:
        (DEF / "tables" / f"{name}.tmdl").write_text(write_static(name, cols, rows, sort_by), encoding="utf-8")
        names.append(name)
    (DEF / "tables" / "Date.tmdl").write_text(write_date(), encoding="utf-8")
    (DEF / "tables" / "_Measures.tmdl").write_text(write_measures(), encoding="utf-8")
    names += ["Date", "_Measures"]

    (DEF / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1606\n\n", encoding="utf-8")
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tsourceQueryCulture: en-US", "\tvalueFilterBehavior: independent", "\tdataAccessOptions",
             "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
             "annotation __PBI_TimeIntelligenceEnabled = 0", "",
             'annotation PBI_ProTooling = ["TMDLView_Desktop","DevMode"]', ""]
    model += [f"ref table {q(n)}" for n in names] + [""]
    (DEF / "model.tmdl").write_text("\n".join(model), encoding="utf-8")
    (DEF / "expressions.tmdl").write_text(
        f'expression DataFolder = "{DATA_FOLDER}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f"\tlineageTag: {tag('DataFolder')}\n\n\tannotation PBI_ResultType = Text\n\n", encoding="utf-8")
    rels = []
    for i, (ft, fc, tt, tc) in enumerate(RELATIONSHIPS, 1):
        rels += [f"relationship rel_{i:02d}", f"\tfromColumn: {q(ft)}.{q(fc)}", f"\ttoColumn: {q(tt)}.{q(tc)}", ""]
    (DEF / "relationships.tmdl").write_text("\n".join(rels), encoding="utf-8")
    print(f"semantic model: {len(names)} tables, {len(MEASURES)} measures, {len(RELATIONSHIPS)} relationships")


if __name__ == "__main__":
    main()
