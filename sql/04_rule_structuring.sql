-- 04_rule_structuring.sql
-- R4: repeated cash deposits just below the configurable monitoring threshold.
-- "Just below" = between :band_pct x threshold and the threshold itself.
-- Parameters: :threshold, :band_pct, :window_days, :min_count

-- name: triggers
WITH near AS (
    SELECT transaction_id, receiver_account AS account_id, ts, amount_usd
    FROM transactions
    WHERE transaction_type = 'CASH_DEPOSIT'
      AND receiver_account LIKE 'A%'
      AND amount_usd >= :band_pct * :threshold
      AND amount_usd <  :threshold
)
SELECT n.account_id                     AS subject_id,
       n.transaction_id                 AS anchor_txn,
       n.ts                             AS anchor_ts,
       MIN(m.ts)                        AS window_start,
       n.ts                             AS window_end,
       COUNT(m.transaction_id)          AS near_threshold_count,
       ROUND(SUM(m.amount_usd), 2)      AS total_usd,
       ROUND(MIN(m.amount_usd), 2)      AS min_deposit_usd,
       ROUND(MAX(m.amount_usd), 2)      AS max_deposit_usd
FROM near n
JOIN near m
  ON m.account_id = n.account_id
 AND m.ts <= n.ts
 AND julianday(m.ts) > julianday(n.ts) - :window_days
GROUP BY n.transaction_id
HAVING COUNT(m.transaction_id) >= :min_count;

-- name: evidence
SELECT transaction_id, 'Cash deposit just below threshold' AS evidence_role
FROM transactions
WHERE receiver_account = :subject_id
  AND transaction_type = 'CASH_DEPOSIT'
  AND amount_usd >= :band_pct * :threshold AND amount_usd < :threshold
  AND ts BETWEEN :window_start AND :window_end;
