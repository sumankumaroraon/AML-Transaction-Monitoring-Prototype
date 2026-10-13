# Case 03 — Near-threshold cash deposits at a restaurant (false positive)

> Sample investigation write-up on **synthetic data**. This alert was triggered by a *planted benign look-alike*
> (see `data/labels/benign_lookalikes.csv`, B17) — it is included to show how an alert is closed with reasons.

| Field | Value |
|---|---|
| Alert | **AL-0001** (R4 Below-threshold structuring, Medium, score 50) |
| Subject | Account A000928 (business checking) · Customer C00639 |
| Profile (KYC) | Restaurant Owner · business · declared expected activity **$42,500/month** · customer since 2018-05-05 |
| Review window | 2025-03-08 → 2025-03-14 |
| Status / disposition | **Closed — No further action, activity explained** |

## 1. Why was this flagged?
> 3 cash deposits between $9,132 and $9,777 were made, each within 10% below the $10,000 monitoring threshold; all 3 fell inside 6.0 days.

| Rule check | Observed | Threshold |
|---|---|---|
| Near-threshold cash deposits | 3 | ≥ 3 within 10 days |
| Deposit band | $9,132 – $9,777 | $9,000 – $9,999 |

## 2. Evidence reviewed
- **Cash is normal for this business.** The account made **22 cash deposits in 2025 ($214k)**, consistent with a cash-intensive restaurant.
- **The customer does not avoid the threshold.** **10 of those 22 deposits were $10,000 or more** (e.g. $14,460 and $13,594 in January, $14,032 in April, three deposits of $11,952–$13,996 in August). Someone deliberately structuring would not regularly deposit above the threshold.
- **Size fits the profile.** March money-in was $54.6k against declared expected activity of $42.5k/month — elevated but in line with other busy months (Aug $39.4k, Oct $38.8k).
- **No rapid outflow.** March outgoing payments were the usual supplier wires ($7.4k, $8.5k) and payroll ($11.9k); the cash was not moved straight out.
- **Timing:** deposits fall after weekend trading days, matching restaurant takings.

## 3. Analyst conclusion
The three deposits look like ordinary weekend takings that happened to land just under $10,000. The customer's year-long pattern of depositing *above* the threshold contradicts the structuring hypothesis, and volumes fit the declared business profile.

**Disposition:** Closed — no further action, activity explained.
**Tuning note:** R4 produced 3 alerts on cash-intensive restaurants, all benign. A possible refinement is to suppress R4 when a customer's own history shows regular deposits above the threshold, or to raise `min_count` for cash-intensive business segments. This would need re-testing because it could also hide real structuring by business customers.
