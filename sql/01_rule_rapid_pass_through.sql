-- 01_rule_rapid_pass_through.sql
-- R1: several incoming transfers from different senders, followed shortly by
--     one large outgoing transfer of a similar amount ("money in, money out").
-- Parameters (config/rules_config.json): :lookback_hours, :min_in_count,
--     :min_distinct_senders, :min_out_usd, :min_out_ratio, :max_out_ratio

-- name: triggers
WITH large_out AS (
    SELECT transaction_id, sender_account AS account_id, ts, amount_usd, receiver_account
    FROM transactions
    WHERE transaction_type IN ('WIRE_OUT', 'P2P_TRANSFER', 'CASH_WITHDRAWAL')
      AND sender_account LIKE 'A%'
      AND amount_usd >= :min_out_usd
),
inflow AS (
    SELECT o.transaction_id                   AS anchor_txn,
           o.account_id                       AS subject_id,
           o.ts                               AS anchor_ts,
           o.amount_usd                       AS out_usd,
           o.receiver_account                 AS out_receiver,
           COUNT(i.transaction_id)            AS in_count,
           COUNT(DISTINCT i.sender_account)   AS in_senders,
           ROUND(SUM(i.amount_usd), 2)        AS in_usd,
           MIN(i.ts)                          AS window_start
    FROM large_out o
    JOIN transactions i
      ON i.receiver_account = o.account_id
     AND i.transaction_type IN ('P2P_TRANSFER', 'WIRE_IN', 'CASH_DEPOSIT')
     AND i.ts <  o.ts
     AND julianday(i.ts) >= julianday(o.ts) - :lookback_hours / 24.0
    GROUP BY o.transaction_id
)
SELECT subject_id, anchor_txn, anchor_ts, window_start, anchor_ts AS window_end,
       in_count, in_senders, in_usd, out_usd, out_receiver,
       ROUND(out_usd / in_usd, 3)                                        AS out_ratio,
       ROUND((julianday(anchor_ts) - julianday(window_start)) * 24, 1)   AS hours_in_to_out
FROM inflow
WHERE in_count   >= :min_in_count
  AND in_senders >= :min_distinct_senders
  AND out_usd    >= :min_out_ratio * in_usd
  AND out_usd    <= :max_out_ratio * in_usd;

-- name: evidence
SELECT transaction_id,
       CASE WHEN receiver_account = :subject_id THEN 'Incoming transfer'
            ELSE 'Large outgoing transfer' END AS evidence_role
FROM transactions
WHERE ts BETWEEN :window_start AND :window_end
  AND (
        (receiver_account = :subject_id AND transaction_type IN ('P2P_TRANSFER', 'WIRE_IN', 'CASH_DEPOSIT'))
     OR (sender_account = :subject_id AND transaction_type IN ('WIRE_OUT', 'P2P_TRANSFER', 'CASH_WITHDRAWAL')
         AND amount_usd >= :min_out_usd)
      );
