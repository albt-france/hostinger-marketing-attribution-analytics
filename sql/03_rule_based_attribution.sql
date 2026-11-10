-- =====================================================================
-- 03 · Rule-based attribution
-- Splits each order (credit = 1) across the channels of its 30-day path with
-- five rules. The Markov (data-driven) model is added by the notebook.
--   Last click      100% to the last touchpoint
--   First click     100% to the first touchpoint
--   Linear          equal share to every touchpoint
--   Time decay      weight halves every 7 days before the order (half-life 7 days)
--   Position-based  40% first, 40% last, 20% shared by the middle ("40/20/40")
-- SIMULATED data.
-- =====================================================================

CREATE OR REPLACE TABLE attribution_rule_based AS
WITH touches AS (
    SELECT
        order_id,
        channel,
        touch_rank,
        n_touches,
        date_diff('second', ts, order_ts) / 86400.0  AS days_before_order
    FROM order_touchpoints
),
weights AS (
    SELECT
        order_id,
        channel,
        CASE WHEN touch_rank = n_touches THEN 1.0 ELSE 0.0 END  AS last_click,
        CASE WHEN touch_rank = 1         THEN 1.0 ELSE 0.0 END  AS first_click,
        1.0 / n_touches                                         AS linear,
        POWER(0.5, days_before_order / 7.0)                     AS decay_raw,
        CASE
            WHEN n_touches = 1                     THEN 1.0
            WHEN n_touches = 2                     THEN 0.5
            WHEN touch_rank IN (1, n_touches)      THEN 0.4
            ELSE 0.2 / (n_touches - 2)
        END                                                     AS position_based
    FROM touches
),
normalised AS (
    -- time-decay weights are rescaled so that each order still sums to 1
    SELECT
        * EXCLUDE (decay_raw),
        decay_raw / SUM(decay_raw) OVER (PARTITION BY order_id) AS time_decay
    FROM weights
),
long_format AS (
    UNPIVOT normalised
    ON last_click, first_click, linear, time_decay, position_based
    INTO NAME model VALUE credit
),
model_names AS (
    SELECT * FROM (VALUES
        ('last_click',     'Last click'),
        ('first_click',    'First click'),
        ('linear',         'Linear'),
        ('time_decay',     'Time decay'),
        ('position_based', 'Position 40/20/40')
    ) AS t(model_key, model)
),
tracked AS (
    SELECT
        l.order_id,
        m.model,
        l.channel,
        SUM(l.credit) AS credit                -- a channel can appear twice in a path
    FROM long_format AS l
    JOIN model_names AS m ON m.model_key = l.model
    WHERE l.credit > 0
    GROUP BY ALL
),
untracked AS (
    -- orders with no touchpoint keep their full credit, under every model
    SELECT o.order_id, m.model, 'Unattributed' AS channel, 1.0 AS credit
    FROM orders AS o
    CROSS JOIN model_names AS m
    WHERE NOT EXISTS (SELECT 1 FROM order_touchpoints AS ot WHERE ot.order_id = o.order_id)
)
SELECT * FROM tracked
UNION ALL
SELECT * FROM untracked;


-- output: attribution_rule_based
SELECT * FROM attribution_rule_based ORDER BY order_id, model, channel;


-- output: attribution_check
-- Sanity check: every order must carry exactly 1 credit under every model.
SELECT
    model,
    COUNT(DISTINCT order_id)                 AS orders,
    ROUND(SUM(credit), 4)                    AS total_credit,
    ROUND(MIN(order_total), 6)               AS min_credit_per_order,
    ROUND(MAX(order_total), 6)               AS max_credit_per_order
FROM (
    SELECT
        order_id, model, credit,
        SUM(credit) OVER (PARTITION BY order_id, model) AS order_total
    FROM attribution_rule_based
)
GROUP BY model
ORDER BY model;
