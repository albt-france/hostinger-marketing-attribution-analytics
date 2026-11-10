-- =====================================================================
-- 02 · Conversion paths
-- The ordered list of channels each buyer touched in the 30 days before buying,
-- with path length and time to convert. Also builds the path table used by
-- the Markov attribution model (converting AND non-converting paths).
-- SIMULATED data.
-- =====================================================================

-- Consecutive visits through the same channel ("Direct > Direct") are collapsed
-- into one step: they say nothing new about which channel played a role.
CREATE OR REPLACE TABLE order_paths AS
WITH steps AS (
    SELECT
        order_id,
        order_ts,
        ts,
        touch_rank,
        n_touches,
        channel,
        LAG(channel) OVER (PARTITION BY order_id ORDER BY touch_rank) AS previous_channel
    FROM order_touchpoints
)
SELECT
    order_id,
    STRING_AGG(channel, ' > ' ORDER BY touch_rank)
        FILTER (WHERE previous_channel IS NULL OR channel <> previous_channel)   AS path,
    MAX(n_touches)                                                             AS path_length,
    date_diff('minute', MIN(ts), MAX(order_ts)) / 1440.0                       AS days_to_convert
FROM steps
GROUP BY order_id;


-- output: top_paths
WITH totals AS (SELECT COUNT(*) AS all_orders FROM order_paths)
SELECT
    path,
    COUNT(*)                                     AS orders,
    COUNT(*) / ANY_VALUE(t.all_orders)           AS share_of_orders,
    AVG(path_length)                             AS avg_touchpoints,
    AVG(days_to_convert)                         AS avg_days_to_convert
FROM order_paths
CROSS JOIN totals AS t
GROUP BY path
ORDER BY orders DESC
LIMIT 15;


-- output: path_length_dist
SELECT
    CASE WHEN path_length >= 5 THEN '5+' ELSE CAST(path_length AS VARCHAR) END  AS touchpoints,
    COUNT(*)                                                                     AS orders,
    COUNT(*) / SUM(COUNT(*)) OVER ()                                             AS share_of_orders
FROM order_paths
GROUP BY 1
ORDER BY 1;


-- output: days_to_convert_dist
SELECT
    CASE
        WHEN days_to_convert < 1  THEN '1 · same day'
        WHEN days_to_convert < 4  THEN '2 · 1-3 days'
        WHEN days_to_convert < 8  THEN '3 · 4-7 days'
        WHEN days_to_convert < 15 THEN '4 · 8-14 days'
        ELSE                           '5 · 15-30 days'
    END                                   AS days_to_convert,
    COUNT(*)                              AS orders,
    COUNT(*) / SUM(COUNT(*)) OVER ()      AS share_of_orders
FROM order_paths
GROUP BY 1
ORDER BY 1;


-- output: markov_paths
-- Every prospect's path: buyers (touchpoints of the 30 days before the order)
-- and non-buyers (all their touchpoints). Aggregated: one row per distinct path.
WITH buyer_touches AS (
    SELECT o.user_id, ot.touch_rank, ot.channel, 1 AS converted
    FROM order_touchpoints AS ot
    JOIN orders AS o USING (order_id)
),
non_buyer_touches AS (
    SELECT
        t.user_id,
        ROW_NUMBER() OVER (PARTITION BY t.user_id ORDER BY t.ts, t.touch_id) AS touch_rank,
        t.channel,
        0 AS converted
    FROM touchpoints_clean AS t
    WHERE NOT EXISTS (SELECT 1 FROM orders AS o WHERE o.user_id = t.user_id)
),
all_touches AS (
    SELECT * FROM buyer_touches
    UNION ALL
    SELECT * FROM non_buyer_touches
),
collapsed AS (
    SELECT
        *,
        LAG(channel) OVER (PARTITION BY user_id ORDER BY touch_rank) AS previous_channel
    FROM all_touches
),
user_paths AS (
    SELECT
        user_id,
        MAX(converted)                                                   AS converted,
        STRING_AGG(channel, ' > ' ORDER BY touch_rank)
            FILTER (WHERE previous_channel IS NULL OR channel <> previous_channel) AS path
    FROM collapsed
    GROUP BY user_id
)
SELECT
    path,
    SUM(converted)          AS conversions,
    SUM(1 - converted)      AS non_conversions
FROM user_paths
GROUP BY path
ORDER BY conversions + non_conversions DESC;
