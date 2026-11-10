-- =====================================================================
-- 00 · Staging
-- Builds the clean base tables every other query reads from.
-- SIMULATED data. Engine: DuckDB (standard SQL, close to Snowflake / BigQuery).
-- =====================================================================

-- 1) touchpoints_clean
-- A tracking tag that fires twice creates the same visit twice, a few hundred
-- milliseconds apart. We keep the first event and drop any repeat of the same
-- user + channel + sub-channel within 2 seconds.
CREATE OR REPLACE TABLE touchpoints_clean AS
WITH ordered AS (
    SELECT
        *,
        LAG(ts) OVER (PARTITION BY user_id, channel, sub_channel ORDER BY ts, touch_id) AS previous_ts
    FROM touchpoints
)
SELECT * EXCLUDE (previous_ts)
FROM ordered
WHERE previous_ts IS NULL
   OR date_diff('millisecond', previous_ts, ts) > 2000;


-- 2) order_touchpoints
-- For each order, the buyer's clean touchpoints in the 30 days before the purchase
-- (30 days = Hostinger's affiliate cookie window, see data/SOURCES.md).
-- touch_rank = position in the path (1 = first), n_touches = path length.
CREATE OR REPLACE TABLE order_touchpoints AS
SELECT
    o.order_id,
    o.ts                                    AS order_ts,
    t.touch_id,
    t.ts,
    t.channel,
    t.sub_channel,
    t.creator_id,
    t.affiliate_id,
    t.cart_started,
    ROW_NUMBER() OVER (PARTITION BY o.order_id ORDER BY t.ts, t.touch_id) AS touch_rank,
    COUNT(*)     OVER (PARTITION BY o.order_id)                          AS n_touches
FROM orders AS o
JOIN touchpoints_clean AS t
  ON  t.user_id = o.user_id
  AND t.ts <= o.ts
  AND t.ts >= o.ts - INTERVAL 30 DAY;


-- 3) order_first_last
-- First-click and last-click channel of every order. Orders with no tracked
-- touchpoint (cookies declined) are labelled 'Unattributed' instead of being lost.
CREATE OR REPLACE TABLE order_first_last AS
WITH first_last AS (
    SELECT DISTINCT
        order_id,
        FIRST_VALUE(channel) OVER w AS first_click_channel,
        LAST_VALUE(channel)  OVER w AS last_click_channel
    FROM order_touchpoints
    WINDOW w AS (PARTITION BY order_id ORDER BY touch_rank
                 ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
)
SELECT
    o.order_id,
    COALESCE(fl.first_click_channel, 'Unattributed') AS first_click_channel,
    COALESCE(fl.last_click_channel,  'Unattributed') AS last_click_channel
FROM orders AS o
LEFT JOIN first_last AS fl USING (order_id);
