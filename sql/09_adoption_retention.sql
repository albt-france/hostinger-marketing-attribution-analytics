-- =====================================================================
-- 09 · Defining adoption: the "aha" moment and retention
-- Candidate definition of a successful Reach adoption: the first campaign is
-- sent within 7 days of the onboarding start. This file measures how much
-- longer those users stay, with censoring-safe retention:
-- a user only counts at day d once d days have fully passed before the end
-- of the data (31 Oct 2026). Without that rule, recent users would look
-- like churners.
-- Retention = at least one core Reach action (campaign sent, AI copy used,
-- template chosen, contacts imported) in the window:
--   day-7 retention  = days 7-13 after the start
--   day-30 retention = days 28-34 after the start
-- Also prepares the Mail panel for the AI-reply rollout analysis.
-- SIMULATED data. Correlation, not causation: see the notebook.
-- =====================================================================

-- reach_activity: one row per user and active day (days since the onboarding start)
CREATE OR REPLACE TABLE reach_activity AS
SELECT DISTINCT
    e.user_id,
    date_diff('day', u.started_ts, e.event_time) AS day_index
FROM reach_events AS e
JOIN reach_funnel_users AS u USING (user_id)
WHERE e.event_name IN ('reach_campaign_sent', 'reach_ai_copy_used', 'reach_template_chosen', 'reach_contacts_imported')
  AND e.event_time >= u.started_ts;


-- reach_users: funnel + retention + upgrade, one row per user (fact table for Power BI)
CREATE OR REPLACE TABLE reach_users AS
WITH params AS (
    SELECT TIMESTAMP '2026-10-31 23:59:59' AS observation_end
),
retention AS (
    SELECT
        user_id,
        BOOL_OR(day_index BETWEEN 7 AND 13)  AS active_d7,
        BOOL_OR(day_index BETWEEN 28 AND 34) AS active_d30,
        COUNT(DISTINCT day_index // 7) FILTER (WHERE day_index < 91) AS active_weeks_first_13
    FROM reach_activity
    GROUP BY user_id
),
upgrades AS (
    SELECT user_id, MIN(event_time) AS upgrade_ts
    FROM reach_events
    WHERE event_name = 'reach_upgrade'
    GROUP BY user_id
)
SELECT
    u.* EXCLUDE (template_ts, contacts_ts),
    CASE
        WHEN u.days_to_first_campaign IS NULL THEN 'No campaign in 30 days'
        WHEN u.days_to_first_campaign <= 7    THEN 'First campaign within 7 days'
        ELSE 'First campaign on days 8-30'
    END                                                                AS adoption_group,
    u.started_ts + INTERVAL 14 DAY <= p.observation_end                AS mature_d7,
    u.started_ts + INTERVAL 35 DAY <= p.observation_end                AS mature_d30,
    u.started_ts + INTERVAL 60 DAY <= p.observation_end                AS mature_60d,
    COALESCE(r.active_d7, FALSE)                                       AS retained_d7,
    COALESCE(r.active_d30, FALSE)                                      AS retained_d30,
    COALESCE(r.active_weeks_first_13, 0)                               AS active_weeks_first_13,
    COALESCE(g.upgrade_ts <= u.started_ts + INTERVAL 60 DAY, FALSE)    AS upgraded_60d
FROM reach_funnel_users AS u
CROSS JOIN params AS p
LEFT JOIN retention AS r USING (user_id)
LEFT JOIN upgrades  AS g USING (user_id);


-- output: reach_users
SELECT * FROM reach_users ORDER BY started_ts, user_id;


-- output: aha_retention
-- Day-30 retention and upgrades by how fast the first campaign was sent.
-- Only users with a full 35 days of history.
WITH bucketed AS (
    SELECT
        *,
        CASE
            WHEN days_to_first_campaign IS NULL THEN 6
            WHEN days_to_first_campaign <= 1    THEN 1
            WHEN days_to_first_campaign <= 3    THEN 2
            WHEN days_to_first_campaign <= 7    THEN 3
            WHEN days_to_first_campaign <= 14   THEN 4
            ELSE 5
        END AS bucket_order
    FROM reach_users
    WHERE mature_d30
)
SELECT
    bucket_order,
    CASE bucket_order
        WHEN 1 THEN 'Day 0-1' WHEN 2 THEN 'Day 2-3' WHEN 3 THEN 'Day 4-7'
        WHEN 4 THEN 'Day 8-14' WHEN 5 THEN 'Day 15-30' ELSE 'No campaign'
    END                                           AS first_campaign,
    COUNT(*)                                      AS users,
    COUNT(*) * 1.0 / SUM(COUNT(*)) OVER ()        AS share_of_users,
    AVG(retained_d30::INT)                        AS retention_d30,
    AVG(upgraded_60d::INT) FILTER (WHERE mature_60d) AS upgrade_rate_60d
FROM bucketed
GROUP BY bucket_order
ORDER BY bucket_order;


-- output: adoption_curve
-- Weekly retention curve (share of users active in week w) by adoption group,
-- censoring-safe: a user counts in week w only if that week has fully passed.
WITH params AS (
    SELECT TIMESTAMP '2026-10-31 23:59:59' AS observation_end
),
weeks AS (
    SELECT range AS week FROM range(0, 13)
),
observable AS (
    SELECT u.user_id, u.adoption_group, w.week
    FROM reach_users AS u
    CROSS JOIN weeks AS w
    CROSS JOIN params AS p
    WHERE u.mature_d30                                         -- group is known (30-day window over)
      AND u.started_ts + to_days(CAST(7 * (w.week + 1) AS INTEGER)) <= p.observation_end
),
active_weeks AS (
    SELECT DISTINCT user_id, day_index // 7 AS week FROM reach_activity
)
SELECT
    o.adoption_group,
    o.week,
    COUNT(*)                                       AS users_observed,
    AVG(CASE WHEN a.user_id IS NOT NULL THEN 1.0 ELSE 0.0 END) AS retention
FROM observable AS o
LEFT JOIN active_weeks AS a USING (user_id, week)
GROUP BY ALL
ORDER BY o.adoption_group, o.week;


-- output: adoption_cohorts
-- By onboarding month: how many users reach the aha moment, and do they stay?
SELECT
    onboarding_month,
    COUNT(*)                                                   AS starters,
    AVG(activated_7d::INT) FILTER (WHERE funnel_complete)      AS activated_7d_rate,
    AVG(retained_d30::INT) FILTER (WHERE mature_d30)           AS retention_d30,
    AVG(retained_d30::INT) FILTER (WHERE mature_d30 AND activated_7d)     AS retention_d30_activated,
    AVG(retained_d30::INT) FILTER (WHERE mature_d30 AND NOT activated_7d) AS retention_d30_not_activated
FROM reach_users
GROUP BY onboarding_month
ORDER BY onboarding_month;


-- output: mail_weekly
-- Hostinger Mail panel: every mail user x every week (weeks without activity
-- kept as zeros, via a CROSS JOIN with a week spine). AI replies were rolled
-- out in two waves: US, FR, ES on 1 Jun 2026; BR, IN, ID on 3 Aug 2026.
WITH mail_events AS (
    SELECT
        user_id,
        CAST(date_trunc('week', event_time) AS DATE)                          AS week,
        event_name,
        CAST(event_time AS DATE)                                              AS day,
        COALESCE(CAST(json_extract_string(event_properties, '$.count') AS INTEGER), 1) AS n
    FROM product_events
    WHERE product = 'Mail'
),
mail_users AS (
    SELECT DISTINCT m.user_id, o.country, o.device, o.product AS hosting_product
    FROM mail_events AS m
    JOIN orders AS o USING (user_id)
),
week_spine AS (
    SELECT CAST(range AS DATE) AS week
    FROM range(DATE '2026-03-02', DATE '2026-10-26', INTERVAL 7 DAY)
),
user_week AS (
    SELECT
        user_id,
        week,
        COUNT(DISTINCT day) FILTER (WHERE event_name = 'mail_inbox_opened') AS active_days,
        SUM(n)              FILTER (WHERE event_name = 'mail_message_sent') AS messages_sent,
        COUNT(*)            FILTER (WHERE event_name = 'mail_ai_reply_used') AS ai_days
    FROM mail_events
    GROUP BY ALL
),
panel AS (
    SELECT
        u.user_id,
        CASE WHEN u.country IN ('US', 'FR', 'ES') THEN 'Wave 1 (1 Jun)' ELSE 'Wave 2 (3 Aug)' END AS rollout_wave,
        CASE
            WHEN u.device = 'mobile'                         THEN 'Mobile'
            WHEN u.hosting_product IN ('builder', 'shared')  THEN 'Desktop · website & hosting'
            ELSE 'Desktop · cloud & VPS'
        END                                                  AS segment,
        s.week,
        COALESCE(w.active_days, 0)                           AS active_days,
        COALESCE(w.messages_sent, 0)                         AS messages_sent,
        COALESCE(w.ai_days, 0) > 0                           AS used_ai
    FROM mail_users AS u
    CROSS JOIN week_spine AS s
    LEFT JOIN user_week AS w ON w.user_id = u.user_id AND w.week = s.week
)
SELECT
    rollout_wave,
    segment,
    week,
    COUNT(*)                  AS users,
    AVG(active_days)          AS active_days_per_user,
    AVG(messages_sent)        AS messages_per_user,
    AVG(used_ai::INT)         AS ai_user_share
FROM panel
GROUP BY ALL
ORDER BY rollout_wave, segment, week;
