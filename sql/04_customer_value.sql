-- =====================================================================
-- 04 · Customer value
-- Net value of each order = paid - refunded + renewals, at 30 days, 12 and
-- 24 months, and the cumulative value curve by acquisition channel.
--
-- Right-censoring: an order placed in September 2026 cannot have a 12-month
-- value yet. An order only counts at horizon k once k months have fully
-- passed before the end of the data (31 Oct 2026). Without this rule, recent
-- cohorts would drag every average down.
-- SIMULATED data.
-- =====================================================================

-- order_value: one row per order
CREATE OR REPLACE TABLE order_value AS
WITH params AS (
    SELECT TIMESTAMP '2026-10-31 23:59:59' AS observation_end
),
renewal_months AS (
    -- month index of each renewal: 1 for a monthly renewal, 12 for an annual plan, ...
    SELECT
        r.order_id,
        CAST(ROUND(date_diff('hour', o.ts, r.renewal_ts) / (24 * 30.4375)) AS INTEGER) AS month_k,
        r.amount
    FROM renewals AS r
    JOIN orders AS o USING (order_id)
),
renewal_value AS (
    SELECT
        order_id,
        SUM(amount) FILTER (WHERE month_k <= 12) AS renewal_12m,
        SUM(amount) FILTER (WHERE month_k <= 24) AS renewal_24m
    FROM renewal_months
    GROUP BY order_id
),
first_renewal AS (
    -- outcome of the first renewal decision (end of the term, or month 1 for monthly plans)
    SELECT order_id, ARG_MIN(renewed, renewal_ts) AS renewed_first_time
    FROM renewals
    GROUP BY order_id
),
base AS (
    SELECT
        o.order_id,
        o.ts                                                        AS order_ts,
        CAST(date_trunc('month', o.ts) AS DATE)                     AS cohort_month,
        o.country,
        o.product,
        o.plan_months,
        o.coupon_code,
        o.paid_amount_eur,
        COALESCE(r.amount, 0)                                       AS refunded_eur,
        r.order_id IS NOT NULL                                      AS is_refunded,
        COALESCE(rv.renewal_12m, 0)                                 AS renewal_12m,
        COALESCE(rv.renewal_24m, 0)                                 AS renewal_24m,
        fr.order_id IS NOT NULL                                     AS has_renewal_decision,
        COALESCE(fr.renewed_first_time, FALSE)                      AS renewed_first_time,
        f.first_click_channel,
        f.last_click_channel,
        -- maturity flags: has the horizon fully passed before the end of the data?
        o.ts + INTERVAL 30 DAY                     <= p.observation_end  AS mature_30d,
        o.ts + to_days(CAST(12 * 30.4375 AS INT) + 1) <= p.observation_end AS mature_12m,
        o.ts + to_days(CAST(24 * 30.4375 AS INT) + 1) <= p.observation_end AS mature_24m
    FROM orders AS o
    CROSS JOIN params AS p
    JOIN order_first_last AS f USING (order_id)
    LEFT JOIN refunds AS r USING (order_id)
    LEFT JOIN renewal_value AS rv USING (order_id)
    LEFT JOIN first_renewal AS fr USING (order_id)
),
segment_renewals AS (
    -- average 12-month renewal revenue of mature orders, per product x plan x channel:
    -- used to project the 12-month value of orders that are not mature yet
    SELECT product, plan_months, first_click_channel, AVG(renewal_12m) AS avg_renewal_12m
    FROM base
    WHERE mature_12m
    GROUP BY ALL
)
SELECT
    b.*,
    b.paid_amount_eur - b.refunded_eur                          AS net_value_30d,
    CASE WHEN b.mature_12m THEN b.paid_amount_eur - b.refunded_eur + b.renewal_12m END AS net_value_12m,
    CASE WHEN b.mature_24m THEN b.paid_amount_eur - b.refunded_eur + b.renewal_24m END AS net_value_24m,
    -- expected 12-month value: actual when mature, otherwise projected from the segment
    CASE
        WHEN b.mature_12m THEN b.paid_amount_eur - b.refunded_eur + b.renewal_12m
        WHEN b.is_refunded THEN 0
        ELSE b.paid_amount_eur + COALESCE(s.avg_renewal_12m, 0)
    END                                                          AS expected_value_12m
FROM base AS b
LEFT JOIN segment_renewals AS s USING (product, plan_months, first_click_channel);


-- output: order_value
SELECT * FROM order_value ORDER BY order_id;


-- value_curve: cumulative net value per order, k months after purchase,
-- by acquisition (first-click) channel, censoring-safe
CREATE OR REPLACE TABLE value_curve AS
WITH params AS (
    SELECT TIMESTAMP '2026-10-31 23:59:59' AS observation_end
),
months AS (
    SELECT range AS k FROM range(0, 25)
),
renewal_months AS (
    SELECT
        r.order_id,
        CAST(ROUND(date_diff('hour', o.ts, r.renewal_ts) / (24 * 30.4375)) AS INTEGER) AS month_k,
        r.amount
    FROM renewals AS r
    JOIN orders AS o USING (order_id)
),
observable AS (
    -- order x month pairs that can be observed: month k has fully passed
    SELECT v.order_id, v.first_click_channel AS channel, v.net_value_30d, m.k
    FROM order_value AS v
    CROSS JOIN months AS m
    CROSS JOIN params AS p
    WHERE v.order_ts + to_days(CAST(m.k * 30.4375 AS INT) + 1) <= p.observation_end
      AND v.mature_30d
),
value_at_k AS (
    SELECT
        ob.channel,
        ob.k,
        ob.order_id,
        ob.net_value_30d + COALESCE(SUM(rm.amount), 0) AS cumulative_value
    FROM observable AS ob
    LEFT JOIN renewal_months AS rm
      ON rm.order_id = ob.order_id
     AND rm.month_k <= ob.k
    GROUP BY ob.channel, ob.k, ob.order_id, ob.net_value_30d
)
SELECT
    channel,
    k                       AS months_since_order,
    COUNT(*)                AS orders_observed,
    AVG(cumulative_value)   AS cumulative_value_per_order
FROM value_at_k
GROUP BY ALL;


-- output: value_curve
SELECT * FROM value_curve ORDER BY channel, months_since_order;


-- output: channel_quality
-- One row per acquisition channel: refunds, plan mix, renewals, LTV, CAC, payback.
WITH spend_by_channel AS (
    SELECT channel, SUM(spend_eur) AS spend_eur FROM spend GROUP BY channel
),
orders_by_channel AS (
    SELECT
        first_click_channel                                          AS channel,
        COUNT(*)                                                     AS orders,
        AVG(CASE WHEN is_refunded THEN 1.0 ELSE 0.0 END) FILTER (WHERE mature_30d) AS refund_rate_30d,
        AVG(CASE WHEN plan_months = 1  THEN 1.0 ELSE 0.0 END)        AS share_plan_1m,
        AVG(CASE WHEN plan_months = 12 THEN 1.0 ELSE 0.0 END)        AS share_plan_12m,
        AVG(CASE WHEN plan_months = 24 THEN 1.0 ELSE 0.0 END)        AS share_plan_24m,
        AVG(CASE WHEN plan_months = 48 THEN 1.0 ELSE 0.0 END)        AS share_plan_48m,
        AVG(plan_months)                                             AS avg_plan_months,
        AVG(net_value_30d) FILTER (WHERE mature_30d)                 AS net_value_30d,
        AVG(net_value_12m)                                           AS net_value_12m_mature,
        AVG(expected_value_12m)                                      AS expected_value_12m
    FROM order_value
    GROUP BY 1
),
renewal_rate AS (
    -- share of renewal decisions that ended in a renewal (all plan lengths)
    SELECT v.first_click_channel AS channel, AVG(CASE WHEN r.renewed THEN 1.0 ELSE 0.0 END) AS renewal_rate
    FROM renewals AS r
    JOIN order_value AS v USING (order_id)
    WHERE v.plan_months > 1                 -- term plans only: one decision per order
    GROUP BY 1
),
ltv AS (
    SELECT channel,
           MAX(cumulative_value_per_order) FILTER (WHERE months_since_order = 24) AS ltv_24m,
           MAX(orders_observed)            FILTER (WHERE months_since_order = 24) AS orders_in_ltv_24m
    FROM value_curve
    GROUP BY 1
),
payback AS (
    -- first month where the cumulative value per order covers the first-click CAC
    SELECT vc.channel, MIN(vc.months_since_order) AS payback_month
    FROM value_curve AS vc
    JOIN orders_by_channel AS o USING (channel)
    JOIN spend_by_channel AS s USING (channel)
    WHERE vc.cumulative_value_per_order >= s.spend_eur / o.orders
    GROUP BY 1
)
SELECT
    o.*,
    rr.renewal_rate,
    l.ltv_24m,
    l.orders_in_ltv_24m,
    s.spend_eur,
    s.spend_eur / NULLIF(o.orders, 0)       AS cac_first_click,
    p.payback_month
FROM orders_by_channel AS o
LEFT JOIN renewal_rate     AS rr USING (channel)
LEFT JOIN ltv              AS l  USING (channel)
LEFT JOIN spend_by_channel AS s  USING (channel)
LEFT JOIN payback          AS p  USING (channel)
ORDER BY o.orders DESC;
