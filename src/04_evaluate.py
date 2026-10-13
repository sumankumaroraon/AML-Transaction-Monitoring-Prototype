"""
04_evaluate.py
Score the alerts against the planted (labeled) synthetic scenarios.

Matching rule: an alert "matches" a planted scenario when the alert's subject is the
scenario's subject (account or beneficiary) AND at least one of the alert's evidence
transactions is one of the scenario's planted transactions.

  precision     = alerts matching any planted scenario / all alerts
  recall        = planted scenarios matched by at least one alert / all planted scenarios
  alert volume  = number of alerts an analyst would need to review
  rule coverage = for each rule x scenario type, share of scenarios that rule caught

These numbers describe behaviour on SYNTHETIC scenarios only. They do not establish
how the rules would perform on real banking data.
"""
from __future__ import annotations

import copy
import importlib

import pandas as pd

from common import OUT_DIR, RULE_LABELS, connect, load_config

run_rules = importlib.import_module("03_run_rules").run_rules


def match(alerts: pd.DataFrame, evidence: pd.DataFrame, scen: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
    """Return alert_id x scenario_id pairs that match."""
    ev = evidence.merge(alerts[["alert_id", "subject_id", "rule_id"]], on="alert_id")
    pl = links.merge(scen[["scenario_id", "subject_id", "scenario_type", "variant"]], on="scenario_id")
    m = ev.merge(pl, on=["transaction_id", "subject_id"])
    return m[["alert_id", "rule_id", "scenario_id", "scenario_type", "variant"]].drop_duplicates()


def score(alerts, evidence, scen, links) -> dict:
    m = match(alerts, evidence, scen, links)
    n_alerts = len(alerts)
    tp_alerts = m.alert_id.nunique()
    caught = m.scenario_id.nunique()
    return {"alerts": n_alerts, "matched_alerts": tp_alerts,
            "precision": tp_alerts / n_alerts if n_alerts else float("nan"),
            "scenarios": len(scen), "scenarios_detected": caught, "recall": caught / len(scen), "_m": m}


def main():
    cfg = load_config()
    conn = connect()
    alerts = pd.read_sql("SELECT * FROM alerts", conn)
    evidence = pd.read_sql("SELECT * FROM alert_evidence", conn)
    scen = pd.read_sql("SELECT * FROM planted_scenarios", conn)
    links = pd.read_sql("SELECT * FROM planted_transactions", conn)
    benign = pd.read_sql("SELECT * FROM benign_lookalikes", conn)

    s = score(alerts, evidence, scen, links)
    m = s.pop("_m")

    # ---- overall + per rule
    rows = [{"scope": "All rules", **s}]
    for rid in sorted(alerts.rule_id.unique()):
        a = alerts[alerts.rule_id == rid]
        mm = m[m.rule_id == rid]
        rows.append({"scope": RULE_LABELS[rid], "alerts": len(a), "matched_alerts": mm.alert_id.nunique(),
                     "precision": mm.alert_id.nunique() / len(a), "scenarios": len(scen),
                     "scenarios_detected": mm.scenario_id.nunique(),
                     "recall": mm.scenario_id.nunique() / len(scen)})
    summary = pd.DataFrame(rows)
    summary["precision"] = summary.precision.round(3)
    summary["recall"] = summary.recall.round(3)

    # ---- scenario-level detection
    det = scen.copy()
    by = m.groupby("scenario_id").agg(detected_by=("rule_id", lambda x: ", ".join(sorted(set(x)))),
                                      alert_ids=("alert_id", lambda x: ", ".join(sorted(set(x)))))
    det = det.merge(by, left_on="scenario_id", right_index=True, how="left")
    det["detected"] = det.detected_by.notna()

    # ---- recall by scenario type and variant
    rec = det.groupby(["scenario_type", "variant"]).agg(scenarios=("scenario_id", "count"),
                                                       detected=("detected", "sum")).reset_index()
    rec["recall"] = (rec.detected / rec.scenarios).round(3)
    rec_type = det.groupby("scenario_type").agg(scenarios=("scenario_id", "count"),
                                               detected=("detected", "sum")).reset_index()
    rec_type["recall"] = (rec_type.detected / rec_type.scenarios).round(3)

    # ---- rule coverage matrix (share of each scenario type each rule caught)
    cov = m.groupby(["rule_id", "scenario_type"]).scenario_id.nunique().unstack(fill_value=0)
    totals = scen.groupby("scenario_type").size()
    cov = cov.reindex(columns=totals.index, fill_value=0).reindex(sorted(cfg["rules"]), fill_value=0)
    cov_pct = (cov / totals).round(3)
    cov_out = cov.astype(str) + "/" + totals.astype(str).reindex(cov.columns).values + \
        " (" + (cov_pct * 100).round(0).astype(int).astype(str) + "%)"
    cov_out.index = [RULE_LABELS[r] for r in cov_out.index]

    # ---- false-positive breakdown
    fp = alerts[~alerts.alert_id.isin(m.alert_id)].copy()

    def fp_cause(a):
        b = benign[(benign.subject_id == a.subject_id) &
                   (benign.window_start <= a.window_end) & (benign.window_end >= a.window_start)]
        if len(b):
            return "Planted benign look-alike: " + b.description.iloc[0]
        if a.window_start < "2025-03-01" and a.rule_id in ("R2_ACTIVITY_SPIKE", "R3_MANY_TO_ONE"):
            return "Cold start: little or no history at start of data"
        return "Organic background activity"
    fp["fp_cause"] = fp.apply(fp_cause, axis=1)
    fp_break = fp.groupby(["rule_id", "fp_cause"]).size().reset_index(name="alerts")

    # ---- threshold sensitivity: vary one parameter at a time
    sweeps = [
        ("R1_RAPID_PASS_THROUGH", "lookback_hours", [48, 72, 96, 144]),
        ("R2_ACTIVITY_SPIKE", "spike_multiplier", [3.0, 4.0, 5.0, 6.0, 8.0]),
        ("R3_MANY_TO_ONE", "min_new_senders", [4, 5, 6, 8, 10]),
        ("R3_MANY_TO_ONE", "apply_warmup", [0, 1]),
        ("R4_STRUCTURING", "band_pct", [0.80, 0.85, 0.90, 0.95]),
    ]
    sens = []
    for rid, param, values in sweeps:
        for v in values:
            c2 = copy.deepcopy(cfg)
            c2["rules"][rid][param] = v
            a2, e2 = run_rules(conn, c2)
            sc = score(a2, e2, scen, links)
            mm = sc["_m"]
            ra = a2[a2.rule_id == rid]
            sens.append({"rule": RULE_LABELS[rid], "parameter": param, "value": v,
                         "is_default": v == cfg["rules"][rid][param],
                         "rule_alerts": len(ra),
                         "rule_precision": round(mm[mm.rule_id == rid].alert_id.nunique() / len(ra), 3) if len(ra) else None,
                         "total_alerts": sc["alerts"], "overall_precision": round(sc["precision"], 3),
                         "overall_recall": round(sc["recall"], 3)})
    sens = pd.DataFrame(sens)

    OUT_DIR.mkdir(exist_ok=True)
    summary.to_csv(OUT_DIR / "evaluation_summary.csv", index=False)
    det.to_csv(OUT_DIR / "scenario_detection.csv", index=False)
    rec.to_csv(OUT_DIR / "recall_by_scenario_variant.csv", index=False)
    rec_type.to_csv(OUT_DIR / "recall_by_scenario_type.csv", index=False)
    cov_out.to_csv(OUT_DIR / "rule_coverage.csv")
    fp_break.to_csv(OUT_DIR / "false_positive_breakdown.csv", index=False)
    sens.to_csv(OUT_DIR / "threshold_sensitivity.csv", index=False)

    pd.set_option("display.width", 200)
    print(summary.to_string(index=False), "\n")
    print(rec.to_string(index=False), "\n")
    print(cov_out.to_string(), "\n")
    print(fp_break.to_string(index=False), "\n")
    print(det[~det.detected][["scenario_id", "scenario_type", "variant", "subject_id", "description"]].to_string(index=False), "\n")
    print(sens.to_string(index=False))


if __name__ == "__main__":
    main()
