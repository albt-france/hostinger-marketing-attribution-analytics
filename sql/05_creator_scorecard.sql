-- =====================================================================
-- 05 · Creator & affiliate scorecards
-- What each creator and affiliate really brings once leaked codes, refunds
-- and "already decided" buyers are taken out.
-- SIMULATED data.
-- =====================================================================

-- creator_orders: every order a creator can claim, by code and/or by link
CREATE OR REPLACE TABLE creator_orders AS
WITH code_orders AS (
    SELECT o.order_id, c.creator_id
    FROM orders AS o
    JOIN creators AS c ON o.coupon_code = c.promo_code
),
link_orders AS (
    -- the creator's tracked link is the last click within the 30-day window
    SELECT order_id, creator_id
    FROM order_touchpoints
    WHERE channel = 'Influencers' AND touch_rank = n_touches
),
claims AS (
    SELECT order_id, creator_id, TRUE AS via_code, FALSE AS via_link FROM code_orders
    UNION ALL
    SELECT order_id, creator_id, FALSE, TRUE FROM link_orders
)
SELECT
    c.order_id,
    c.creator_id,
    BOOL_OR(c.via_code)  AS via_code,
    BOOL_OR(c.via_link)  AS via_link
FROM claims AS c
GROUP BY ALL;


-- code_leak_check: a code use looks leaked when the buyer arrived from a coupon
-- site AND the creator had published no video in the previous 21 days
CREATE OR REPLACE TABLE code_leak_check AS
SELECT
    co.order_id,
    co.creator_id,
    v.order_ts,
    v.last_click_channel = 'Affiliates - Coupon'                 AS via_coupon_site,
    NOT EXISTS (
        SELECT 1
        FROM video_dates AS vd
        WHERE vd.creator_id = co.creator_id
          AND CAST(vd.video_date AS DATE) BETWEEN CAST(v.order_ts AS DATE) - 21 AND CAST(v.order_ts AS DATE)
    )                                                            AS no_recent_video
FROM creator_orders AS co
JOIN order_value AS v USING (order_id)
WHERE co.via_code;


-- output: creator_scorecard
WITH cost AS (
    SELECT creator_id, SUM(spend_eur) AS cost_eur
    FROM spend
    WHERE channel = 'Influencers'
    GROUP BY 1
),
videos AS (
    SELECT creator_id, COUNT(*) AS videos FROM video_dates GROUP BY 1
),
orders_scored AS (
    SELECT
        co.creator_id,
        co.order_id,
        co.via_code,
        co.via_link,
        COALESCE(lc.via_coupon_site AND lc.no_recent_video, FALSE)   AS is_leaked,
        v.is_refunded,
        v.mature_30d,
        v.expected_value_12m
    FROM creator_orders AS co
    JOIN order_value AS v USING (order_id)
    LEFT JOIN code_leak_check AS lc USING (order_id, creator_id)
),
per_creator AS (
    SELECT
        creator_id,
        COUNT(*)                                                     AS claimed_orders,
        COUNT(*) FILTER (WHERE via_link)                             AS link_orders,
        COUNT(*) FILTER (WHERE via_code)                             AS code_orders,
        COUNT(*) FILTER (WHERE is_leaked)                            AS leaked_code_orders,
        AVG(CASE WHEN is_refunded THEN 1.0 ELSE 0.0 END) FILTER (WHERE mature_30d) AS refund_rate_30d,
        SUM(expected_value_12m) FILTER (WHERE NOT is_leaked)         AS value_12m_genuine
    FROM orders_scored
    GROUP BY 1
)
SELECT
    c.creator_id,
    c.creator_name,
    c.platform,
    c.niche,
    c.main_country,
    c.audience_size,
    c.fee_model,
    COALESCE(vd.videos, 0)                                           AS videos,
    COALESCE(k.cost_eur, 0)                                          AS cost_eur,
    COALESCE(p.claimed_orders, 0)                                    AS claimed_orders,
    COALESCE(p.link_orders, 0)                                       AS link_orders,
    COALESCE(p.code_orders, 0)                                       AS code_orders,
    COALESCE(p.leaked_code_orders, 0)                                AS leaked_code_orders,
    p.leaked_code_orders / NULLIF(p.code_orders, 0)                  AS leaked_share_of_code,
    p.refund_rate_30d,
    COALESCE(p.claimed_orders, 0) - COALESCE(p.leaked_code_orders, 0) AS genuine_orders,
    k.cost_eur / NULLIF(p.claimed_orders - p.leaked_code_orders, 0)  AS cost_per_genuine_order,
    p.value_12m_genuine,
    (p.value_12m_genuine - k.cost_eur) / NULLIF(k.cost_eur, 0)       AS roi_12m
FROM creators AS c
LEFT JOIN cost        AS k  USING (creator_id)
LEFT JOIN videos      AS vd USING (creator_id)
LEFT JOIN per_creator AS p  USING (creator_id)
ORDER BY cost_eur DESC;


-- output: code_usage_weekly
-- Weekly code uses per creator next to video weeks: uses without a video = leak signal.
WITH weeks AS (
    SELECT CAST(range AS DATE) AS week
    FROM range(DATE '2024-04-29', DATE '2026-11-02', INTERVAL 7 DAY)
),
uses AS (
    SELECT
        creator_id,
        CAST(date_trunc('week', order_ts) AS DATE)              AS week,
        COUNT(*)                                                AS code_orders,
        COUNT(*) FILTER (WHERE via_coupon_site AND no_recent_video) AS leaked_code_orders
    FROM code_leak_check
    GROUP BY ALL
),
video_weeks AS (
    SELECT creator_id, CAST(date_trunc('week', video_date) AS DATE) AS week, COUNT(*) AS videos
    FROM video_dates
    GROUP BY ALL
)
SELECT
    c.creator_id,
    w.week,
    COALESCE(u.code_orders, 0)          AS code_orders,
    COALESCE(u.leaked_code_orders, 0)   AS leaked_code_orders,
    COALESCE(v.videos, 0)               AS videos
FROM creators AS c
CROSS JOIN weeks AS w
LEFT JOIN uses        AS u ON u.creator_id = c.creator_id AND u.week = w.week
LEFT JOIN video_weeks AS v ON v.creator_id = c.creator_id AND v.week = w.week
ORDER BY c.creator_id, w.week;


-- output: affiliate_scorecard
-- Orders where the affiliate is the last click (the rule commissions are paid on).
WITH aff_orders AS (
    SELECT
        ot.order_id,
        ot.affiliate_id,
        ot.n_touches,
        -- buyer had already started a cart on an earlier visit = already decided
        EXISTS (
            SELECT 1 FROM order_touchpoints AS e
            WHERE e.order_id = ot.order_id AND e.touch_rank < ot.touch_rank AND e.cart_started
        )                                                        AS cart_before_click
    FROM order_touchpoints AS ot
    WHERE ot.channel LIKE 'Affiliates%' AND ot.touch_rank = ot.n_touches
),
commission AS (
    SELECT affiliate_id, SUM(spend_eur) AS commission_eur
    FROM spend
    WHERE affiliate_id IS NOT NULL
    GROUP BY 1
)
SELECT
    a.affiliate_id,
    a.type,
    a.main_country,
    a.commission_rate,
    COUNT(ao.order_id)                                                   AS last_click_orders,
    COALESCE(ANY_VALUE(c.commission_eur), 0)                             AS commission_eur,
    ANY_VALUE(c.commission_eur) / NULLIF(COUNT(ao.order_id), 0)          AS commission_per_order,
    AVG(CASE WHEN v.is_refunded THEN 1.0 ELSE 0.0 END) FILTER (WHERE v.mature_30d) AS refund_rate_30d,
    AVG(CASE WHEN ao.cart_before_click THEN 1.0 ELSE 0.0 END)            AS share_cart_already_started,
    AVG(CASE WHEN ao.n_touches > 1 THEN 1.0 ELSE 0.0 END)                AS share_with_earlier_channel,
    AVG(v.expected_value_12m)                                            AS expected_value_12m_per_order
FROM affiliates AS a
LEFT JOIN aff_orders  AS ao USING (affiliate_id)
LEFT JOIN order_value AS v  USING (order_id)
LEFT JOIN commission  AS c  USING (affiliate_id)
GROUP BY a.affiliate_id, a.type, a.main_country, a.commission_rate
ORDER BY commission_eur DESC;
