"""
03_run_rules.py
Run the four explainable monitoring rules (SQL), merge overlapping hits into
alerts, attach the evidence transactions, score priority and write a plain-English
reason for every alert.

Outputs: tables alerts / alert_evidence in the SQLite DB, plus
         outputs/alerts.csv and outputs/alert_evidence.csv
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd

from common import OUT_DIR, RULE_FILES, connect, load_config, named_sql

FMT = "%Y-%m-%d %H:%M:%S"


def _ts(s: str) -> datetime:
    return datetime.strptime(s, FMT)


def rule_params(cfg: dict, rule_id: str) -> dict:
    p = {k: v for k, v in cfg["rules"][rule_id].items() if k != "description"}
    p["threshold"] = cfg["monitoring_threshold_usd"]
    return p


def merge_triggers(trig: pd.DataFrame, gap_days: int) -> list[pd.DataFrame]:
    """Group raw rule hits for the same subject whose windows overlap or sit within gap_days."""
    clusters = []
    for _, g in trig.sort_values("window_start").groupby("subject_id", sort=False):
        current, end = [], None
        for _, row in g.sort_values("window_start").iterrows():
            ws, we = _ts(row.window_start), _ts(row.window_end)
            if current and ws > end + timedelta(days=gap_days):
                clusters.append(pd.DataFrame(current))
                current, end = [], None
            current.append(row)
            end = we if end is None else max(end, we)
        if current:
            clusters.append(pd.DataFrame(current))
    return clusters


def describe(rule_id: str, c: pd.DataFrame, p: dict, ev: pd.DataFrame, tx_lookup: dict) -> tuple[str, list, float]:
    """Return (reason text, metrics list, value_usd) for one merged alert."""
    if rule_id == "R1_RAPID_PASS_THROUGH":
        best = c.sort_values(["in_count", "out_usd"], ascending=False).iloc[0]
        out = tx_lookup[best.anchor_txn]
        reason = (f"{int(best.in_count)} incoming transfers from {int(best.in_senders)} different senders "
                  f"(${best.in_usd:,.0f}) arrived within {p['lookback_hours']}h; then ${best.out_usd:,.0f} "
                  f"({best.out_ratio:.0%} of that inflow) left by {out['transaction_type']} to {out['receiver_account']} "
                  f"on {best.anchor_ts[:16]}, {best.hours_in_to_out:.0f}h after the first incoming transfer.")
        metrics = [
            ("Incoming transfers in look-back window", int(best.in_count), f">= {p['min_in_count']}"),
            ("Distinct senders", int(best.in_senders), f">= {p['min_distinct_senders']}"),
            ("Outgoing transfer (USD)", round(best.out_usd, 2), f">= {p['min_out_usd']:,}"),
            ("Outgoing / incoming ratio", round(best.out_ratio, 3), f"{p['min_out_ratio']} - {p['max_out_ratio']}"),
            ("Hours from first inflow to outflow", best.hours_in_to_out, f"<= {p['lookback_hours']}"),
        ]
        value = float(c.out_usd.sum())
    elif rule_id == "R2_ACTIVITY_SPIKE":
        best = c.sort_values("x_baseline", ascending=False).iloc[0]
        month_name = datetime.strptime(best.month, "%Y-%m").strftime("%B %Y")
        others = [m for m in c.month if m != best.month]
        extra = f" Activity was also elevated in {', '.join(others)}." if others else ""
        reason = (f"Account activity in {month_name} was ${best.month_usd:,.0f} across {int(best.month_txns)} "
                  f"transactions: {best.x_baseline:.1f}x its baseline of ${best.baseline_usd:,.0f} "
                  f"({best.baseline_source}) and {best.x_expected:.1f}x the customer's declared expected "
                  f"activity of ${best.expected_usd:,.0f}/month.{extra}")
        metrics = [
            ("Month activity, in + out (USD)", round(best.month_usd, 2), f">= {p['min_month_usd']:,}"),
            ("Multiple of baseline", best.x_baseline, f">= {p['spike_multiplier']}"),
            ("Multiple of declared expected activity", best.x_expected, f">= {p['profile_multiplier']}"),
            ("Baseline used", round(best.baseline_usd, 2), best.baseline_source),
        ]
        value = float(c.month_usd.max())
    elif rule_id == "R3_MANY_TO_ONE":
        best = c.sort_values(["new_senders", "total_usd"], ascending=False).iloc[0]
        span = (_ts(best.window_end) - _ts(best.window_start)).total_seconds() / 86400
        reason = (f"{int(best.new_senders)} different accounts with no payment to {best.subject_id} in the prior "
                  f"{p['relationship_days']} days sent {int(best.payments)} payments totalling ${best.total_usd:,.0f} "
                  f"within {span:.1f} days.")
        metrics = [
            ("New senders in window", int(best.new_senders), f">= {p['min_new_senders']}"),
            ("All distinct senders", int(best.senders), "info"),
            ("Total received (USD)", round(best.total_usd, 2), f">= {p['min_total_usd']:,}"),
            ("Window length (days)", round(span, 1), f"<= {p['window_days']}"),
        ]
        value = float(tx_lookup_sum(ev, tx_lookup))
    else:  # R4
        best = c.sort_values(["near_threshold_count", "total_usd"], ascending=False).iloc[0]
        span = (_ts(best.window_end) - _ts(best.window_start)).total_seconds() / 86400
        n_all = len(ev)
        reason = (f"{n_all} cash deposits between ${ev_amounts(ev, tx_lookup).min():,.0f} and "
                  f"${ev_amounts(ev, tx_lookup).max():,.0f} were made, each within "
                  f"{(1 - p['band_pct']):.0%} below the ${p['threshold']:,} monitoring threshold; "
                  f"{int(best.near_threshold_count)} of them fell inside {span:.1f} days.")
        metrics = [
            ("Near-threshold cash deposits in window", int(best.near_threshold_count), f">= {p['min_count']}"),
            ("Deposit band (USD)", f"{best.min_deposit_usd:,.0f} - {best.max_deposit_usd:,.0f}",
             f"{p['band_pct'] * p['threshold']:,.0f} - {p['threshold']:,} (excl.)"),
            ("Window length (days)", round(span, 1), f"<= {p['window_days']}"),
            ("Total deposited (USD)", round(best.total_usd, 2), "info"),
        ]
        value = float(tx_lookup_sum(ev, tx_lookup))
    metrics = [{"metric": m, "observed": o, "threshold": t} for m, o, t in metrics]
    return reason, metrics, value


def ev_amounts(ev, tx_lookup):
    return pd.Series([tx_lookup[t]["amount_usd"] for t in ev.transaction_id])


def tx_lookup_sum(ev, tx_lookup):
    return ev_amounts(ev, tx_lookup).sum()


def run_rules(conn, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    tx = pd.read_sql("SELECT transaction_id, ts, sender_account, receiver_account, amount_usd, transaction_type "
                     "FROM transactions", conn)
    tx_lookup = tx.set_index("transaction_id").to_dict("index")
    acct = pd.read_sql("SELECT account_id, customer_id, open_date FROM accounts", conn).set_index("account_id")

    alerts, evidence = [], []
    for rule_id, fname in RULE_FILES.items():
        sql = named_sql(fname)
        p = rule_params(cfg, rule_id)
        trig = pd.read_sql(sql["triggers"], conn, params=p)
        if trig.empty:
            continue
        for c in merge_triggers(trig, cfg["alert_merge_gap_days"]):
            subject = c.subject_id.iloc[0]
            ws, we = c.window_start.min(), c.window_end.max()
            ev = pd.read_sql(sql["evidence"], conn, params={**p, "subject_id": subject,
                                                             "window_start": ws, "window_end": we})
            reason, metrics, value = describe(rule_id, c, p, ev, tx_lookup)
            alerts.append({
                "rule_id": rule_id, "subject_id": subject,
                "customer_id": acct.customer_id.get(subject),
                "window_start": ws, "window_end": we, "alert_date": we[:10],
                "value_usd": round(value, 2), "n_triggers": len(c),
                "reason": reason, "metrics_json": json.dumps(metrics),
                "_evidence": ev,
            })

    al = pd.DataFrame(alerts)
    if al.empty:
        return al, pd.DataFrame(columns=["alert_id", "transaction_id", "evidence_role"])
    al = al.sort_values(["alert_date", "rule_id", "subject_id"]).reset_index(drop=True)
    al["alert_id"] = [f"AL-{i + 1:04d}" for i in range(len(al))]

    # ---- priority scoring (documented in docs/assumptions_and_thresholds.md)
    pr = cfg["priority"]
    scores = []
    for _, a in al.iterrows():
        s = pr["base_score"][a.rule_id]
        if a.value_usd >= 50000:
            s += pr["value_50k_bonus"]
        elif a.value_usd >= 25000:
            s += pr["value_25k_bonus"]
        if a.subject_id in acct.index:
            age = (_ts(a.window_end) - datetime.strptime(acct.open_date[a.subject_id], "%Y-%m-%d")).days
            if age <= pr["new_account_days"]:
                s += pr["new_account_bonus"]
        near = al[(al.subject_id == a.subject_id) & (al.rule_id != a.rule_id)]
        near = near[(pd.to_datetime(near.alert_date) - pd.to_datetime(a.alert_date)).abs().dt.days <= 31]
        if len(near):
            s += pr["multi_rule_bonus"]
        scores.append(s)
    al["priority_score"] = scores
    al["priority"] = pd.cut(al.priority_score, [-1, pr["medium_min"] - 1, pr["high_min"] - 1, 999],
                            labels=["Low", "Medium", "High"]).astype(str)

    ev_rows = []
    for _, a in al.iterrows():
        e = a["_evidence"].copy()
        e.insert(0, "alert_id", a.alert_id)
        ev_rows.append(e)
    evd = pd.concat(ev_rows, ignore_index=True)
    al = al.drop(columns="_evidence")
    cols = ["alert_id", "rule_id", "subject_id", "customer_id", "window_start", "window_end", "alert_date",
            "value_usd", "n_triggers", "priority_score", "priority", "reason", "metrics_json"]
    return al[cols], evd


def main():
    cfg = load_config()
    conn = connect()
    al, evd = run_rules(conn, cfg)
    conn.execute("DELETE FROM alerts")
    conn.execute("DELETE FROM alert_evidence")
    al.to_sql("alerts", conn, if_exists="append", index=False)
    evd.to_sql("alert_evidence", conn, if_exists="append", index=False)
    conn.commit()
    OUT_DIR.mkdir(exist_ok=True)
    al.to_csv(OUT_DIR / "alerts.csv", index=False)
    evd.to_csv(OUT_DIR / "alert_evidence.csv", index=False)
    print(f"alerts={len(al)} evidence rows={len(evd)}")
    print(al.groupby(["rule_id", "priority"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
