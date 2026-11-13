-- =====================================================================
-- 08 · Reach onboarding funnel
-- Hostinger Reach (AI e-mail marketing): onboarding started -> template
-- chosen -> contacts imported -> first campaign sent.
-- An ordered funnel with a 30-day conversion window, like an Amplitude
-- funnel: each step only counts if it happens after the previous one and
-- within 30 days of the start. Linked to the marketing side through the
-- customer's acquisition (first-click) channel from 00_staging.sql.
-- SIMULATED data (src/generate_product_sim.py).
-- =====================================================================

-- reach_events: Reach events only (the event table also holds Mail and referral events)
CREATE OR REPLACE TABLE reach_events AS
SELECT user_id, event_name, event_time, platform, event_properties
FROM product_events
WHERE product = 'Reach';


-- reach_funnel_users: one row per Reach user, with the time each step was reached
CREATE OR REPLACE TABLE reach_funnel_users AS
WITH params AS (
    SELECT TIMESTAMP '2026-10-31 23:59:59' AS observation_end
),
starts AS (
    -- first onboarding start per user, and where it came from (post-purchase, hPanel, newsletter)
    SELECT
        user_id,
        MIN(event_time)                                                   AS started_ts,
        ARG_MIN(json_extract_string(event_properties, '$.source'), event_time) AS source,
        ARG_MIN(platform, event_time)                                     AS platform
    FROM reach_events
    WHERE event_name = 'reach_onboarding_started'
    GROUP BY user_id
),
step_template AS (
    SELECT s.user_id, MIN(e.event_time) AS template_ts
    FROM starts AS s
    JOIN reach_events AS e
      ON  e.user_id = s.user_id
      AND e.event_name = 'reach_template_chosen'
      AND e.event_time BETWEEN s.started_ts AND s.started_ts + INTERVAL 30 DAY
    GROUP BY s.user_id
),
step_contacts AS (
    SELECT t.user_id, MIN(e.event_time) AS contacts_ts,
           ARG_MIN(CAST(json_extract_string(e.event_properties, '$.contacts') AS INTEGER), e.event_time) AS contacts
    FROM step_template AS t
    JOIN starts AS s USING (user_id)
    JOIN reach_events AS e
      ON  e.user_id = t.user_id
      AND e.event_name = 'reach_contacts_imported'
      AND e.event_time BETWEEN t.template_ts AND s.started_ts + INTERVAL 30 DAY
    GROUP BY t.user_id
),
step_campaign AS (
    SELECT c.user_id, MIN(e.event_time) AS first_campaign_ts
    FROM step_contacts AS c
    JOIN starts AS s USING (user_id)
    JOIN reach_events AS e
      ON  e.user_id = c.user_id
      AND e.event_name = 'reach_campaign_sent'
      AND e.event_time BETWEEN c.contacts_ts AND s.started_ts + INTERVAL 30 DAY
    GROUP BY c.user_id
)
SELECT
    s.user_id,
    s.started_ts,
    CAST(s.started_ts AS DATE)                                          AS onboarding_date,
    CAST(date_trunc('month', s.started_ts) AS DATE)                     AS onboarding_month,
    s.source,
    s.platform,
    o.country,
    o.product                                                           AS hosting_product,
    f.first_click_channel                                               AS channel,
    t.template_ts,
    c.contacts_ts,
    c.contacts,
    k.first_campaign_ts,
    t.template_ts IS NOT NULL                                           AS reached_template,
    c.contacts_ts IS NOT NULL                                           AS reached_contacts,
    k.first_campaign_ts IS NOT NULL                                     AS reached_campaign,
    date_diff('minute', s.started_ts, t.template_ts) / 60.0             AS hours_to_template,
    date_diff('minute', t.template_ts, c.contacts_ts) / 60.0            AS hours_template_to_contacts,
    date_diff('minute', c.contacts_ts, k.first_campaign_ts) / 60.0      AS hours_contacts_to_campaign,
    date_diff('minute', s.started_ts, k.first_campaign_ts) / 1440.0     AS days_to_first_campaign,
    -- the "aha" moment tested in 09: first campaign sent within 7 days of the start
    COALESCE(k.first_campaign_ts <= s.started_ts + INTERVAL 7 DAY, FALSE) AS activated_7d,
    -- censoring: the 30-day funnel window must be over before the end of the data
    s.started_ts + INTERVAL 30 DAY <= p.observation_end                 AS funnel_complete
FROM starts AS s
CROSS JOIN params AS p
JOIN orders AS o USING (user_id)
JOIN order_first_last AS f USING (order_id)
LEFT JOIN step_template AS t USING (user_id)
LEFT JOIN step_contacts AS c USING (user_id)
LEFT JOIN step_campaign AS k USING (user_id);


-- output: reach_funnel
-- Users at each step (completed 30-day windows only), conversion from the start and
-- from the previous step (LAG), and the median time from the previous step.
WITH steps AS (
    SELECT 1 AS step_order, 'Onboarding started' AS step, COUNT(*) AS users, NULL::DOUBLE AS median_hours_from_previous
    FROM reach_funnel_users WHERE funnel_complete
    UNION ALL
    SELECT 2, 'Template chosen', COUNT(*) FILTER (WHERE reached_template),
           MEDIAN(hours_to_template)
    FROM reach_funnel_users WHERE funnel_complete
    UNION ALL
    SELECT 3, 'Contacts imported', COUNT(*) FILTER (WHERE reached_contacts),
           MEDIAN(hours_template_to_contacts)
    FROM reach_funnel_users WHERE funnel_complete
    UNION ALL
    SELECT 4, 'First campaign sent', COUNT(*) FILTER (WHERE reached_campaign),
           MEDIAN(hours_contacts_to_campaign)
    FROM reach_funnel_users WHERE funnel_complete
)
SELECT
    step_order,
    step,
    users,
    users * 1.0 / FIRST_VALUE(users) OVER (ORDER BY step_order)        AS conversion_from_start,
    COALESCE(users * 1.0 / LAG(users) OVER (ORDER BY step_order), 1.0) AS conversion_from_previous,   -- first step: 100%
    LAG(users) OVER (ORDER BY step_order) - users                      AS users_lost,
    median_hours_from_previous
FROM steps
ORDER BY step_order;


-- output: reach_funnel_segments
-- Same funnel by segment: acquisition channel (the link with the marketing part),
-- country, platform, hosting product and onboarding source.
WITH segmented AS (
    SELECT 'Acquisition channel' AS segment_type, channel         AS segment, * FROM reach_funnel_users WHERE funnel_complete
    UNION ALL
    SELECT 'Country',                             country,                    * FROM reach_funnel_users WHERE funnel_complete
    UNION ALL
    SELECT 'Platform',                            platform,                   * FROM reach_funnel_users WHERE funnel_complete
    UNION ALL
    SELECT 'Hosting product',                     hosting_product,            * FROM reach_funnel_users WHERE funnel_complete
    UNION ALL
    SELECT 'Onboarding source',                   source,                     * FROM reach_funnel_users WHERE funnel_complete
),
rates AS (
    SELECT
        segment_type,
        segment,
        COUNT(*)                                                     AS starters,
        AVG(reached_template::INT)                                   AS template_rate,
        AVG(reached_contacts::INT)                                   AS contacts_rate,
        AVG(reached_campaign::INT)                                   AS campaign_rate,
        AVG(activated_7d::INT)                                       AS activated_7d_rate,
        MEDIAN(days_to_first_campaign)                               AS median_days_to_first_campaign
    FROM segmented
    GROUP BY ALL
)
SELECT
    *,
    -- gap to the overall rate, in points: where is the funnel weakest?
    campaign_rate - (SELECT AVG(reached_campaign::INT) FROM reach_funnel_users WHERE funnel_complete) AS campaign_rate_vs_all,
    RANK() OVER (PARTITION BY segment_type ORDER BY campaign_rate DESC) AS rank_in_type
FROM rates
WHERE starters >= 100
ORDER BY segment_type, rank_in_type;


-- output: reach_adoption_by_channel
-- The link with the marketing part: out of 100 new customers acquired by each
-- channel (orders since 1 May 2025, 30-day window over), how many start Reach
-- and how many reach the aha moment? Channels bring customers who differ in
-- product use, not only in refunds and renewals (page 4).
WITH params AS (
    SELECT TIMESTAMP '2026-10-31 23:59:59' AS observation_end
),
new_customers AS (
    SELECT o.user_id, f.first_click_channel AS channel
    FROM orders AS o
    JOIN order_first_last AS f USING (order_id)
    CROSS JOIN params AS p
    WHERE o.ts >= TIMESTAMP '2025-05-01'
      AND o.ts + INTERVAL 60 DAY <= p.observation_end
)
SELECT
    n.channel,
    COUNT(*)                                                         AS new_customers,
    COUNT(u.user_id) * 1.0 / COUNT(*)                                AS started_reach_rate,
    COUNT(*) FILTER (WHERE u.activated_7d) * 1.0 / COUNT(*)          AS activated_per_customer,
    AVG(u.activated_7d::INT)                                         AS activated_7d_rate_of_starters
FROM new_customers AS n
LEFT JOIN reach_funnel_users AS u
  ON  u.user_id = n.user_id
  AND u.source = 'post_purchase'
  AND u.funnel_complete
GROUP BY n.channel
ORDER BY activated_per_customer DESC;


-- output: product_daily
-- Daily roll-up of every product event (Reach, Mail, referral), the grain used
-- by Power BI: users and events per day, event, platform and country.
SELECT
    CAST(event_time AS DATE)        AS date,
    product,
    event_name,
    platform,
    country,
    COUNT(DISTINCT user_id)         AS users,
    COUNT(*)                        AS events
FROM product_events
GROUP BY ALL
ORDER BY ALL;
