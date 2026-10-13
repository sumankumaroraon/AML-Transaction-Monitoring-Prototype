# Case 01 — Rapid pass-through on a retiree account

> Sample investigation write-up on **synthetic data**. Customer, accounts and counterparties are simulated.
> The disposition below is an illustrative analyst conclusion, not a legal finding.

| Field | Value |
|---|---|
| Alerts | **AL-0042** (R1 Rapid pass-through, High, score 65) · linked: AL-0040 (R3 Many-to-one), AL-0049 (R2 Activity spike) |
| Subject | Account A000464 (checking) · Customer C00323 |
| Profile (KYC) | Retiree · retail · declared expected activity **$4,000/month** · customer since 2012-04-22 |
| Review window | 2025-09-10 → 2025-09-12 |
| Status / disposition | **Closed — Escalate, refer for SAR decision** |

## 1. Why was this flagged?
Three independent rules fired on the same account within the same week:

| Rule | What it saw | Configured threshold |
|---|---|---|
| R1 Rapid pass-through | 9 incoming transfers from 9 different senders ($30,299), then a **$25,989 WIRE_OUT (86% of the inflow)** 54 hours after the first credit | ≥ 4 credits from ≥ 3 senders within 72h, outflow ≥ $8,000 and 70–120% of inflow |
| R3 Many-to-one | 7 internal accounts with no prior payment to this account sent $23,666 within 0.6 days | ≥ 6 new senders, ≥ $15,000 within 7 days |
| R2 Activity spike | September activity $62,070 = **10.0x** the trailing 3-month average ($6,193) and **15.5x** declared expected activity | ≥ 5x baseline, ≥ 3x declared, ≥ $20,000 |

## 2. Evidence reviewed
**Normal pattern (Jan–Aug 2025).** One government benefit credit (EXT-GOV-SSA) per month, a few bill payments, card purchases and small P2P transfers. Largest single outgoing payment before September: **$1,472**. Monthly money-in stayed between $2.3k and $4.7k.

**Activity under review.**

| When | What | Amount (USD) |
|---|---|---|
| Sep 10 12:17 → Sep 11 07:03 (~19h) | 7 P2P transfers from 7 different internal customers + 2 international wires (EUR, GBP) from two external originators | $30,299 total ($2,042–$4,591 each) |
| Sep 12 18:23 | WIRE_OUT to **EXT-BEN-9002** | $25,989 |

Checks performed:
- **Relationship with senders:** none of the 9 senders had ever paid this account before (0 prior transactions in 2025).
- **Destination:** EXT-BEN-9002 appears exactly once in the dataset — this wire. No prior payment history to it.
- **Retention:** ~86% of the money left within 2.3 days; balance did not stay in the account.
- **Fit with profile:** a retiree on benefit income receiving business-like credits from unrelated people, including cross-border wires, is inconsistent with the declared profile.
- **After the event:** October–December returned to the normal pattern (single benefit credit, small spending).

## 3. Analyst conclusion
The account behaved as a **pass-through**: funds from many unrelated sources were collected and forwarded in one wire to a new beneficiary, with no apparent economic purpose for this customer. This pattern is consistent with money-mule activity; the customer may also be a **victim** (e.g. recruited through a romance or job scam), which the referral should note.

**Disposition:** Escalated — refer for SAR decision. AL-0040 and AL-0049 closed as *linked to escalated case*.
**Recommended next steps:** request the customer's explanation of the senders and the beneficiary; review the 9 sender accounts for similar outbound patterns; consider outreach in case the customer is being exploited.

*Limitations:* synthetic data only; no balances, device/IP, or KYC documents were available to the reviewer.
