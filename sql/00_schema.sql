-- 00_schema.sql
-- SQLite schema for the AML transaction-monitoring prototype (synthetic data only).

DROP TABLE IF EXISTS customers;
CREATE TABLE customers (
    customer_id                    TEXT PRIMARY KEY,
    occupation                     TEXT NOT NULL,
    customer_segment               TEXT NOT NULL,          -- retail | business
    expected_monthly_activity_usd  REAL NOT NULL,          -- declared at onboarding (KYC profile)
    account_opening_date           TEXT NOT NULL           -- YYYY-MM-DD, start of relationship
);

DROP TABLE IF EXISTS accounts;
CREATE TABLE accounts (
    account_id    TEXT PRIMARY KEY,
    customer_id   TEXT NOT NULL REFERENCES customers(customer_id),
    account_type  TEXT NOT NULL,                           -- checking | business_checking | savings
    open_date     TEXT NOT NULL
);

DROP TABLE IF EXISTS transactions;
CREATE TABLE transactions (
    transaction_id    TEXT PRIMARY KEY,
    ts                TEXT NOT NULL,                       -- YYYY-MM-DD HH:MM:SS
    sender_account    TEXT NOT NULL,                       -- internal A###### or external party
    receiver_account  TEXT NOT NULL,
    amount            REAL NOT NULL,                       -- original currency
    currency          TEXT NOT NULL,
    amount_usd        REAL NOT NULL,                       -- converted with fixed project FX rates
    transaction_type  TEXT NOT NULL
);
CREATE INDEX ix_tx_sender   ON transactions(sender_account, ts);
CREATE INDEX ix_tx_receiver ON transactions(receiver_account, ts);
CREATE INDEX ix_tx_type     ON transactions(transaction_type, ts);

-- ground truth for evaluation (never read by the rules)
DROP TABLE IF EXISTS planted_scenarios;
CREATE TABLE planted_scenarios (
    scenario_id TEXT PRIMARY KEY, scenario_type TEXT, variant TEXT, subject_id TEXT, customer_id TEXT,
    window_start TEXT, window_end TEXT, n_transactions INTEGER, total_usd REAL, description TEXT
);
DROP TABLE IF EXISTS planted_transactions;
CREATE TABLE planted_transactions (scenario_id TEXT, transaction_id TEXT);

DROP TABLE IF EXISTS benign_lookalikes;
CREATE TABLE benign_lookalikes (
    lookalike_id TEXT PRIMARY KEY, resembles TEXT, subject_id TEXT, description TEXT,
    window_start TEXT, window_end TEXT, n_txns REAL
);

-- alert outputs (written by src/03_run_rules.py)
DROP TABLE IF EXISTS alerts;
CREATE TABLE alerts (
    alert_id        TEXT PRIMARY KEY,
    rule_id         TEXT NOT NULL,
    subject_id      TEXT NOT NULL,       -- account (R1, R2, R4) or beneficiary (R3)
    customer_id     TEXT,                -- owner of subject account, NULL for external beneficiary
    window_start    TEXT NOT NULL,
    window_end      TEXT NOT NULL,
    alert_date      TEXT NOT NULL,
    value_usd       REAL NOT NULL,       -- value of the evidence that triggered the rule
    n_triggers      INTEGER NOT NULL,    -- raw rule hits merged into this alert
    priority_score  INTEGER NOT NULL,
    priority        TEXT NOT NULL,       -- High | Medium | Low
    reason          TEXT NOT NULL,       -- plain-English explanation
    metrics_json    TEXT NOT NULL        -- observed values vs configured thresholds
);
DROP TABLE IF EXISTS alert_evidence;
CREATE TABLE alert_evidence (alert_id TEXT, transaction_id TEXT, evidence_role TEXT);

-- analyst case review (seeded from data/reviews/seed_reviews.csv, updated by the dashboard)
CREATE TABLE IF NOT EXISTS alert_reviews (
    alert_id     TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'New',   -- New | Investigating | Closed
    disposition  TEXT,                          -- e.g. 'Escalate - refer for SAR decision' | 'No further action'
    analyst      TEXT,
    note         TEXT,
    updated_at   TEXT
);
