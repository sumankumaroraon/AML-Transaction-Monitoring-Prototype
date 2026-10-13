-- 03_rule_many_to_one.sql
-- R3: many different accounts send funds to the same beneficiary within a short
--     window. Only "new" senders count: a sender who already paid this beneficiary
--     in the previous :relationship_days is treated as an established relationship
--     (e.g. tenants paying rent), which suppresses routine fan-in.
-- Warm-up: "new sender" can only be judged once :relationship_days of history
--     exist, so when :apply_warmup = 1 windows starting before
--     (first transaction date + :relationship_days) are not scored.
-- Parameters: :window_days, :min_new_senders, :min_total_usd, :relationship_days, :apply_warmup

-- name: triggers
WITH pay AS (
    SELECT transaction_id, sender_account, receiver_account AS beneficiary, ts, amount_usd
    FROM transactions
    WHERE transaction_type IN ('WIRE_OUT', 'P2P_TRANSFER')
      AND sender_account LIKE 'A%'
),
flagged AS (
    SELECT p.*,
           NOT EXISTS (
               SELECT 1 FROM pay q
               WHERE q.sender_account = p.sender_account
                 AND q.beneficiary    = p.beneficiary
                 AND q.ts < p.ts
                 AND julianday(q.ts) >= julianday(p.ts) - :relationship_days
           ) AS is_new_sender
    FROM pay p
),
windowed AS (
    SELECT a.beneficiary                                                  AS subject_id,
           a.transaction_id                                               AS anchor_txn,
           a.ts                                                           AS anchor_ts,
           MIN(b.ts)                                                      AS window_start,
           COUNT(DISTINCT b.sender_account)                               AS senders,
           COUNT(DISTINCT CASE WHEN b.is_new_sender THEN b.sender_account END) AS new_senders,
           COUNT(b.transaction_id)                                        AS payments,
           ROUND(SUM(b.amount_usd), 2)                                    AS total_usd
    FROM flagged a
    JOIN flagged b
      ON b.beneficiary = a.beneficiary
     AND b.ts <= a.ts
     AND julianday(b.ts) > julianday(a.ts) - :window_days
    GROUP BY a.transaction_id
)
SELECT subject_id, anchor_txn, anchor_ts, window_start, anchor_ts AS window_end,
       senders, new_senders, payments, total_usd
FROM windowed
WHERE new_senders >= :min_new_senders
  AND total_usd   >= :min_total_usd
  AND (:apply_warmup = 0
       OR window_start >= (SELECT datetime(MIN(ts), '+' || :relationship_days || ' days') FROM transactions));

-- name: evidence
SELECT transaction_id, 'Payment to beneficiary' AS evidence_role
FROM transactions
WHERE receiver_account = :subject_id
  AND transaction_type IN ('WIRE_OUT', 'P2P_TRANSFER')
  AND ts BETWEEN :window_start AND :window_end;
