-- 05_reporting_views.sql
-- Views used by the investigation dashboard.

DROP VIEW IF EXISTS v_daily_volume;
CREATE VIEW v_daily_volume AS
SELECT date(ts) AS day, COUNT(*) AS txn_count, ROUND(SUM(amount_usd), 2) AS value_usd
FROM transactions GROUP BY date(ts);

DROP VIEW IF EXISTS v_alert_queue;
CREATE VIEW v_alert_queue AS
SELECT a.alert_id, a.rule_id, a.priority, a.priority_score, a.subject_id, a.customer_id,
       c.occupation, a.alert_date, a.value_usd, a.reason,
       COALESCE(r.status, 'New') AS status, r.disposition, r.analyst, r.note, r.updated_at
FROM alerts a
LEFT JOIN customers c     ON c.customer_id = a.customer_id
LEFT JOIN alert_reviews r ON r.alert_id = a.alert_id;

DROP VIEW IF EXISTS v_customer_monthly;
CREATE VIEW v_customer_monthly AS
SELECT a.customer_id, substr(t.ts, 1, 7) AS month,
       ROUND(SUM(CASE WHEN t.receiver_account = a.account_id THEN t.amount_usd ELSE 0 END), 2) AS money_in_usd,
       ROUND(SUM(CASE WHEN t.sender_account   = a.account_id THEN t.amount_usd ELSE 0 END), 2) AS money_out_usd,
       COUNT(*) AS txn_count
FROM accounts a
JOIN transactions t ON t.sender_account = a.account_id OR t.receiver_account = a.account_id
GROUP BY a.customer_id, substr(t.ts, 1, 7);
