-- =====================================================================
-- 10 · A/B test: AI-prefilled first campaign vs blank editor
-- Experiment reach_onboarding_ai_prefill, 4 May - 23 Aug 2026 (16 weeks):
-- users who start Reach onboarding are split 50/50 between
--   control   = blank campaign editor (current experience)
--   treatment = first campaign pre-filled by AI (copy, layout, subject line)
-- Primary metric: first campaign sent within 7 days (activated_7d, the aha
-- moment from 09). Guardrails: day-30 retention, upgrade within 60 days.
-- This file prepares the data and the sample-ratio check; the statistics
-- (power, chi-square, z-test, bootstrap) are in the notebook.
-- SIMULATED data.
-- =====================================================================

-- ab_users: one row per assigned user with every metric of the test plan
CREATE OR REPLACE TABLE ab_users AS
SELECT
    x.experiment_id,
    x.user_id,
    x.variant,
    x.assigned_ts,
    CAST(x.assigned_ts AS DATE)            AS assigned_date,
    x.platform,
    u.country,
    u.channel,
    u.source,
    u.hosting_product,
    u.reached_template,
    u.reached_contacts,
    u.reached_campaign,
    u.activated_7d,
    u.retained_d30,
    u.mature_d30,
    u.upgraded_60d,
    u.mature_60d,
    u.days_to_first_campaign
FROM experiments AS x
JOIN reach_users AS u USING (user_id);


-- output: ab_users
SELECT * FROM ab_users ORDER BY assigned_ts, user_id;


-- output: ab_daily
-- Sample-ratio check by day: with a 50/50 split, the daily share in treatment
-- should stay close to 50%. z = (treatment - expected) / sqrt(n * 0.5 * 0.5).
-- A day with |z| > 3 points to an assignment or logging problem.
WITH daily AS (
    SELECT
        assigned_date,
        COUNT(*) FILTER (WHERE variant = 'control')                              AS control_users,
        COUNT(*) FILTER (WHERE variant = 'treatment')                            AS treatment_users,
        COUNT(*) FILTER (WHERE variant = 'control'   AND platform = 'Web - mobile') AS control_mobile,
        COUNT(*) FILTER (WHERE variant = 'treatment' AND platform = 'Web - mobile') AS treatment_mobile,
        COUNT(*)                                                                 AS users
    FROM ab_users
    GROUP BY assigned_date
)
SELECT
    *,
    treatment_users * 1.0 / users                                     AS treatment_share,
    (treatment_users - users * 0.5) / SQRT(users * 0.25)              AS srm_z,
    SUM(treatment_users) OVER w * 1.0 / SUM(users) OVER w             AS cumulative_treatment_share
FROM daily
WINDOW w AS (ORDER BY assigned_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
ORDER BY assigned_date;


-- output: ab_by_variant
-- Raw metrics per variant, all days (the notebook removes the day flagged by the
-- sample-ratio check before reading the effect).
SELECT
    variant,
    COUNT(*)                                                AS users,
    AVG(reached_template::INT)                              AS template_rate,
    AVG(reached_contacts::INT)                              AS contacts_rate,
    AVG(activated_7d::INT)                                  AS activated_7d_rate,
    AVG(retained_d30::INT) FILTER (WHERE mature_d30)        AS retention_d30,
    AVG(upgraded_60d::INT) FILTER (WHERE mature_60d)        AS upgrade_rate_60d,
    AVG((platform = 'Web - mobile')::INT)                   AS mobile_share
FROM ab_users
GROUP BY variant
ORDER BY variant;
