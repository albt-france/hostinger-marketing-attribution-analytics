-- =====================================================================
-- 11 · Referral programme economics and self-referral detection
-- Public terms (hostinger.com/referral-program, read 13 Nov 2026): the
-- referrer earns 20% of the friend's purchase (up to 450 USD), the friend
-- gets 20% off, the reward is paid once the friend has kept the plan 45+
-- days (30-day money-back guarantee + 15 days).
-- Cost of a referral   = reward (unless voided by a refund)
--                      + the friend's 20% discount (revenue given up)
-- Value of a referral  = the friend's 12-month net value (04_customer_value)
-- A referral only creates value if the friend would not have bought anyway,
-- so the key number is the break-even incrementality: cost / value.
-- Self-referral = a customer refers a second account of their own to get the
-- reward and the discount. Signals: same payment card fingerprint, or same
-- device and a sign-up minutes after the link was shared.
-- SIMULATED data.
-- =====================================================================

-- referral_detail: one row per referral, cost, value and fraud signals
CREATE OR REPLACE TABLE referral_detail AS
WITH base AS (
    SELECT
        r.referral_id,
        r.referrer_user_id,
        r.referee_user_id,
        r.referee_order_id                                                  AS order_id,
        CAST(r.purchase_ts AS DATE)                                         AS referral_date,
        CAST(date_trunc('month', r.purchase_ts) AS DATE)                    AS referral_month,
        r.country,
        r.reward_status,
        r.reward_eur,
        v.first_click_channel                                               AS channel,
        v.product                                                           AS hosting_product,
        v.plan_months,
        v.paid_amount_eur,
        v.is_refunded,
        v.renewal_12m,
        v.mature_12m,
        v.expected_value_12m,
        r.referee_payment_fingerprint = r.referrer_payment_fingerprint      AS same_payment_card,
        r.referee_device_id = r.referrer_device_id                          AS same_device,
        date_diff('second', r.link_shared_ts, r.signup_ts) / 60.0           AS minutes_link_to_signup,
        date_diff('second', r.signup_ts, r.purchase_ts) / 60.0              AS minutes_signup_to_purchase
    FROM referrals AS r
    JOIN order_value AS v ON v.order_id = r.referee_order_id
)
SELECT
    *,
    CASE WHEN reward_status = 'voided (refunded)' THEN 0 ELSE reward_eur END        AS reward_cost_eur,
    paid_amount_eur * friend_discount / (1 - friend_discount)                        AS discount_cost_eur,
    CASE
        WHEN same_payment_card                                 THEN 'Block: same payment card'
        WHEN same_device AND minutes_link_to_signup <= 10      THEN 'Block: same device, sign-up < 10 min'
        WHEN same_device                                       THEN 'Review: same device'
        ELSE 'Clean'
    END                                                                             AS fraud_check,
    same_payment_card OR (same_device AND minutes_link_to_signup <= 10)              AS flag_self_referral,
    -- referrer-level view: how many referrals, and how many of them flagged
    COUNT(*) OVER (PARTITION BY referrer_user_id)                                    AS referrer_referrals,
    CASE
        WHEN reward_eur < 5  THEN '< €5'
        WHEN reward_eur < 10 THEN '€5-10'
        WHEN reward_eur < 20 THEN '€10-20'
        WHEN reward_eur < 40 THEN '€20-40'
        ELSE '€40+'
    END                                                                             AS reward_band,
    CASE
        WHEN reward_eur < 5  THEN 1 WHEN reward_eur < 10 THEN 2 WHEN reward_eur < 20 THEN 3
        WHEN reward_eur < 40 THEN 4 ELSE 5
    END                                                                             AS reward_band_order
FROM base
CROSS JOIN (SELECT 0.20 AS friend_discount) AS t;


-- output: referral_detail
SELECT
    * EXCLUDE (friend_discount),
    reward_cost_eur + discount_cost_eur                                   AS programme_cost_eur,
    expected_value_12m - (reward_cost_eur + discount_cost_eur)            AS net_value_after_cost_eur
FROM referral_detail
ORDER BY referral_id;


-- output: referral_by_band
-- Cost vs value by reward size. Self-referrals are counted separately: their
-- value is not incremental (the customer was already buying).
SELECT
    reward_band_order,
    reward_band,
    COUNT(*)                                                                 AS referrals,
    COUNT(*) FILTER (WHERE flag_self_referral)                               AS flagged_self_referrals,
    AVG(plan_months)                                                         AS avg_plan_months,
    AVG(is_refunded::INT)                                                    AS refund_rate,
    SUM(reward_cost_eur + discount_cost_eur)                                 AS programme_cost_eur,
    SUM(reward_cost_eur + discount_cost_eur) FILTER (WHERE flag_self_referral) AS cost_on_self_referrals_eur,
    SUM(expected_value_12m) FILTER (WHERE NOT flag_self_referral)            AS value_12m_clean_eur,
    -- share of genuine friends who must be truly new customers for the band to pay back
    SUM(reward_cost_eur + discount_cost_eur)
        / NULLIF(SUM(expected_value_12m) FILTER (WHERE NOT flag_self_referral), 0) AS break_even_incrementality
FROM referral_detail
GROUP BY ALL
ORDER BY reward_band_order;


-- output: referral_fraud_rules
-- What each rule catches, and the reward it would have saved.
SELECT
    fraud_check,
    COUNT(*)                                                         AS referrals,
    COUNT(*) * 1.0 / SUM(COUNT(*)) OVER ()                           AS share_of_referrals,
    SUM(reward_cost_eur)                                             AS reward_eur,
    SUM(discount_cost_eur)                                           AS discount_eur,
    MEDIAN(minutes_link_to_signup)                                   AS median_minutes_link_to_signup,
    MEDIAN(minutes_signup_to_purchase)                               AS median_minutes_signup_to_purchase,
    COUNT(DISTINCT referrer_user_id)                                 AS referrers
FROM referral_detail
GROUP BY fraud_check
ORDER BY referrals DESC;


-- output: referral_quality
-- Are referred friends good customers? Compared with every customer acquired
-- through the same channels in the same period (orders since 15 May 2025).
WITH window_customers AS (
    SELECT
        v.*,
        d.referral_id IS NOT NULL AS is_referred
    FROM order_value AS v
    LEFT JOIN referral_detail AS d USING (order_id)
    WHERE v.order_ts >= TIMESTAMP '2025-05-15'
      AND v.first_click_channel IN ('Direct', 'PPC Brand', 'SEO')
      AND v.coupon_code IS NULL
)
SELECT
    CASE WHEN is_referred THEN 'Referred friends' ELSE 'Other customers, same channels' END AS customers,
    COUNT(*)                                             AS orders,
    AVG(paid_amount_eur)                                 AS avg_first_payment_eur,
    AVG(plan_months)                                     AS avg_plan_months,
    AVG(is_refunded::INT) FILTER (WHERE mature_30d)      AS refund_rate_30d,
    AVG(expected_value_12m)                              AS expected_value_12m_eur
FROM window_customers
GROUP BY ALL
ORDER BY customers DESC;
