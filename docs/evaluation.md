# Evaluation

> **Performance on synthetic scenarios does not establish effectiveness on real banking data.**
> The scenarios were designed by the same person who wrote the rules, the background activity is far more
> regular than real customer behaviour, and there are no unknown typologies in the data. Treat these numbers
> as a test that the rules work as designed — not as an estimate of real-world precision or recall.

## Method
- **Ground truth:** 44 planted scenarios (36 standard, 8 subtle) covering 284 transactions, plus 19 benign look-alike groups.
- **Match:** an alert matches a scenario when the alert's subject equals the scenario's subject **and** at least one evidence transaction is a planted transaction for that scenario.
- **Precision** = alerts matching any planted scenario ÷ all alerts.
- **Recall** = planted scenarios matched by at least one alert ÷ all planted scenarios.
- Reproduce with `python src/04_evaluate.py`.

## Headline (default thresholds)
| Metric | Value |
|---|---|
| Transactions monitored | 52,544 |
| Alerts to review | **72** (51 distinct subjects; 9 High · 56 Medium · 7 Low) |
| Precision | **81.9%** (59 / 72) |
| Recall | **90.9%** (40 / 44) |
| Recall — standard scenarios | 100% (36 / 36) |
| Recall — subtle scenarios | 50% (4 / 8) |

## By rule
| Rule | Alerts | Matched | Precision | Scenarios caught |
|---|---|---|---|---|
| R1 Rapid pass-through | 10 | 10 | 100.0% | 10 |
| R2 Activity spike | 39 | 31 | 79.5% | 31 |
| R3 Many-to-one beneficiary | 10 | 8 | 80.0% | 8 |
| R4 Below-threshold structuring | 13 | 10 | 76.9% | 10 |

## Rule coverage (share of each planted pattern each rule detects)
| Rule | Activity spike | Many-to-one | Rapid pass-through | Structuring |
|---|---|---|---|---|
| R1 Rapid pass-through | 0/12 | 0/8 | **10/12 (83%)** | 0/12 |
| R2 Activity spike | **11/12 (92%)** | 0/8 | 12/12 (100%) | 8/12 (67%) |
| R3 Many-to-one | 0/12 | **6/8 (75%)** | 2/12 (17%) | 0/12 |
| R4 Structuring | 0/12 | 0/8 | 0/12 | **10/12 (83%)** |

Reading the matrix: each pattern is caught best by its own rule, but **R2 acts as a safety net** — it caught both subtle pass-through cases that R1 missed (inflows spread over ~5–6 days, outside R1's 72-hour look-back) and one subtle structuring case. The trade-off is that R2 also produces most of the alert volume (39 of 72).

## Recall by pattern
| Pattern | Scenarios | Detected | Recall |
|---|---|---|---|
| Activity spike | 12 | 11 | 91.7% |
| Many-to-one | 8 | 6 | 75.0% |
| Rapid pass-through | 12 | 12 | 100.0% |
| Structuring | 12 | 11 | 91.7% |

## What was missed (4 scenarios, all "subtle" by design)
| Scenario | Why it was missed |
|---|---|
| S023 Activity spike | Inflow ~1.7x declared activity, well under the 5x / 3x multipliers |
| S031, S032 Many-to-one | Only 5 senders (rule needs 6) and totals under $15k |
| S043 Structuring | 6 deposits at 80–88% of the threshold, below the 90% band; $51k of deposits was not large enough relative to this customer's baseline to trip R2 |

## False positives (13 alerts)
All 13 unmatched alerts trace back to **planted benign look-alikes**:
| Rule | Cause | Alerts |
|---|---|---|
| R2 | Home sale proceeds / car purchase (one-off life event) | 6 |
| R2 | Community fundraiser collected from friends | 2 |
| R3 | Community fundraiser collected from friends | 2 |
| R4 | Cash-intensive restaurant depositing weekend takings near the threshold | 3 |

No false positives came from ordinary background activity. That is a sign the synthetic background is **too clean**, not that the rules are precise — real data would produce many more.

## Threshold sensitivity (one parameter changed at a time)
Full table: `outputs/threshold_sensitivity.csv`.
| Change | Total alerts | Precision | Recall |
|---|---|---|---|
| **Default** | **72** | **81.9%** | **90.9%** |
| R1 look-back 72h → 48h | 67 | 80.6% | 90.9% |
| R1 look-back 72h → 144h | 74 | 82.4% | 90.9% |
| R2 multiplier 5x → 3x | 76 | 82.9% | 93.2% |
| R2 multiplier 5x → 8x | 65 | 80.0% | 86.4% |
| R3 min new senders 6 → 4 | 74 | 82.4% | 90.9% |
| R3 min new senders 6 → 10 | 68 | 80.9% | 86.4% |
| R3 warm-up off | 85 | 69.4% | 90.9% |
| R4 band 90% → 85% | 74 | 82.4% | 93.2% |
| R4 band 90% → 95% | 62 | 82.3% | 86.4% |

Takeaways: widening the R4 band to 85% or lowering the R2 multiplier to 3x each recover one more subtle scenario for a few extra alerts; the R3 warm-up has the largest effect on alert volume.

## Limitations
- Synthetic, self-designed scenarios; no unknown typologies; background behaviour is regular.
- No balances, device/IP, geography, KYC documents, or network data beyond transactions.
- Rules run in batch on a full year; no real-time scoring.
- Alerts are not merged across rules into cases, so one customer can generate several alerts.
- Reviews in `data/reviews/seed_reviews.csv` are illustrative sample reviews.
