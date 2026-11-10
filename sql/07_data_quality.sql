-- =====================================================================
-- 07 · Data quality checks
-- Run before trusting any number above: duplicates, orders without
-- touchpoints, missing cost days, spend rows without campaign, spend vs invoices.
-- SIMULATED data.
-- =====================================================================

-- output: dq_daily_events
-- Raw vs de-duplicated tracking events per day; a spike in duplicates = tag fired twice.
WITH raw_events AS (
    SELECT CAST(ts AS DATE) AS date, COUNT(*) AS raw_events FROM touchpoints GROUP BY 1
),
clean_events AS (
    SELECT CAST(ts AS DATE) AS date, COUNT(*) AS clean_events FROM touchpoints_clean GROUP BY 1
)
SELECT
    r.date,
    r.raw_events,
    c.clean_events,
    r.raw_events - c.clean_events                           AS duplicate_events,
    (r.raw_events - c.clean_events) / r.raw_events          AS duplicate_rate
FROM raw_events AS r
JOIN clean_events AS c USING (date)
ORDER BY r.date;


-- output: dq_spend_vs_invoice
-- Tracked spend vs what finance was invoiced, per month and channel.
WITH tracked AS (
    SELECT CAST(date_trunc('month', date) AS DATE) AS month, channel, SUM(spend_eur) AS tracked_spend_eur
    FROM spend
    GROUP BY ALL
)
SELECT
    CAST(i.month AS DATE)                                              AS month,
    i.channel,
    COALESCE(t.tracked_spend_eur, 0)                                   AS tracked_spend_eur,
    i.invoiced_eur,
    i.invoiced_eur - COALESCE(t.tracked_spend_eur, 0)                  AS gap_eur,
    (i.invoiced_eur - COALESCE(t.tracked_spend_eur, 0)) / NULLIF(i.invoiced_eur, 0) AS gap_pct
FROM invoices AS i
LEFT JOIN tracked AS t ON t.month = CAST(i.month AS DATE) AND t.channel = i.channel
ORDER BY ABS(gap_pct) DESC;


-- output: dq_checks
-- One line per check: how many rows fail, and what to do about it.
WITH calendar AS (
    SELECT CAST(range AS DATE) AS date
    FROM range(DATE '2024-05-01', DATE '2026-11-01', INTERVAL 1 DAY)
),
nb_days AS (
    SELECT DISTINCT CAST(date AS DATE) AS date FROM spend WHERE channel = 'PPC Non-brand'
),
checks AS (
    SELECT 1 AS check_id,
           'Duplicated tracking events' AS check_name,
           (SELECT COUNT(*) FROM touchpoints) - (SELECT COUNT(*) FROM touchpoints_clean) AS failing_rows,
           (SELECT MAX(date) FROM (SELECT CAST(ts AS DATE) AS date, COUNT(*) - COUNT(DISTINCT (user_id, channel, sub_channel, date_trunc('second', ts))) AS d
                                  FROM touchpoints GROUP BY 1 ORDER BY d DESC LIMIT 1))::VARCHAR AS detail,
           'Removed in touchpoints_clean (same user + channel within 2 s)' AS action
    UNION ALL
    SELECT 2, 'Orders with no touchpoint in the 30-day window',
           (SELECT COUNT(*) FROM order_first_last WHERE last_click_channel = 'Unattributed'),
           ROUND(100.0 * (SELECT COUNT(*) FROM order_first_last WHERE last_click_channel = 'Unattributed')
                 / (SELECT COUNT(*) FROM orders), 1)::VARCHAR || '% of orders',
           'Kept as "Unattributed" so totals still match finance'
    UNION ALL
    SELECT 3, 'Days without PPC Non-brand cost (always-on channel)',
           (SELECT COUNT(*) FROM calendar c WHERE NOT EXISTS (SELECT 1 FROM nb_days n WHERE n.date = c.date)),
           (SELECT STRING_AGG(CAST(date AS VARCHAR), ', ') FROM calendar c
             WHERE NOT EXISTS (SELECT 1 FROM nb_days n WHERE n.date = c.date)),
           'Cost import failed: re-import, or use the invoice for that month'
    UNION ALL
    SELECT 4, 'Spend rows without campaign id',
           (SELECT COUNT(*) FROM spend WHERE campaign_id IS NULL),
           (SELECT STRING_AGG(DISTINCT channel, ', ') FROM spend WHERE campaign_id IS NULL),
           'Reported under the channel, excluded from campaign-level views'
    UNION ALL
    SELECT 5, 'Months where tracked spend and invoice differ by more than 1%',
           (SELECT COUNT(*) FROM invoices i
              LEFT JOIN (SELECT CAST(date_trunc('month', date) AS DATE) m, channel, SUM(spend_eur) s FROM spend GROUP BY ALL) t
                ON t.m = CAST(i.month AS DATE) AND t.channel = i.channel
             WHERE ABS(i.invoiced_eur - COALESCE(t.s, 0)) / i.invoiced_eur > 0.01),
           'see dq_spend_vs_invoice',
           'Finance invoice is the source of truth for cost'
    UNION ALL
    SELECT 6, 'Duplicate order ids',
           (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM orders), '', 'Must be 0'
    UNION ALL
    SELECT 7, 'Refunds after the 30-day guarantee or above the amount paid',
           (SELECT COUNT(*) FROM refunds r JOIN orders o USING (order_id)
             WHERE r.refund_ts > o.ts + INTERVAL 30 DAY OR r.amount > o.paid_amount_eur), '', 'Must be 0'
    UNION ALL
    SELECT 8, 'Renewals or refunds without a matching order',
           (SELECT COUNT(*) FROM renewals r WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.order_id = r.order_id))
         + (SELECT COUNT(*) FROM refunds  r WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.order_id = r.order_id)),
           '', 'Must be 0'
)
SELECT * FROM checks ORDER BY check_id;
