"""Write the Power BI semantic model (TMDL) for powerbi/HostingerAttribution.SemanticModel.

Star schema:
  marketing facts  Orders (one row per order: paid, refunded, renewals, value), Attribution Credits
                   (order x model x channel), Spend (day x channel x campaign)
  product facts    Reach Users (one row per Reach user: funnel, adoption, retention), Experiment Users
                   (one row per user in the A/B test), Referrals (one row per referral), Product Daily
                   (product events rolled up per day, event, platform and country)
  dimensions       Date, Channel, Country (shared by both parts), Attribution Model, Creator, Affiliate,
                   Product, AB Variant
  outputs          small tables written by SQL / the notebooks (paths, value curve, geo test, funnel, ...)

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


def csv_table(name, path, cols, extra_steps=None, hidden=(), sort_by=None):
    return {"name": name, "path": path, "cols": cols, "extra": extra_steps or [], "hidden": set(hidden),
            "sort": sort_by or {}}


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
    # ------------------------------------------------------------ product part (SIMULATED, sql/08-11 + product notebook)
    csv_table("Reach Users", r"output\reach_users.csv", [
        ("user_id", "int", "0"), ("onboarding_date", "date", "dd mmm yyyy"), ("onboarding_month", "date", "mmm yyyy"),
        ("source", "text", None), ("platform", "text", None), ("country", "text", None),
        ("hosting_product", "text", None), ("channel", "text", None), ("contacts", "int", INT),
        ("reached_template", "bool", None), ("reached_contacts", "bool", None), ("reached_campaign", "bool", None),
        ("days_to_first_campaign", "num", "0.0"), ("activated_7d", "bool", None), ("funnel_complete", "bool", None),
        ("adoption_group", "text", None), ("mature_d7", "bool", None), ("mature_d30", "bool", None),
        ("mature_60d", "bool", None), ("retained_d7", "bool", None), ("retained_d30", "bool", None),
        ("active_weeks_first_13", "int", "0"), ("upgraded_60d", "bool", None)],
        hidden=["user_id"]),
    csv_table("Experiment Users", r"output\ab_users.csv", [
        ("user_id", "int", "0"), ("variant", "text", None), ("assigned_date", "date", "dd mmm yyyy"),
        ("platform", "text", None), ("country", "text", None), ("channel", "text", None), ("source", "text", None),
        ("reached_template", "bool", None), ("reached_contacts", "bool", None), ("activated_7d", "bool", None),
        ("retained_d30", "bool", None), ("mature_d30", "bool", None), ("upgraded_60d", "bool", None),
        ("mature_60d", "bool", None)],
        hidden=["user_id"]),
    csv_table("Referrals", r"output\referral_detail.csv", [
        ("referral_id", "int", "0"), ("referral_date", "date", "dd mmm yyyy"), ("referral_month", "date", "mmm yyyy"),
        ("country", "text", None), ("channel", "text", None), ("hosting_product", "text", None),
        ("plan_months", "int", "0"), ("reward_status", "text", None), ("reward_band", "text", None),
        ("reward_band_order", "int", "0"), ("paid_amount_eur", "num", EUR2), ("is_refunded", "bool", None),
        ("expected_value_12m", "num", EUR2), ("reward_cost_eur", "num", EUR2), ("discount_cost_eur", "num", EUR2),
        ("programme_cost_eur", "num", EUR2), ("net_value_after_cost_eur", "num", EUR2), ("fraud_check", "text", None),
        ("flag_self_referral", "bool", None), ("same_payment_card", "bool", None), ("same_device", "bool", None),
        ("minutes_link_to_signup", "num", "#,0.0")],
        hidden=["referral_id", "reward_band_order"], sort_by={"reward_band": "reward_band_order"}),
    csv_table("Product Daily", r"output\product_daily.csv", [
        ("date", "date", "dd mmm yyyy"), ("product", "text", None), ("event_name", "text", None),
        ("platform", "text", None), ("country", "text", None), ("users", "int", INT), ("events", "int", INT)]),
    csv_table("Reach Funnel", r"output\reach_funnel.csv", [
        ("step_order", "int", "0"), ("step", "text", None), ("users", "int", INT),
        ("conversion_from_start", "num", PCT0), ("conversion_from_previous", "num", PCT0), ("users_lost", "int", INT),
        ("median_hours_from_previous", "num", "#,0")],
        hidden=["step_order"], sort_by={"step": "step_order"}),
    csv_table("Reach Adoption by Channel", r"output\reach_adoption_by_channel.csv", [
        ("channel", "text", None), ("new_customers", "int", INT), ("started_reach_rate", "num", PCT0),
        ("activated_per_customer", "num", PCT1), ("activated_7d_rate_of_starters", "num", PCT0)]),
    csv_table("Aha Retention", r"output\aha_retention.csv", [
        ("bucket_order", "int", "0"), ("first_campaign", "text", None), ("users", "int", INT),
        ("share_of_users", "num", PCT0), ("retention_d30", "num", PCT0), ("upgrade_rate_60d", "num", PCT0)],
        hidden=["bucket_order"], sort_by={"first_campaign": "bucket_order"}),
    csv_table("Adoption Curve", r"output\adoption_curve.csv", [
        ("adoption_group", "text", None), ("week", "int", "0"), ("users_observed", "int", INT), ("retention", "num", PCT0)]),
    csv_table("AB Daily", r"output\ab_daily.csv", [
        ("assigned_date", "date", "dd mmm"), ("control_users", "int", INT), ("treatment_users", "int", INT),
        ("users", "int", INT), ("treatment_share", "num", PCT0), ("srm_z", "num", "0.0")]),
    csv_table("AB Result", r"output\ab_result.csv", [
        ("metric", "text", None), ("control", "num", PCT1), ("treatment", "num", PCT1), ("diff", "num", "+0.0%;-0.0%;0.0%"),
        ("ci_low", "num", "+0.0%;-0.0%;0.0%"), ("ci_high", "num", "+0.0%;-0.0%;0.0%"), ("p_value", "num", "0.000"),
        ("p_holm", "num", "0.000"), ("rank", "int", "0")],
        hidden=["rank"], sort_by={"metric": "rank"}),
    csv_table("AB Power", r"output\ab_power.csv", [
        ("mde_points", "num", "0.00"), ("users_per_arm", "int", INT), ("weeks_needed", "num", "0.0")]),
    csv_table("Mail AI Lift", r"output\mail_ai_lift.csv", [
        ("segment", "text", None), ("metric", "text", None), ("users", "int", INT), ("did_lift", "num", "+0.0%;-0.0%;0.0%"),
        ("ci_low", "num", "+0.0%;-0.0%;0.0%"), ("ci_high", "num", "+0.0%;-0.0%;0.0%")]),
    csv_table("Referral Bands", r"output\referral_by_band.csv", [
        ("reward_band_order", "int", "0"), ("reward_band", "text", None), ("referrals", "int", INT),
        ("flagged_self_referrals", "int", INT), ("avg_plan_months", "num", "0"), ("refund_rate", "num", PCT1),
        ("programme_cost_eur", "num", EUR0), ("cost_on_self_referrals_eur", "num", EUR0),
        ("value_12m_clean_eur", "num", EUR0), ("break_even_incrementality", "num", PCT0)],
        hidden=["reward_band_order"], sort_by={"reward_band": "reward_band_order"}),
    csv_table("Referral Scenarios", r"output\referral_scenarios.csv", [
        ("reward_rate", "num", PCT0), ("controls", "text", None), ("incrementality", "num", PCT0),
        ("elasticity", "num", "0.0"), ("genuine_referrals_year", "num", INT), ("self_referrals_year", "num", INT),
        ("cost_year_eur", "num", EUR0), ("incremental_value_year_eur", "num", EUR0), ("net_value_year_eur", "num", EUR0)]),
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
    ("Product", [("product", "text"), ("product_name", "text"), ("product_sort", "int")],
     [("Reach", "Hostinger Reach (AI e-mail marketing)", 1), ("Mail", "Hostinger Mail (business e-mail)", 2),
      ("Referral", "Customer referral programme", 3)], {"product": "product_sort"}),
    ("AB Variant", [("variant", "text"), ("variant_label", "text")],
     [("control", "Blank editor (control)"), ("treatment", "AI-prefilled first campaign")], {}),
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
    # ------------------------------------------------------------ product (SIMULATED)
    # funnel: completed 30-day windows only (censoring-safe)
    ("Reach Starters", "CALCULATE ( COUNTROWS ( 'Reach Users' ), 'Reach Users'[funnel_complete] = TRUE () )", INT, "Product\\Funnel"),
    ("Template Rate", "DIVIDE ( CALCULATE ( COUNTROWS ( 'Reach Users' ), 'Reach Users'[funnel_complete] = TRUE (), 'Reach Users'[reached_template] = TRUE () ), [Reach Starters] )", PCT0, "Product\\Funnel"),
    ("Contacts Rate", "DIVIDE ( CALCULATE ( COUNTROWS ( 'Reach Users' ), 'Reach Users'[funnel_complete] = TRUE (), 'Reach Users'[reached_contacts] = TRUE () ), [Reach Starters] )", PCT0, "Product\\Funnel"),
    ("First Campaign Rate", "DIVIDE ( CALCULATE ( COUNTROWS ( 'Reach Users' ), 'Reach Users'[funnel_complete] = TRUE (), 'Reach Users'[reached_campaign] = TRUE () ), [Reach Starters] )", PCT0, "Product\\Funnel"),
    ("Contacts Step Conversion", "DIVIDE ( [Contacts Rate], [Template Rate] )", PCT0, "Product\\Funnel"),
    # adoption and retention
    ("Activation Rate 7d", "DIVIDE ( CALCULATE ( COUNTROWS ( 'Reach Users' ), 'Reach Users'[funnel_complete] = TRUE (), 'Reach Users'[activated_7d] = TRUE () ), [Reach Starters] )", PCT1, "Product\\Adoption"),
    ("Retention D7", "DIVIDE ( CALCULATE ( COUNTROWS ( 'Reach Users' ), 'Reach Users'[mature_d7] = TRUE (), 'Reach Users'[retained_d7] = TRUE () ), CALCULATE ( COUNTROWS ( 'Reach Users' ), 'Reach Users'[mature_d7] = TRUE () ) )", PCT0, "Product\\Adoption"),
    ("Retention D30", "DIVIDE ( CALCULATE ( COUNTROWS ( 'Reach Users' ), 'Reach Users'[mature_d30] = TRUE (), 'Reach Users'[retained_d30] = TRUE () ), CALCULATE ( COUNTROWS ( 'Reach Users' ), 'Reach Users'[mature_d30] = TRUE () ) )", PCT0, "Product\\Adoption"),
    ("Retention D30 Adopters", "CALCULATE ( [Retention D30], 'Reach Users'[activated_7d] = TRUE () )", PCT0, "Product\\Adoption"),
    ("Upgrade Rate 60d", "DIVIDE ( CALCULATE ( COUNTROWS ( 'Reach Users' ), 'Reach Users'[mature_60d] = TRUE (), 'Reach Users'[upgraded_60d] = TRUE () ), CALCULATE ( COUNTROWS ( 'Reach Users' ), 'Reach Users'[mature_60d] = TRUE () ) )", PCT1, "Product\\Adoption"),
    ("Activated per 100 Customers", "AVERAGE ( 'Reach Adoption by Channel'[activated_per_customer] ) * 100", "0.0", "Product\\Adoption"),
    ("Retention by Week", "AVERAGE ( 'Adoption Curve'[retention] )", PCT0, "Product\\Adoption"),
    ("Mail AI Lift", "AVERAGE ( 'Mail AI Lift'[did_lift] )", "+0.0%;-0.0%;0.0%", "Product\\Adoption"),
    # A/B test: the user-level table, without 14 July (sample-ratio mismatch, see the notebook)
    ("Test Users", "CALCULATE ( COUNTROWS ( 'Experiment Users' ), 'Experiment Users'[assigned_date] <> DATE ( 2026, 7, 14 ) )", INT, "Product\\A/B test"),
    ("Test Activation Rate", "DIVIDE ( CALCULATE ( COUNTROWS ( 'Experiment Users' ), 'Experiment Users'[assigned_date] <> DATE ( 2026, 7, 14 ), 'Experiment Users'[activated_7d] = TRUE () ), [Test Users] )", PCT1, "Product\\A/B test"),
    ("Control Activation", "CALCULATE ( [Test Activation Rate], 'AB Variant'[variant] = \"control\" )", PCT1, "Product\\A/B test"),
    ("Treatment Activation", "CALCULATE ( [Test Activation Rate], 'AB Variant'[variant] = \"treatment\" )", PCT1, "Product\\A/B test"),
    ("Test Effect", "[Treatment Activation] - [Control Activation]", "+0.0%;-0.0%;0.0%", "Product\\A/B test"),
    ("Assigned Users All Days", "COUNTROWS ( 'Experiment Users' )", INT, "Product\\A/B test"),
    ("Control Users per Day", "SUM ( 'AB Daily'[control_users] )", INT, "Product\\A/B test"),
    ("Treatment Users per Day", "SUM ( 'AB Daily'[treatment_users] )", INT, "Product\\A/B test"),
    ("Users per Arm Needed", "SUM ( 'AB Power'[users_per_arm] )", INT, "Product\\A/B test"),
    # referral programme
    ("Referral Count", "COUNTROWS ( Referrals )", INT, "Product\\Referral"),
    ("Referral Programme Cost", "SUM ( Referrals[programme_cost_eur] )", EUR0, "Product\\Referral"),
    ("Referral Reward Cost", "SUM ( Referrals[reward_cost_eur] )", EUR0, "Product\\Referral"),
    ("Referral Value 12m Clean", "CALCULATE ( SUM ( Referrals[expected_value_12m] ), Referrals[flag_self_referral] = FALSE () )", EUR0, "Product\\Referral"),
    ("Break-even Incrementality", "DIVIDE ( [Referral Programme Cost], [Referral Value 12m Clean] )", PCT0, "Product\\Referral"),
    ("Self-referral Count", "CALCULATE ( [Referral Count], Referrals[flag_self_referral] = TRUE () )", INT, "Product\\Referral"),
    ("Self-referral Share", "DIVIDE ( [Self-referral Count], [Referral Count] )", PCT1, "Product\\Referral"),
    ("Self-referral Cost Share", "DIVIDE ( CALCULATE ( [Referral Programme Cost], Referrals[flag_self_referral] = TRUE () ), [Referral Programme Cost] )", PCT0, "Product\\Referral"),
    ("Median Minutes Link to Sign-up", "MEDIAN ( Referrals[minutes_link_to_signup] )", "#,0", "Product\\Referral"),
    ("Clean Referrals", "CALCULATE ( [Referral Count], Referrals[flag_self_referral] = FALSE () )", INT, "Product\\Referral"),
    ("Scenario Net Value", "SUM ( 'Referral Scenarios'[net_value_year_eur] )", EUR0, "Product\\Referral"),
    ("Band Programme Cost", "SUM ( 'Referral Bands'[programme_cost_eur] )", EUR0, "Product\\Referral"),
    ("Band Value 12m", "SUM ( 'Referral Bands'[value_12m_clean_eur] )", EUR0, "Product\\Referral"),
    ("Product Events", "SUM ( 'Product Daily'[events] )", INT, "Product\\Events"),
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
    # product part: same Date, Channel and Country dimensions as the marketing part
    ("Reach Users", "onboarding_date", "Date", "Date"),
    ("Reach Users", "country", "Country", "country"),
    ("Reach Users", "channel", "Channel", "channel"),
    ("Experiment Users", "variant", "AB Variant", "variant"),
    ("Experiment Users", "assigned_date", "Date", "Date"),
    ("Experiment Users", "country", "Country", "country"),
    ("Referrals", "referral_date", "Date", "Date"),
    ("Referrals", "country", "Country", "country"),
    ("Referrals", "channel", "Channel", "channel"),
    ("Product Daily", "date", "Date", "Date"),
    ("Product Daily", "product", "Product", "product"),
    ("Product Daily", "country", "Country", "country"),
    ("Reach Adoption by Channel", "channel", "Channel", "channel"),
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
        out.append(column_block(name, c, kind, fmt, hidden=c in t["hidden"], sort_by=t["sort"].get(c)))
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
