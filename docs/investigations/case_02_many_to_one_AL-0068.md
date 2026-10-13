# Case 02 — Eleven customers wiring the same new external beneficiary

> Sample investigation write-up on **synthetic data**. The disposition is an illustrative analyst conclusion.

| Field | Value |
|---|---|
| Alert | **AL-0068** (R3 Many-to-one beneficiary, Medium, score 45) |
| Subject | External beneficiary **EXT-BEN-9505** (not a bank customer) |
| Review window | 2025-11-09 → 2025-11-14 |
| Status / disposition | **Closed — Escalate, refer for SAR decision** |

## 1. Why was this flagged?
> 11 different accounts with no payment to EXT-BEN-9505 in the prior 60 days sent 11 payments totalling **$32,583** within **5.0 days**.

| Rule check | Observed | Threshold |
|---|---|---|
| New senders in window | 11 | ≥ 6 |
| Total received | $32,583 | ≥ $15,000 |
| Window length | 5.0 days | ≤ 7 days |

## 2. Evidence reviewed
- **Beneficiary history:** all 11 payments to EXT-BEN-9505 in the whole dataset fall inside this 5-day window. It had no history before and none after.
- **Payment shape:** one WIRE_OUT per sender, $1,867–$4,475 each, every one under $5,000.
- **Who the senders are:** 11 customers with different occupations and almost no links to each other (one small P2P between two of them in the whole year):

| Sender group | Count | WIRE_OUT count in 2025 | Read |
|---|---|---|---|
| Retail customers (nurse, retail workers, teacher, student, property owner) | 6 | 1–3 | A wire is rare for these customers; this one is out of pattern |
| Business owners (small business, restaurant) | 5 | 25 each (supplier payments) | Wires are routine, but this beneficiary is not one of their suppliers |

- One sender (student, C00958) only opened the relationship in April 2025.

## 3. Analyst conclusion
Many unrelated customers paying the same brand-new beneficiary in a few days, in similar sub-$5k amounts, has no obvious legitimate explanation in the data. Two readings are possible and both warrant escalation: (a) the beneficiary is a **collection account for a scam** (e.g. fake investment or invoice fraud) and our customers are victims, or (b) the senders are part of a **coordinated network** moving funds to one destination.

**Disposition:** Escalated — refer for SAR decision.
**Recommended next steps:** contact the six retail senders to ask about the payment purpose (victim check); check whether other beneficiaries received from the same group of senders; place the beneficiary on a watch list.

*Limitations:* the beneficiary is external, so its own account activity and ownership are not visible in this dataset.
