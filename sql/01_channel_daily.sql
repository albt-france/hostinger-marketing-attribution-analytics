-- =====================================================================
-- 01 · Channel performance by day
-- Spend, clicks, last-click orders, revenue, CAC and 30-day ROAS for every
-- day x channel, including days with orders but no spend (and the reverse).
-- SIMULATED data.
-- =====================================================================

-- output: channel_daily
WITH calendar AS (
    -- one row per day: a date spine, so that days without spend still appear
    SELECT CAST(range AS DATE) AS date
    FROM range(DATE '2024-05-01', DATE '2026-11-01', INTERVAL 1 DAY)
),
channels AS (
    SELECT channel FROM spend
    UNION
    SELECT last_click_channel FROM order_first_last
),
spine AS (
    SELECT c.date, ch.channel
    FROM calendar AS c
    CROSS JOIN channels AS ch
),
daily_spend AS (
    SELECT
        CAST(date AS DATE)  AS date,
        channel,
        SUM(spend_eur)      AS spend_eur,
        SUM(clicks)         AS paid_clicks
    FROM spend
    GROUP BY ALL
),
daily_orders AS (
    -- refunds are joined before aggregating: one refund at most per order,
    -- so the join cannot duplicate order rows
    SELECT
        CAST(o.ts AS DATE)                              AS date,
        f.last_click_channel                            AS channel,
        COUNT(*)                                        AS orders,
        SUM(o.paid_amount_eur)                          AS gross_revenue_eur,
        SUM(o.paid_amount_eur - COALESCE(r.amount, 0))  AS net_revenue_30d_eur
    FROM orders AS o
    JOIN order_first_last AS f USING (order_id)
    LEFT JOIN refunds AS r USING (order_id)
    GROUP BY ALL
)
SELECT
    s.date,
    s.channel,
    COALESCE(sp.spend_eur, 0)            AS spend_eur,
    COALESCE(sp.paid_clicks, 0)          AS paid_clicks,
    COALESCE(o.orders, 0)                AS orders_last_click,
    COALESCE(o.gross_revenue_eur, 0)     AS gross_revenue_eur,
    COALESCE(o.net_revenue_30d_eur, 0)   AS net_revenue_30d_eur,
    -- NULLIF avoids a division by zero on days without orders or spend
    sp.spend_eur / NULLIF(o.orders, 0)                AS cac_last_click_eur,
    o.net_revenue_30d_eur / NULLIF(sp.spend_eur, 0)   AS roas_30d
FROM spine AS s
LEFT JOIN daily_spend  AS sp USING (date, channel)
LEFT JOIN daily_orders AS o  USING (date, channel)
ORDER BY s.date, s.channel;
