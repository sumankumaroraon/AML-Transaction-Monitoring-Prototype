-- 02_rule_activity_spike.sql
-- R2: an account's monthly activity (money in + money out) is far above both
--     its own trailing history and the customer's declared expected activity.
-- Baseline = average of the previous :history_months calendar months (zero-filled)
--            once the account has that much history; otherwise the declared
--            expected monthly activity from the customer profile.
-- Parameters: :min_month_usd, :spike_multiplier, :profile_multiplier, :history_months

-- name: triggers
WITH RECURSIVE months(m) AS (
    SELECT '2025-01' UNION ALL
    SELECT strftime('%Y-%m', date(m || '-01', '+1 month')) FROM months WHERE m < '2025-12'
),
acct_months AS (               -- one row per account per month since opening
    SELECT a.account_id, a.customer_id, mo.m AS month
    FROM accounts a
    JOIN months mo ON mo.m >= substr(a.open_date, 1, 7)
),
flows AS (
    SELECT sender_account AS account_id, substr(ts, 1, 7) AS month, amount_usd FROM transactions
    UNION ALL
    SELECT receiver_account, substr(ts, 1, 7), amount_usd FROM transactions
),
monthly AS (
    SELECT am.account_id, am.customer_id, am.month,
           COALESCE(SUM(f.amount_usd), 0) AS month_usd,
           COUNT(f.amount_usd)            AS month_txns
    FROM acct_months am
    LEFT JOIN flows f ON f.account_id = am.account_id AND f.month = am.month
    GROUP BY am.account_id, am.customer_id, am.month
),
hist AS (
    SELECT m.*,
           AVG(month_usd) OVER w   AS trailing_avg_usd,
           COUNT(*)       OVER w   AS history_months
    FROM monthly m
    WINDOW w AS (PARTITION BY account_id ORDER BY month ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING)
),
scored AS (
    SELECT h.*, c.expected_monthly_activity_usd AS expected_usd,
           CASE WHEN h.history_months >= :history_months THEN h.trailing_avg_usd
                ELSE c.expected_monthly_activity_usd END AS baseline_usd,
           CASE WHEN h.history_months >= :history_months THEN 'trailing 3-month average'
                ELSE 'declared expected activity (insufficient history)' END AS baseline_source
    FROM hist h JOIN customers c ON c.customer_id = h.customer_id
)
SELECT account_id AS subject_id, month,
       month || '-01 00:00:00'                                   AS window_start,
       strftime('%Y-%m-%d 23:59:59', month || '-01', '+1 month', '-1 day') AS window_end,
       ROUND(month_usd, 2) AS month_usd, month_txns,
       ROUND(baseline_usd, 2) AS baseline_usd, baseline_source,
       ROUND(month_usd / NULLIF(baseline_usd, 0), 2) AS x_baseline,
       expected_usd,
       ROUND(month_usd / expected_usd, 2)            AS x_expected
FROM scored
WHERE month_usd >= :min_month_usd
  AND month_usd >= :spike_multiplier   * baseline_usd
  AND month_usd >= :profile_multiplier * expected_usd;

-- name: evidence
SELECT transaction_id,
       CASE WHEN receiver_account = :subject_id THEN 'Money in (alert month)'
            ELSE 'Money out (alert month)' END AS evidence_role
FROM transactions
WHERE ts BETWEEN :window_start AND :window_end
  AND (sender_account = :subject_id OR receiver_account = :subject_id);
