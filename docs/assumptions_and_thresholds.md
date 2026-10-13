# Assumptions and thresholds

> **These are project assumptions for a synthetic simulation, not legal or regulatory requirements.**
> All values live in `config/rules_config.json` and can be changed without touching code.
> An alert is an **investigation trigger**, not proof of money laundering.

## Monitoring rules

| Rule | Pattern | Parameters (default) | Why this design |
|---|---|---|---|
| **R1 Rapid pass-through** | Several incoming transfers from different senders, followed by one large outgoing transfer of a similar amount | look-back **72h**; ≥ **4** incoming (P2P / WIRE_IN / CASH_DEPOSIT) from ≥ **3** distinct senders; outgoing (WIRE_OUT / P2P / CASH_WITHDRAWAL) ≥ **$8,000** and **70–120%** of the inflow | "Money in, money out" with little retention is the core mule signal. The ratio band avoids flagging businesses paying large bills from existing balances |
| **R2 Activity spike** | Monthly activity (in + out) far above normal | ≥ **5x** baseline **and** ≥ **3x** declared expected activity **and** ≥ **$20,000** | Two baselines: the account's own trailing 3-month average (behaviour) and the KYC declaration (profile). Requiring both reduces noise from naturally variable accounts. Accounts with < 3 months of history use the declared value as baseline |
| **R3 Many-to-one beneficiary** | Many different accounts paying the same beneficiary in a short window | ≥ **6 new** senders and ≥ **$15,000** within **7 days**; a sender is "new" if it did not pay that beneficiary in the previous **60 days**; warm-up on | The "new sender" condition suppresses routine fan-in (tenants paying rent, customers paying a shared supplier) |
| **R4 Below-threshold structuring** | Repeated cash deposits just below the monitoring threshold | threshold **$10,000** (configurable); "just below" = **90–100%** of threshold; ≥ **3** deposits within **10 days** | Keeps the threshold a parameter rather than hard-coding a legal figure |

### Warm-up period (R3)
Whether a sender is "new" can only be judged once 60 days of history exist. The first run without a warm-up produced **13 extra alerts in January–February**, all on business suppliers (`EXT-SUP-…`) that are paid by several businesses each month — the rule simply had no history yet. With `apply_warmup = 1`, R3 does not score windows that start in the first 60 days of data. Effect: alerts 85 → 72, overall precision 69.4% → 81.9%, recall unchanged (90.9%). See `outputs/threshold_sensitivity.csv`.

## Alert construction
- Each rule returns raw "trigger" rows from SQL (one per anchor transaction or account-month).
- Triggers for the same rule and subject are **merged** into one alert when their windows overlap or are within **7 days**.
- Every alert stores its evidence transactions, the observed metrics vs thresholds, and a plain-English reason.
- Different rules are **not** merged: a customer hit by three rules has three alerts, linked on the alert detail page.

## Priority score
| Component | Points |
|---|---|
| Base by rule | R1 40 · R4 40 · R3 35 · R2 25 |
| Value of evidence ≥ $25k / ≥ $50k | +10 / +15 |
| Subject account opened ≤ 180 days before the alert | +10 |
| Same subject has an alert from another rule within 31 days | +15 |
| **Level** | **High ≥ 60 · Medium 40–59 · Low < 40** |

## Data-generation assumptions
- 1,000 customers, 1,458 accounts, 12 months, seed 42.
- Each customer's real activity is drawn around their declared profile (log-normal noise), so the profile is informative but not exact.
- P2P transfers go to a small fixed "friends" network per customer, so normal P2P does not create random fan-in.
- Fixed FX rates; no balances, devices, IP addresses, or KYC documents are simulated.
- **Subtle variants** (8 of 44 scenarios) were planted near or just outside thresholds on purpose, to show what the rules miss.
