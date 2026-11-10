-- =====================================================================
-- 06 · Geo test: brand search ads switched off
-- Brand ads were paused for 12 weeks (2 Mar - 24 May 2026) in US, ES and ID
-- (test group) and kept on in FR, BR and IN (control group). Other budgets
-- were frozen during the test.
-- This query prepares the weekly panel for the difference-in-differences
-- analysis done in the notebook.
-- SIMULATED data.
-- =====================================================================

-- output: geo_weekly
WITH test_window AS (
    SELECT MIN(week) AS test_start, MAX(week) AS test_end
    FROM geo_test
    WHERE NOT brand_ads_on
),
brand_search_orders AS (
    -- orders whose 30-day path contains a brand search (paid ad or organic result):
    -- the only buyers brand ads can influence
    SELECT DISTINCT order_id
    FROM order_touchpoints
    WHERE channel = 'PPC Brand' OR sub_channel = 'Organic - brand'
),
weekly_orders AS (
    SELECT
        o.country,
        CAST(date_trunc('week', o.ts) AS DATE)                           AS week,
        COUNT(*)                                                         AS orders,
        COUNT(b.order_id)                                                AS brand_search_orders,
        COUNT(*) FILTER (WHERE f.last_click_channel = 'PPC Brand')       AS orders_last_click_brand_ads
    FROM orders AS o
    JOIN order_first_last AS f USING (order_id)
    LEFT JOIN brand_search_orders AS b USING (order_id)
    GROUP BY ALL
),
weekly_brand_clicks AS (
    SELECT
        country,
        CAST(date_trunc('week', ts) AS DATE)                             AS week,
        COUNT(*) FILTER (WHERE channel = 'PPC Brand')                    AS brand_ad_clicks,
        COUNT(*) FILTER (WHERE sub_channel = 'Organic - brand')          AS organic_brand_clicks
    FROM touchpoints_clean
    GROUP BY ALL
)
SELECT
    g.country,
    CAST(g.week AS DATE)                                                 AS week,
    g."group",
    g.brand_ads_on,
    CASE
        WHEN g.week <  t.test_start THEN 'pre'
        WHEN g.week <= t.test_end   THEN 'test'
        ELSE 'post'
    END                                                                  AS period,
    COALESCE(o.orders, 0)                                                AS orders,
    COALESCE(o.brand_search_orders, 0)                                   AS brand_search_orders,
    COALESCE(o.orders_last_click_brand_ads, 0)                           AS orders_last_click_brand_ads,
    COALESCE(c.brand_ad_clicks, 0)                                       AS brand_ad_clicks,
    COALESCE(c.organic_brand_clicks, 0)                                  AS organic_brand_clicks
FROM geo_test AS g
CROSS JOIN test_window AS t
LEFT JOIN weekly_orders       AS o ON o.country = g.country AND o.week = CAST(g.week AS DATE)
LEFT JOIN weekly_brand_clicks AS c ON c.country = g.country AND c.week = CAST(g.week AS DATE)
ORDER BY g.country, week;
