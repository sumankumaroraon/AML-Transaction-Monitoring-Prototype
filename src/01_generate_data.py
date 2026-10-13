"""
01_generate_data.py
Generate a synthetic retail-banking dataset (customers, accounts, transactions)
with deliberately planted suspicious scenarios and benign look-alike activity.

Everything here is simulated. No real customer data is used.

Outputs
  data/raw/customers.csv
  data/raw/accounts.csv
  data/raw/transactions.csv
  data/labels/planted_scenarios.csv        one row per planted suspicious scenario
  data/labels/planted_transactions.csv     scenario_id -> transaction_id
  data/labels/benign_lookalikes.csv        benign activity designed to resemble a pattern
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
LABELS = ROOT / "data" / "labels"
CFG = json.loads((ROOT / "config" / "rules_config.json").read_text())
FX = CFG["fx_to_usd"]

START = datetime(2025, 1, 1)
END = datetime(2025, 12, 31, 23, 59, 59)
N_CUSTOMERS = 1000

rng = np.random.default_rng(SEED)

# occupation -> (share, expected monthly activity range USD, segment)
OCCUPATIONS = {
    "Student":              (0.10, (800, 2000), "retail"),
    "Retail Worker":        (0.12, (2000, 4000), "retail"),
    "Teacher":              (0.11, (3000, 6000), "retail"),
    "Nurse":                (0.10, (4000, 7000), "retail"),
    "Software Engineer":    (0.09, (8000, 15000), "retail"),
    "Contractor":           (0.09, (5000, 12000), "retail"),
    "Retiree":              (0.10, (2000, 5000), "retail"),
    "Physician":            (0.05, (12000, 25000), "retail"),
    "Property Owner":       (0.04, (8000, 20000), "retail"),
    "Small Business Owner": (0.12, (15000, 40000), "business"),
    "Restaurant Owner":     (0.08, (20000, 50000), "business"),
}

txns: list[dict] = []          # all transactions (id assigned at the end)
planted_rows: list[dict] = []  # scenario metadata
planted_links: list[tuple] = []  # (scenario_id, txn_index)
benign_rows: list[dict] = []


def rand_ts(day: datetime, business_hours: bool = True) -> datetime:
    """Random timestamp on a given day."""
    if business_hours:
        h = int(rng.integers(8, 20))
    else:
        h = int(rng.integers(0, 24))
    return day.replace(hour=h, minute=int(rng.integers(0, 60)), second=int(rng.integers(0, 60)))


def add_txn(ts, sender, receiver, amount, ttype, currency="USD") -> int:
    amount = round(float(amount), 2)
    txns.append({
        "timestamp": ts,
        "sender_account": sender,
        "receiver_account": receiver,
        "amount": amount,
        "currency": currency,
        "amount_usd": round(amount * FX[currency], 2),
        "transaction_type": ttype,
    })
    return len(txns) - 1


# ---------------------------------------------------------------- customers
occ_names = list(OCCUPATIONS)
occ_p = np.array([OCCUPATIONS[o][0] for o in occ_names])
occ_p = occ_p / occ_p.sum()

customers = []
for i in range(N_CUSTOMERS):
    occ = rng.choice(occ_names, p=occ_p)
    lo, hi = OCCUPATIONS[occ][1]
    expected = int(round(rng.uniform(lo, hi) / 500) * 500)
    # ~8% of customers onboarded during the monitoring year (new relationships)
    if rng.random() < 0.08:
        opened = START + timedelta(days=int(rng.integers(0, 240)))
    else:
        opened = datetime(2012, 1, 1) + timedelta(days=int(rng.integers(0, 365 * 13)))
    customers.append({
        "customer_id": f"C{i + 1:05d}",
        "occupation": occ,
        "customer_segment": OCCUPATIONS[occ][2],
        "expected_monthly_activity_usd": expected,
        "account_opening_date": opened.date(),
    })
cust = pd.DataFrame(customers)

# ---------------------------------------------------------------- accounts
accounts = []
acct_seq = 0


def new_account(cid, atype, opened):
    global acct_seq
    acct_seq += 1
    aid = f"A{acct_seq:06d}"
    accounts.append({"account_id": aid, "customer_id": cid, "account_type": atype, "open_date": opened})
    return aid


primary = {}   # customer -> main transacting account
savings = {}
for c in customers:
    opened = c["account_opening_date"]
    atype = "business_checking" if c["customer_segment"] == "business" else "checking"
    primary[c["customer_id"]] = new_account(c["customer_id"], atype, opened)
    if rng.random() < 0.45:
        sav_open = opened + timedelta(days=int(rng.integers(0, 400)))
        savings[c["customer_id"]] = new_account(c["customer_id"], "savings", min(sav_open, END.date()))
acc = pd.DataFrame(accounts)

cust_by_id = {c["customer_id"]: c for c in customers}
all_primary = list(primary.values())
acct_owner = dict(zip(acc.account_id, acc.customer_id))

# small social network for P2P (keeps normal P2P from looking like random fan-in)
friends = {cid: list(rng.choice(all_primary, size=3, replace=False)) for cid in primary}
SUPPLIERS = [f"EXT-SUP-{i:03d}" for i in range(1, 61)]
supplier_of = {cid: list(rng.choice(SUPPLIERS, size=2, replace=False)) for cid in primary}
paid_semimonthly = {cid: bool(rng.random() < 0.55) for cid in primary}
employer_of = {cid: f"EXT-EMP-{int(rng.integers(1, 151)):03d}" for cid in primary}

# landlords (Property Owners) collect rent from a fixed set of tenants -> benign many-to-one
property_owners = [c["customer_id"] for c in customers if c["occupation"] == "Property Owner"]
landlord_tenants = {}
retail_ids = [c["customer_id"] for c in customers if c["customer_segment"] == "retail"
              and c["occupation"] not in ("Property Owner",)]
for lid in property_owners[:8]:
    landlord_tenants[lid] = list(rng.choice(retail_ids, size=int(rng.integers(6, 10)), replace=False))
tenant_landlord = {t: l for l, ts in landlord_tenants.items() for t in ts}


def month_starts():
    for m in range(1, 13):
        yield datetime(2025, m, 1)


def days_in_month(d: datetime) -> int:
    nxt = datetime(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return (nxt - d).days


def day_in(d: datetime, lo: int = 1, hi: int | None = None) -> datetime:
    hi = hi or days_in_month(d)
    return d + timedelta(days=int(rng.integers(lo, hi + 1)) - 1)


# ---------------------------------------------------------------- normal activity
for c in customers:
    cid = c["customer_id"]
    a = primary[cid]
    E = c["expected_monthly_activity_usd"]
    # actual typical activity differs a little from the declared profile
    base = E * rng.lognormal(0, 0.20)
    opened = datetime.combine(c["account_opening_date"], datetime.min.time())
    biz = c["customer_segment"] == "business"
    for ms in month_starts():
        if ms + timedelta(days=days_in_month(ms)) <= opened:
            continue
        month_total = base * rng.lognormal(0, 0.25)
        inflow, outflow = month_total * 0.5, month_total * 0.5

        def valid(ts):
            return ts >= opened

        if not biz:
            # income
            if c["occupation"] in ("Retiree",):
                ts = rand_ts(day_in(ms, 1, 3))
                if valid(ts):
                    add_txn(ts, "EXT-GOV-SSA", a, inflow, "ACH_CREDIT")
            elif c["occupation"] == "Property Owner":
                if cid not in landlord_tenants:
                    ts = rand_ts(day_in(ms, 1, 6))
                    if valid(ts):
                        add_txn(ts, f"EXT-ORG-{int(rng.integers(1, 400)):04d}", a, inflow, "WIRE_IN")
            elif c["occupation"] == "Contractor":
                for _ in range(int(rng.integers(1, 3))):
                    ts = rand_ts(day_in(ms))
                    if valid(ts):
                        add_txn(ts, f"EXT-ORG-{int(rng.integers(1, 400)):04d}", a, inflow / 1.5, "ACH_CREDIT")
            else:
                pay_days = (1, 15) if paid_semimonthly[cid] else (28,)
                for d in pay_days:
                    ts = rand_ts(ms + timedelta(days=d - 1 + int(rng.integers(0, 2))))
                    if valid(ts):
                        add_txn(ts, employer_of[cid], a, inflow / len(pay_days), "PAYROLL_DEPOSIT")
            # rent paid to a landlord customer (internal P2P)
            spend = outflow
            if cid in tenant_landlord:
                rent = round(float(rng.uniform(1100, 2400)) / 25) * 25
                rent = min(rent, outflow * 0.6)
                ts = rand_ts(day_in(ms, 1, 4))
                if valid(ts):
                    add_txn(ts, a, primary[tenant_landlord[cid]], rent, "P2P_TRANSFER")
                spend -= rent
            # bill payment
            ts = rand_ts(day_in(ms))
            if valid(ts):
                add_txn(ts, a, f"EXT-BIL-{int(rng.integers(1, 80)):03d}", spend * rng.uniform(0.25, 0.4), "BILL_PAYMENT")
            # card purchases
            for _ in range(rng.poisson(0.65)):
                ts = rand_ts(day_in(ms), business_hours=False)
                if valid(ts):
                    add_txn(ts, a, f"EXT-MER-{int(rng.integers(1, 900)):04d}", spend * rng.uniform(0.05, 0.2), "CARD_PURCHASE")
            # P2P to friends
            for _ in range(rng.poisson(0.35)):
                ts = rand_ts(day_in(ms), business_hours=False)
                if valid(ts):
                    add_txn(ts, a, friends[cid][int(rng.integers(0, 3))], rng.uniform(20, 400), "P2P_TRANSFER")
            # cash withdrawal
            if rng.random() < 0.22:
                ts = rand_ts(day_in(ms))
                if valid(ts):
                    add_txn(ts, a, "CASH", round(float(rng.uniform(40, 600)) / 20) * 20, "CASH_WITHDRAWAL")
            # occasional international wire
            if rng.random() < 0.025:
                cur = rng.choice(["EUR", "GBP", "CAD"])
                ts = rand_ts(day_in(ms))
                if valid(ts):
                    add_txn(ts, a, f"EXT-BEN-{int(rng.integers(1, 5000)):04d}", rng.uniform(300, 3000), "WIRE_OUT", cur)
        else:
            # business: customer receipts (wires/ACH + cash), supplier wires, payroll ACH out
            n_rec = int(rng.integers(2, 5))
            cash_share = 0.45 if c["occupation"] == "Restaurant Owner" else 0.15
            for _ in range(n_rec):
                ts = rand_ts(day_in(ms))
                if not valid(ts):
                    continue
                amt = inflow / n_rec * rng.uniform(0.6, 1.4)
                if rng.random() < cash_share:
                    add_txn(ts, "CASH", a, amt if amt <= 14500 else 14500 - (amt % 3000), "CASH_DEPOSIT")
                else:
                    add_txn(ts, f"EXT-ORG-{int(rng.integers(1, 400)):04d}", a, amt, "ACH_CREDIT")
            for s in supplier_of[cid]:
                ts = rand_ts(day_in(ms, 5, 25))
                if valid(ts):
                    add_txn(ts, a, s, outflow * rng.uniform(0.2, 0.3), "WIRE_OUT")
            ts = rand_ts(day_in(ms, 25, 28))
            if valid(ts):
                add_txn(ts, a, "EXT-PAYROLL-PROC", outflow * 0.35, "ACH_DEBIT")
            for _ in range(rng.poisson(0.8)):
                ts = rand_ts(day_in(ms), business_hours=False)
                if valid(ts):
                    add_txn(ts, a, f"EXT-MER-{int(rng.integers(1, 900)):04d}", rng.uniform(50, 900), "CARD_PURCHASE")
        # savings sweep
        if cid in savings and rng.random() < 0.28:
            sav_open = next(x["open_date"] for x in accounts if x["account_id"] == savings[cid])
            ts = rand_ts(day_in(ms, 16, 28))
            if ts.date() >= sav_open and valid(ts):
                add_txn(ts, a, savings[cid], rng.uniform(100, 0.1 * month_total + 100), "INTERNAL_TRANSFER")

n_normal = len(txns)

# ---------------------------------------------------------------- benign look-alikes
# (a) one-off large legitimate purchase/sale -> may look like an activity spike
big_life = rng.choice([c["customer_id"] for c in customers if c["customer_segment"] == "retail"
                       and c["account_opening_date"] < datetime(2024, 6, 1).date()], size=6, replace=False)
for cid in big_life:
    a = primary[cid]
    E = cust_by_id[cid]["expected_monthly_activity_usd"]
    ms = datetime(2025, int(rng.integers(5, 12)), 1)
    amt = max(E * rng.uniform(6, 10), 22000)
    ts1 = rand_ts(day_in(ms, 3, 10))
    ts2 = ts1 + timedelta(days=int(rng.integers(2, 6)))
    idx = [add_txn(ts1, f"EXT-ORG-{int(rng.integers(400, 450)):04d}", a, amt, "WIRE_IN"),
           add_txn(ts2, a, f"EXT-BIL-{int(rng.integers(80, 90)):03d}", amt * 0.97, "WIRE_OUT")]
    benign_rows.append({"lookalike_id": f"B{len(benign_rows) + 1:02d}", "resembles": "ACTIVITY_SPIKE",
                        "subject_id": a, "description": "Home sale proceeds / car purchase (one-off life event)",
                        "window_start": ts1, "window_end": ts2, "n_txns": len(idx)})

# (b) community fundraiser: many friends send to one organiser in a few days
organisers = rng.choice(retail_ids, size=2, replace=False)
for cid in organisers:
    a = primary[cid]
    ms = datetime(2025, int(rng.integers(3, 11)), 1)
    d0 = rand_ts(day_in(ms, 2, 20))
    donors = rng.choice([p for p in all_primary if p != a], size=int(rng.integers(8, 13)), replace=False)
    for k, dnr in enumerate(donors):
        add_txn(d0 + timedelta(hours=float(rng.uniform(0, 120))), dnr, a, rng.uniform(800, 3500), "P2P_TRANSFER")
    benign_rows.append({"lookalike_id": f"B{len(benign_rows) + 1:02d}", "resembles": "MANY_TO_ONE",
                        "subject_id": a, "description": "Community fundraiser / medical-bill collection among friends",
                        "window_start": d0, "window_end": d0 + timedelta(days=5), "n_txns": len(donors)})

# (c) landlord rent collection (generated above) – documented here
for lid, tenants in landlord_tenants.items():
    benign_rows.append({"lookalike_id": f"B{len(benign_rows) + 1:02d}", "resembles": "MANY_TO_ONE",
                        "subject_id": primary[lid], "description": f"Landlord collecting monthly rent from {len(tenants)} tenants",
                        "window_start": START, "window_end": END, "n_txns": None})

# (d) cash-heavy restaurant with a few near-threshold deposits
rest = rng.choice([c["customer_id"] for c in customers if c["occupation"] == "Restaurant Owner"], size=3, replace=False)
for cid in rest:
    a = primary[cid]
    ms = datetime(2025, int(rng.integers(2, 12)), 1)
    d0 = rand_ts(day_in(ms, 1, 15))
    for k in range(3):
        add_txn(d0 + timedelta(days=int(rng.integers(0, 9)), hours=float(rng.uniform(0, 4))), "CASH", a,
                rng.uniform(9050, 9900), "CASH_DEPOSIT")
    benign_rows.append({"lookalike_id": f"B{len(benign_rows) + 1:02d}", "resembles": "STRUCTURING",
                        "subject_id": a, "description": "Cash-intensive restaurant: weekend takings deposited near the threshold",
                        "window_start": d0, "window_end": d0 + timedelta(days=10), "n_txns": 3})

# ---------------------------------------------------------------- planted suspicious scenarios
used_subjects: set[str] = set()


def pick_customers(n, pred):
    pool = [c["customer_id"] for c in customers if pred(c) and primary[c["customer_id"]] not in used_subjects]
    chosen = list(rng.choice(pool, size=n, replace=False))
    used_subjects.update(primary[x] for x in chosen)
    return chosen


def register(stype, variant, subject, idxs, note):
    sid = f"S{len(planted_rows) + 1:03d}"
    times = [txns[i]["timestamp"] for i in idxs]
    planted_rows.append({
        "scenario_id": sid, "scenario_type": stype, "variant": variant,
        "subject_id": subject, "customer_id": acct_owner.get(subject),
        "window_start": min(times), "window_end": max(times),
        "n_transactions": len(idxs),
        "total_usd": round(sum(txns[i]["amount_usd"] for i in idxs), 2),
        "description": note,
    })
    planted_links.extend((sid, i) for i in idxs)


def scenario_month():
    return datetime(2025, int(rng.integers(4, 13)), 1)


# 1. Rapid pass-through (12: 10 standard, 2 subtle)
mules = pick_customers(12, lambda c: c["customer_segment"] == "retail" and c["occupation"] in
                       ("Student", "Retail Worker", "Teacher", "Nurse", "Retiree"))
for k, cid in enumerate(mules):
    a = primary[cid]
    subtle = k >= 10
    t = rand_ts(day_in(scenario_month(), 1, 18))
    idx = []
    n_in = int(rng.integers(5, 10))
    span_h = rng.uniform(120, 160) if subtle else rng.uniform(24, 60)  # subtle: spread over ~5-6 days
    offsets = np.sort(rng.uniform(0, span_h, size=n_in))
    for off in offsets:
        if rng.random() < 0.6:
            snd = rng.choice([p for p in all_primary if p != a])
            idx.append(add_txn(t + timedelta(hours=float(off)), snd, a, rng.uniform(1800, 4800), "P2P_TRANSFER"))
        else:
            cur = rng.choice(["USD", "USD", "EUR", "GBP"])
            idx.append(add_txn(t + timedelta(hours=float(off)), f"EXT-ORG-{int(rng.integers(600, 700)):04d}", a,
                               rng.uniform(1800, 4800) / FX[cur], "WIRE_IN", cur))
    total_in = sum(txns[i]["amount_usd"] for i in idx)
    ratio = rng.uniform(0.80, 0.86) if subtle else rng.uniform(0.85, 0.95)
    out_ts = t + timedelta(hours=float(span_h + rng.uniform(4, 30)))
    idx.append(add_txn(out_ts, a, f"EXT-BEN-{9000 + k:04d}", total_in * ratio, "WIRE_OUT"))
    register("RAPID_PASS_THROUGH", "subtle" if subtle else "standard", a, idx,
             f"{n_in} inbound transfers over {span_h:.0f}h, {ratio:.0%} forwarded by wire")

# 2. Sudden activity spike (12: 10 standard, 2 subtle)
spikers = pick_customers(12, lambda c: c["expected_monthly_activity_usd"] <= 7000
                         and c["account_opening_date"] < datetime(2024, 10, 1).date()
                         and c["customer_segment"] == "retail" and c["customer_id"] not in tenant_landlord)
for k, cid in enumerate(spikers):
    a = primary[cid]
    E = cust_by_id[cid]["expected_monthly_activity_usd"]
    subtle = k >= 10
    mult = rng.uniform(1.6, 2.0) if subtle else rng.uniform(6, 12)
    M = max(E * mult, 9000 if subtle else 22000)
    ms = scenario_month()
    t = rand_ts(day_in(ms, 1, 8))
    idx = []
    n_in = int(rng.integers(1, 3))
    for j in range(n_in):
        idx.append(add_txn(t + timedelta(days=j * 3), f"EXT-ORG-{int(rng.integers(700, 800)):04d}", a, M / n_in, "WIRE_IN"))
    n_out = int(rng.integers(3, 6))
    for j in range(n_out):
        when = t + timedelta(days=4 + j * float(rng.uniform(2, 4)), hours=float(rng.uniform(1, 8)))
        if rng.random() < 0.5:
            idx.append(add_txn(when, a, "CASH", round(M * 0.9 / n_out, -1), "CASH_WITHDRAWAL"))
        else:
            idx.append(add_txn(when, a, f"EXT-BEN-{9100 + k * 10 + j:04d}", M * 0.9 / n_out, "WIRE_OUT"))
    register("ACTIVITY_SPIKE", "subtle" if subtle else "standard", a, idx,
             f"Inflow of ~{mult:.1f}x declared monthly activity moved out within weeks")

# 3. Many-to-one beneficiary (8: 6 standard, 2 subtle)
for k in range(8):
    subtle = k >= 6
    ben = f"EXT-BEN-{9500 + k:04d}"
    t = rand_ts(day_in(scenario_month(), 1, 20))
    n_snd = 5 if subtle else int(rng.integers(7, 13))
    senders = rng.choice(all_primary, size=n_snd, replace=False)
    idx = [add_txn(t + timedelta(hours=float(rng.uniform(0, 140))), s, ben, rng.uniform(1500, 4500), "WIRE_OUT")
           for s in senders]
    register("MANY_TO_ONE", "subtle" if subtle else "standard", ben, idx,
             f"{n_snd} unrelated accounts wire funds to one new beneficiary within ~6 days")

# 4. Structuring below the monitoring threshold (12: 10 standard, 2 subtle)
thr = CFG["monitoring_threshold_usd"]
structurers = pick_customers(12, lambda c: c["occupation"] in ("Contractor", "Small Business Owner", "Retail Worker",
                                                               "Software Engineer", "Nurse"))
for k, cid in enumerate(structurers):
    a = primary[cid]
    subtle = k >= 10
    t = rand_ts(day_in(scenario_month(), 1, 18))
    n = int(rng.integers(3, 7))
    days = np.sort(rng.choice(np.arange(0, 9), size=n, replace=False)) if n <= 9 else np.arange(n)
    lo, hi = (0.80, 0.88) if subtle else (0.905, 0.995)  # subtle: deposits kept lower, outside the 90% band
    idx = [add_txn(t + timedelta(days=int(d), hours=float(rng.uniform(0, 6))), "CASH", a,
                   round(rng.uniform(lo, hi) * thr, -1), "CASH_DEPOSIT") for d in days]
    register("STRUCTURING", "subtle" if subtle else "standard", a, idx,
             f"{n} cash deposits between {lo:.0%} and {hi:.0%} of the ${thr:,} threshold within 9 days")

# ---------------------------------------------------------------- finalize
tx = pd.DataFrame(txns)
tx["orig_index"] = range(len(tx))
tx = tx.sort_values("timestamp").reset_index(drop=True)
tx["transaction_id"] = [f"T{i + 1:07d}" for i in range(len(tx))]
idx_to_id = dict(zip(tx.orig_index, tx.transaction_id))
tx["timestamp"] = tx["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
tx = tx[["transaction_id", "timestamp", "sender_account", "receiver_account", "amount", "currency",
         "amount_usd", "transaction_type"]]

RAW.mkdir(parents=True, exist_ok=True)
LABELS.mkdir(parents=True, exist_ok=True)
cust.to_csv(RAW / "customers.csv", index=False)
acc.to_csv(RAW / "accounts.csv", index=False)
tx.to_csv(RAW / "transactions.csv", index=False)

ps = pd.DataFrame(planted_rows)
for col in ("window_start", "window_end"):
    ps[col] = pd.to_datetime(ps[col]).dt.strftime("%Y-%m-%d %H:%M:%S")
ps.to_csv(LABELS / "planted_scenarios.csv", index=False)
pd.DataFrame([(s, idx_to_id[i]) for s, i in planted_links], columns=["scenario_id", "transaction_id"]) \
    .to_csv(LABELS / "planted_transactions.csv", index=False)
bl = pd.DataFrame(benign_rows)
for col in ("window_start", "window_end"):
    bl[col] = pd.to_datetime(bl[col]).dt.strftime("%Y-%m-%d %H:%M:%S")
bl.to_csv(LABELS / "benign_lookalikes.csv", index=False)

print(f"customers={len(cust):,} accounts={len(acc):,} transactions={len(tx):,} "
      f"(normal={n_normal:,}, planted={len(planted_links):,}) scenarios={len(ps)} lookalikes={len(bl)}")
print(tx.transaction_type.value_counts().to_string())
