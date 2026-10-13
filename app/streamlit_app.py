"""
AML Transaction Monitoring - Investigation Dashboard (Streamlit)
Synthetic data only. A portfolio prototype, not a production compliance system.

Run:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "aml_monitoring.db"
OUT = ROOT / "outputs"
sys.path.insert(0, str(ROOT / "src"))

RULE_LABELS = {
    "R1_RAPID_PASS_THROUGH": "R1 Rapid pass-through",
    "R2_ACTIVITY_SPIKE": "R2 Activity spike",
    "R3_MANY_TO_ONE": "R3 Many-to-one beneficiary",
    "R4_STRUCTURING": "R4 Below-threshold structuring",
}
# categorical slots 1-4 of the reference palette, fixed order per rule
RULE_COLORS = {
    "R1 Rapid pass-through": "#2a78d6",
    "R2 Activity spike": "#eb6834",
    "R3 Many-to-one beneficiary": "#1baf7a",
    "R4 Below-threshold structuring": "#eda100",
}
PRIORITY_ORDER = ["High", "Medium", "Low"]
PRIORITY_COLORS = {"High": "#1c4f8f", "Medium": "#4f93e0", "Low": "#a9cbf2"}  # one hue, dark -> light
STATUSES = ["New", "Investigating", "Closed"]
DISPOSITIONS = ["", "Escalate - refer for SAR decision", "No further action - activity explained",
                "Linked to escalated case", "Request more information"]
INK, MUTED, GRID = "#0b0b0b", "#6b6a66", "#e7e6e2"

st.set_page_config(page_title="AML Monitoring Prototype", page_icon="🔎", layout="wide")


# ------------------------------------------------------------------ data access
def ensure_db():
    if not DB.exists():
        with st.spinner("Building the database from the synthetic CSVs (first run)..."):
            for script in ("02_load_sqlite.py", "03_run_rules.py"):
                subprocess.run([sys.executable, str(ROOT / "src" / script)], check=True, cwd=ROOT / "src")


def q(sql: str, params=()) -> pd.DataFrame:
    import sqlite3
    with sqlite3.connect(DB) as conn:
        return pd.read_sql(sql, conn, params=params)


@st.cache_data
def load_static():
    daily = q("SELECT * FROM v_daily_volume ORDER BY day")
    customers = q("SELECT * FROM customers")
    accounts = q("SELECT * FROM accounts")
    return daily, customers, accounts


def load_queue() -> pd.DataFrame:
    df = q("SELECT * FROM v_alert_queue ORDER BY priority_score DESC, alert_date")
    df["rule"] = df.rule_id.map(RULE_LABELS)
    return df


def save_review(alert_id, status, disposition, analyst, note):
    import sqlite3
    with sqlite3.connect(DB) as conn:
        conn.execute(
            """INSERT INTO alert_reviews(alert_id, status, disposition, analyst, note, updated_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(alert_id) DO UPDATE SET status=excluded.status, disposition=excluded.disposition,
               analyst=excluded.analyst, note=excluded.note, updated_at=excluded.updated_at""",
            (alert_id, status, disposition or None, analyst, note, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


def style(fig, height=320, legend=True):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="white",
                      paper_bgcolor="white", font=dict(color=INK, size=13), showlegend=legend,
                      legend=dict(orientation="h", y=-0.18, title=None),
                      title_font=dict(size=15))
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED))
    return fig


def money(x) -> str:
    return f"${x:,.0f}"


# ------------------------------------------------------------------ pages
def page_overview(queue, daily):
    st.subheader("Monitoring overview")
    d = daily.assign(day=pd.to_datetime(daily.day)).set_index("day")
    weekly = d.resample("W-SUN").agg(txn_count=("txn_count", "sum"), value_usd=("value_usd", "sum"),
                                     days=("txn_count", "size")).reset_index()
    weekly = weekly[weekly.days == 7]  # drop partial first/last weeks
    c = st.columns(5)
    c[0].metric("Transactions", f"{daily.txn_count.sum():,}")
    c[1].metric("Value (USD)", f"${daily.value_usd.sum() / 1e6:,.1f}M")
    c[2].metric("Alerts", f"{len(queue):,}")
    c[3].metric("High priority", f"{(queue.priority == 'High').sum():,}")
    c[4].metric("Open (New + Investigating)", f"{(queue.status != 'Closed').sum():,}")

    l, r = st.columns(2)
    f1 = px.line(weekly, x="day", y="txn_count", title="Weekly transaction count")
    f1.update_traces(line=dict(width=2, color="#2a78d6"),
                     hovertemplate="Week ending %{x|%b %d}<br>%{y:,} transactions<extra></extra>")
    f1.update_layout(hovermode="x unified")
    l.plotly_chart(style(f1, legend=False).update_yaxes(title=None).update_xaxes(title=None), use_container_width=True)
    f2 = px.line(weekly, x="day", y="value_usd", title="Weekly transaction value (USD)")
    f2.update_traces(line=dict(width=2, color="#2a78d6"),
                     hovertemplate="Week ending %{x|%b %d}<br>$%{y:,.0f}<extra></extra>")
    f2.update_layout(hovermode="x unified")
    r.plotly_chart(style(f2, legend=False).update_yaxes(title=None, tickprefix="$").update_xaxes(title=None),
                   use_container_width=True)

    l, r = st.columns(2)
    bp = queue.groupby(["rule", "priority"]).size().reset_index(name="alerts")
    f3 = px.bar(bp, y="rule", x="alerts", color="priority", orientation="h", title="Alerts by rule and priority",
                category_orders={"priority": PRIORITY_ORDER, "rule": list(RULE_COLORS)},
                color_discrete_map=PRIORITY_COLORS, text="alerts")
    f3.update_traces(marker_line_color="white", marker_line_width=2, textposition="inside",
                     hovertemplate="%{y}<br>%{fullData.name}: %{x} alerts<extra></extra>")
    l.plotly_chart(style(f3, 340).update_yaxes(title=None).update_xaxes(title=None), use_container_width=True)
    bm = queue.assign(month=pd.to_datetime(queue.alert_date).dt.strftime("%Y-%m")) \
        .groupby(["month", "rule"]).size().reset_index(name="alerts")
    f4 = px.bar(bm, x="month", y="alerts", color="rule", title="Alerts by month and rule",
                color_discrete_map=RULE_COLORS, category_orders={"rule": list(RULE_COLORS)})
    f4.update_traces(marker_line_color="white", marker_line_width=2,
                     hovertemplate="%{x}<br>%{fullData.name}: %{y}<extra></extra>")
    r.plotly_chart(style(f4, 340).update_yaxes(title=None).update_xaxes(title=None), use_container_width=True)

    st.markdown("**Review status**")
    sc = queue.groupby(["status", "priority"]).size().unstack(fill_value=0).reindex(STATUSES, fill_value=0)
    sc = sc.reindex(columns=PRIORITY_ORDER, fill_value=0)
    sc["Total"] = sc.sum(axis=1)
    st.dataframe(sc, use_container_width=True)


def page_queue(queue):
    st.subheader("Alert queue")
    f = st.columns(4)
    rules = f[0].multiselect("Rule", list(RULE_LABELS.values()), default=list(RULE_LABELS.values()))
    pri = f[1].multiselect("Priority", PRIORITY_ORDER, default=PRIORITY_ORDER)
    stat = f[2].multiselect("Status", STATUSES, default=STATUSES)
    search = f[3].text_input("Search subject / customer", "")
    v = queue[queue.rule.isin(rules) & queue.priority.isin(pri) & queue.status.isin(stat)]
    if search:
        s = search.strip().upper()
        v = v[v.subject_id.str.upper().str.contains(s) | v.customer_id.fillna("").str.upper().str.contains(s)]
    st.caption(f"{len(v)} alerts shown. Select an alert ID on the Alert detail page to investigate it.")
    show = v[["alert_id", "priority", "priority_score", "rule", "subject_id", "customer_id", "occupation",
              "alert_date", "value_usd", "status", "reason"]].rename(columns={"value_usd": "value (USD)"})
    st.dataframe(show, use_container_width=True, hide_index=True, height=560,
                 column_config={"value (USD)": st.column_config.NumberColumn(format="$%,.0f"),
                                "reason": st.column_config.TextColumn(width="large")})


def page_alert(queue, customers, accounts, alert_id):
    ids = queue.alert_id.tolist()
    idx = ids.index(alert_id) if alert_id in ids else 0
    alert_id = st.selectbox("Alert", ids, index=idx,
                            format_func=lambda a: f"{a} · {queue.set_index('alert_id').loc[a, 'priority']} · "
                                                  f"{queue.set_index('alert_id').loc[a, 'rule']} · "
                                                  f"{queue.set_index('alert_id').loc[a, 'subject_id']}")
    a = q("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)).iloc[0]
    rv = queue.set_index("alert_id").loc[alert_id]
    ev = q("""SELECT t.transaction_id, t.ts, t.sender_account, t.receiver_account, t.amount, t.currency,
                     t.amount_usd, t.transaction_type, e.evidence_role
              FROM alert_evidence e JOIN transactions t USING(transaction_id)
              WHERE e.alert_id = ? ORDER BY t.ts""", (alert_id,))

    st.markdown(f"### {alert_id} — {RULE_LABELS[a.rule_id]}")
    c = st.columns([1.1, 1.5, 1.1, 1.2, 1])
    c[0].metric("Priority", f"{a.priority} ({a.priority_score})")
    c[1].metric("Subject", a.subject_id)
    c[2].metric("Customer", a.customer_id or "External")
    c[3].metric("Value in evidence", money(a.value_usd))
    c[4].metric("Review status", rv.status)

    # ---- 1. why was this flagged
    st.markdown("#### 1 · Why was this flagged?")
    st.info(a.reason.replace("$", "\\$"))
    m = pd.DataFrame(json.loads(a.metrics_json)).rename(columns={"metric": "Rule check", "observed": "Observed",
                                                                  "threshold": "Configured threshold"})
    def fmt(v):
        if isinstance(v, (int, float)):
            return f"{v:,.0f}" if float(v).is_integer() or abs(v) >= 1000 else f"{v:,.2f}"
        return str(v)
    m["Observed"] = m["Observed"].map(fmt)
    st.dataframe(m, hide_index=True, use_container_width=True)
    st.caption("Thresholds are project assumptions in config/rules_config.json, not legal requirements. "
               "An alert is a trigger for review, not proof of money laundering.")

    # ---- 2. evidence
    st.markdown("#### 2 · What evidence supports review?")
    l, r = st.columns([3, 2])
    evp = ev.assign(ts=pd.to_datetime(ev.ts))
    fig = px.scatter(evp, x="ts", y="amount_usd", color="evidence_role", title="Evidence transactions over time",
                     hover_data={"transaction_id": True, "sender_account": True, "receiver_account": True,
                                 "transaction_type": True, "ts": "|%Y-%m-%d %H:%M", "amount_usd": ":$,.0f",
                                 "evidence_role": False},
                     color_discrete_sequence=["#2a78d6", "#eb6834", "#1baf7a"])
    fig.update_traces(marker=dict(size=11, line=dict(color="white", width=2)))
    l.plotly_chart(style(fig, 320).update_yaxes(title=None, tickprefix="$").update_xaxes(title=None),
                   use_container_width=True)
    with r:
        summ = ev.groupby("evidence_role").agg(transactions=("transaction_id", "count"),
                                               total_usd=("amount_usd", "sum"),
                                               counterparties=("sender_account", "nunique")).reset_index()
        summ["total_usd"] = summ.total_usd.map(money)
        st.markdown("**Evidence summary**")
        st.dataframe(summ, hide_index=True, use_container_width=True)
        if a.customer_id:
            cu = customers.set_index("customer_id").loc[a.customer_id]
            acc = accounts[accounts.customer_id == a.customer_id]
            st.markdown("**Customer profile (KYC)**")
            st.dataframe(pd.DataFrame({
                "Field": ["Occupation", "Segment", "Declared expected activity", "Customer since", "Accounts"],
                "Value": [cu.occupation, cu.customer_segment, f"{money(cu.expected_monthly_activity_usd)}/month",
                          cu.account_opening_date, ", ".join(f"{x.account_id} ({x.account_type})"
                                                             for x in acc.itertuples())]}),
                hide_index=True, use_container_width=True)
        else:
            st.markdown("**Senders to this external beneficiary**")
            snd = q("""SELECT a.account_id, c.customer_id, c.occupation, c.expected_monthly_activity_usd AS expected_usd,
                              (SELECT COUNT(*) FROM transactions x WHERE x.sender_account = a.account_id
                                 AND x.transaction_type = 'WIRE_OUT') AS wires_in_year
                       FROM accounts a JOIN customers c USING(customer_id)
                       WHERE a.account_id IN (SELECT sender_account FROM alert_evidence e
                                              JOIN transactions t USING(transaction_id) WHERE e.alert_id = ?)""",
                    (alert_id,))
            st.dataframe(snd, hide_index=True, use_container_width=True, height=240)
    st.dataframe(ev, hide_index=True, use_container_width=True,
                 column_config={"amount_usd": st.column_config.NumberColumn(format="$%,.2f")})

    if a.customer_id:
        hist = q("SELECT * FROM v_customer_monthly WHERE customer_id = ? ORDER BY month", (a.customer_id,))
        expected = customers.set_index("customer_id").loc[a.customer_id, "expected_monthly_activity_usd"]
        hm = hist.melt(id_vars="month", value_vars=["money_in_usd", "money_out_usd"], var_name="flow",
                       value_name="usd")
        hm["flow"] = hm.flow.map({"money_in_usd": "Money in", "money_out_usd": "Money out"})
        f2 = px.bar(hm, x="month", y="usd", color="flow", barmode="group",
                    title="Customer 12-month history vs declared expected activity",
                    color_discrete_map={"Money in": "#2a78d6", "Money out": "#eb6834"})
        f2.update_traces(marker_line_color="white", marker_line_width=2,
                         hovertemplate="%{x}<br>%{fullData.name}: $%{y:,.0f}<extra></extra>")
        f2.add_hline(y=expected, line_dash="dash", line_color=MUTED,
                     annotation_text=f"Declared expected activity {money(expected)}/mo",
                     annotation_font_color=MUTED)
        st.plotly_chart(style(f2, 320).update_yaxes(title=None, tickprefix="$").update_xaxes(title=None),
                        use_container_width=True)
        others = queue[(queue.customer_id == a.customer_id) & (queue.alert_id != alert_id)]
        if len(others):
            st.markdown("**Other alerts for this customer**")
            st.dataframe(others[["alert_id", "rule", "priority", "alert_date", "status"]], hide_index=True,
                         use_container_width=True)

    # ---- 3. analyst conclusion
    st.markdown("#### 3 · What did the analyst conclude?")
    with st.form(f"review_{alert_id}"):
        c = st.columns([1, 2, 1])
        status = c[0].selectbox("Status", STATUSES, index=STATUSES.index(rv.status))
        disp = c[1].selectbox("Disposition", DISPOSITIONS,
                              index=DISPOSITIONS.index(rv.disposition) if rv.disposition in DISPOSITIONS else 0)
        analyst = c[2].text_input("Analyst", rv.analyst if isinstance(rv.analyst, str) else "")
        note = st.text_area("Investigation note", rv.note if isinstance(rv.note, str) else "", height=120,
                            placeholder="What you checked, what you found, and why you reached this conclusion.")
        if st.form_submit_button("Save review"):
            save_review(alert_id, status, disp, analyst, note)
            st.success("Review saved.")
            st.rerun()
    if isinstance(rv.updated_at, str):
        st.caption(f"Last updated {rv.updated_at} by {rv.analyst}")


def page_customer(customers, accounts, queue, cid):
    st.subheader("Customer transaction history")
    ids = customers.customer_id.tolist()
    alerted = sorted(queue.customer_id.dropna().unique())
    only = st.toggle("Only customers with alerts", value=True)
    pool = alerted if only else ids
    cid = st.selectbox("Customer", pool, index=pool.index(cid) if cid in pool else 0)
    cu = customers.set_index("customer_id").loc[cid]
    acc = accounts[accounts.customer_id == cid]
    c = st.columns(4)
    c[0].metric("Occupation", cu.occupation)
    c[1].metric("Declared expected activity", f"{money(cu.expected_monthly_activity_usd)}/mo")
    c[2].metric("Customer since", cu.account_opening_date)
    c[3].metric("Alerts", int((queue.customer_id == cid).sum()))
    ph = ",".join("?" * len(acc))
    tx = q(f"""SELECT * FROM transactions WHERE sender_account IN ({ph}) OR receiver_account IN ({ph})
               ORDER BY ts""", tuple(acc.account_id) * 2)
    tx["direction"] = tx.receiver_account.isin(acc.account_id).map({True: "In", False: "Out"})
    flagged = set(q(f"""SELECT DISTINCT e.transaction_id FROM alert_evidence e JOIN alerts a USING(alert_id)
                       WHERE a.customer_id = ?""", (cid,)).transaction_id)
    tx["in_alert_evidence"] = tx.transaction_id.isin(flagged)
    t2 = tx.assign(ts=pd.to_datetime(tx.ts), signed=lambda d: d.amount_usd.where(d.direction == "In", -d.amount_usd))
    t2["series"] = t2.apply(lambda r: f"{r.direction}{' · alert evidence' if r.in_alert_evidence else ''}", axis=1)
    fig = px.scatter(t2, x="ts", y="signed", color="series", title="Every transaction (money in above zero, out below)",
                     color_discrete_map={"In": "#a9cbf2", "Out": "#f4b9a0", "In · alert evidence": "#1c4f8f",
                                         "Out · alert evidence": "#b8461a"},
                     hover_data={"transaction_id": True, "transaction_type": True, "amount_usd": ":$,.0f",
                                 "signed": False, "series": False})
    fig.update_traces(marker=dict(size=9, line=dict(color="white", width=1)))
    st.plotly_chart(style(fig, 360).update_yaxes(title=None, tickprefix="$").update_xaxes(title=None),
                    use_container_width=True)
    st.dataframe(tx[["transaction_id", "ts", "direction", "transaction_type", "sender_account", "receiver_account",
                     "amount", "currency", "amount_usd", "in_alert_evidence"]],
                 hide_index=True, use_container_width=True, height=360)


def page_evaluation():
    st.subheader("Evaluation against planted synthetic scenarios")
    st.warning("These results measure the rules against scenarios planted in synthetic data. "
               "They do not establish effectiveness on real banking data.")
    if not (OUT / "evaluation_summary.csv").exists():
        st.info("Run `python src/04_evaluate.py` to produce the evaluation outputs.")
        return
    s = pd.read_csv(OUT / "evaluation_summary.csv")
    allr = s.iloc[0]
    c = st.columns(4)
    c[0].metric("Alerts to review", int(allr.alerts))
    c[1].metric("Precision", f"{allr.precision:.1%}", help="Alerts that match a planted scenario / all alerts")
    c[2].metric("Recall", f"{allr.recall:.1%}", help="Planted scenarios caught by at least one alert")
    c[3].metric("Scenarios caught", f"{int(allr.scenarios_detected)} / {int(allr.scenarios)}")
    st.markdown("**By rule**")
    st.dataframe(s, hide_index=True, use_container_width=True)
    st.markdown("**Rule coverage — share of each planted pattern each rule detects**")
    st.dataframe(pd.read_csv(OUT / "rule_coverage.csv", index_col=0), use_container_width=True)
    l, r = st.columns(2)
    l.markdown("**Recall by scenario type and variant**")
    l.dataframe(pd.read_csv(OUT / "recall_by_scenario_variant.csv"), hide_index=True, use_container_width=True)
    r.markdown("**Where the false positives came from**")
    r.dataframe(pd.read_csv(OUT / "false_positive_breakdown.csv"), hide_index=True, use_container_width=True)
    st.markdown("**Missed scenarios**")
    d = pd.read_csv(OUT / "scenario_detection.csv")
    st.dataframe(d[~d.detected][["scenario_id", "scenario_type", "variant", "subject_id", "description"]],
                 hide_index=True, use_container_width=True)
    st.markdown("**Threshold sensitivity (one parameter changed at a time)**")
    sens = pd.read_csv(OUT / "threshold_sensitivity.csv")
    st.dataframe(sens, hide_index=True, use_container_width=True, height=(len(sens) + 1) * 35 + 3)


# ------------------------------------------------------------------ layout
ensure_db()
daily, customers, accounts = load_static()
queue = load_queue()

PAGES = ["Overview", "Alert queue", "Alert detail", "Customer history", "Evaluation"]
qp = st.query_params
default_page = qp.get("page", "Overview")
with st.sidebar:
    st.markdown("## 🔎 AML Monitoring")
    st.caption("Portfolio prototype on synthetic data. Not a production compliance system.")
    page = st.radio("Page", PAGES, index=PAGES.index(default_page) if default_page in PAGES else 0)
    st.divider()
    st.caption(f"{len(queue)} alerts · {(queue.status == 'New').sum()} new · "
               f"{(queue.status == 'Investigating').sum()} investigating · {(queue.status == 'Closed').sum()} closed")

st.title("AML Investigation Dashboard")
if page == "Overview":
    page_overview(queue, daily)
elif page == "Alert queue":
    page_queue(queue)
elif page == "Alert detail":
    page_alert(queue, customers, accounts, qp.get("alert", "AL-0042"))
elif page == "Customer history":
    page_customer(customers, accounts, queue, qp.get("customer", "C00323"))
else:
    page_evaluation()
