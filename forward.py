"""Forward paper test. Rules are frozen in FORWARD_PROTOCOL.md. Long-only, paper only, no money.
Reads data/YYYY-MM-DD/HHMM.json written by collect.py, appends new signals and evaluates finished days."""
import csv, glob, json, os, statistics, sys
from datetime import datetime, timezone

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
UNIVERSE = ["ADNOCGAS", "ADNOCDRILL", "ADIB", "ALPHADHABI", "BOROUGE", "ALDAR", "ADNOCLS", "ADNOCDIST", "FERTIGLB", "PRESIGHT"]
SPREAD = {"ADIB": .0009, "ALDAR": .0012, "ADNOCDRILL": .0018, "ADNOCDIST": .0026, "ADNOCLS": .0027, "PRESIGHT": .0028,
          "ADNOCGAS": .0031, "ALPHADHABI": .0042, "FERTIGLB": .0042, "BOROUGE": .0043}
COMM_SIDE = 0.00315 / 2
TARGET, STOP = 0.010, 0.008
ACT_MIN, MAX_EXT = 1.5, 0.04
WARM_DAYS = 3
ENTRY_FROM, ENTRY_TO = 6 * 60 + 30, 9 * 60 + 30      # 06:30-09:30 UTC = 10:30-13:30 Dubai
CLOSE_FROM = 10 * 60 + 45                              # a snapshot at/after 10:45 UTC (14:45 Dubai) counts as the close
RULES = ("R1", "R2")
FIELDS = ["id", "day", "rule", "sym", "entry_hhmm", "entry", "target", "stop", "status", "exit_hhmm", "exit", "exit_reason", "net_ret", "ew_ret", "excess"]

def mins(hhmm): return int(hhmm[:2]) * 60 + int(hhmm[2:])

def load_days():
    days = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "????-??-??", "????.json"))):
        day, hhmm = os.path.basename(os.path.dirname(p)), os.path.basename(p)[:4]
        try:
            j = json.load(open(p, encoding="utf-8"))
            a = j["sources"]["adx"]
            if not a.get("ok"): continue
            rows = {r["companySymbol"]: r for r in a["parts"]["stocks"]["response"]["results"] if r.get("companySymbol") in UNIVERSE}
            sess = (a["parts"].get("status", {}).get("response") or {}).get("sessionName", "")
        except Exception:
            continue
        days.setdefault(day, []).append((hhmm, rows, sess))
    for d in days: days[d].sort(key=lambda x: x[0])
    return days

def val_at(snaps, sym, hhmm):
    best = None
    for h, rows, _ in snaps:
        if mins(h) <= mins(hhmm) and sym in rows and rows[sym].get("value") is not None: best = rows[sym]["value"]
    return best

def prior_activity(days, day, sym, hhmm):
    prev = [d for d in sorted(days) if d < day][-5:]
    vals = [v for v in (val_at(days[d], sym, hhmm) for d in prev) if v and v > 0]
    return statistics.median(vals) if len(vals) >= WARM_DAYS else None

def prev_high(days, day, sym):
    prev = [d for d in sorted(days) if d < day]
    if not prev: return None
    hs = [rows[sym]["high"] for _, rows, _ in days[prev[-1]] if sym in rows and rows[sym].get("high")]
    return max(hs) if hs else None

def find_signals(days, day, logged):
    out = []
    for hhmm, rows, sess in days[day]:
        if not (ENTRY_FROM <= mins(hhmm) <= ENTRY_TO) or "Trading" not in str(sess): continue
        for sym, r in rows.items():
            try:
                last, op, hi, lo, pc = r["last"], r["open"], r["high"], r["low"], r["previousClose"]
                if not all(x and x > 0 for x in (last, op, hi, lo, pc)): continue
                base = prior_activity(days, day, sym, hhmm)
                if base is None: continue
                act = (r.get("value") or 0) / base
                chg = last / pc - 1
                ph = prev_high(days, day, sym)
                hit = {"R1": ph is not None and last > ph and act >= ACT_MIN and last >= op and chg <= MAX_EXT,
                       "R2": chg >= 0.015 and hi > lo and last >= lo + 0.8 * (hi - lo) and act >= ACT_MIN and chg <= MAX_EXT}
            except Exception:
                continue
            for rule in RULES:
                sid = "%s_%s_%s" % (day, sym, rule)
                if hit[rule] and sid not in logged:
                    logged.add(sid)
                    e = last
                    out.append(dict(id=sid, day=day, rule=rule, sym=sym, entry_hhmm=hhmm, entry=e, target=round(e * (1 + TARGET), 4),
                                    stop=round(e * (1 - STOP), 4), status="open", exit_hhmm="", exit="", exit_reason="", net_ret="", ew_ret="", excess=""))
    return out

def net(sym, entry, exit_):
    s = SPREAD.get(sym, .003)
    return exit_ * (1 - s / 2) * (1 - COMM_SIDE) / (entry * (1 + s / 2) * (1 + COMM_SIDE)) - 1

def evaluate(days, sig):
    day = sig["day"]; snaps = days.get(day, [])
    if not snaps: return sig
    last_h, last_rows, _ = snaps[-1]
    if mins(last_h) < CLOSE_FROM: return sig
    sym = sig["sym"]; e = float(sig["entry"]); tgt = float(sig["target"]); stp = float(sig["stop"])
    ent = next(((h, rows) for h, rows, _ in snaps if h == sig["entry_hhmm"]), None)
    if ent is None or sym not in ent[1]: return sig
    hi0, lo0 = ent[1][sym]["high"], ent[1][sym]["low"]
    exit_p, reason, hx = None, "close", last_h
    for h, rows, _ in snaps:
        if mins(h) <= mins(sig["entry_hhmm"]) or sym not in rows: continue
        hi, lo = rows[sym]["high"], rows[sym]["low"]
        hit_t = hi > hi0 and hi >= tgt
        hit_s = lo < lo0 and lo <= stp
        if hit_s: exit_p, reason, hx = stp, "stop", h; break
        if hit_t: exit_p, reason, hx = tgt, "target", h; break
    if exit_p is None:
        if sym not in last_rows: return sig
        exit_p = last_rows[sym]["last"]
    ew = []
    for u in UNIVERSE:
        if u in ent[1] and u in last_rows and ent[1][u].get("last") and last_rows[u].get("last"):
            ew.append(net(u, ent[1][u]["last"], last_rows[u]["last"]))
    r = net(sym, e, exit_p)
    sig.update(status="closed", exit_hhmm=hx, exit=round(exit_p, 4), exit_reason=reason, net_ret=round(r, 5),
               ew_ret=round(statistics.mean(ew), 5) if ew else "", excess=round(r - statistics.mean(ew), 5) if ew else "")
    return sig

def summarize(sigs):
    out = {"updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rules": {}}
    for rule in RULES + ("ALL",):
        c = [s for s in sigs if s["status"] == "closed" and (rule == "ALL" or s["rule"] == rule)]
        o = [s for s in sigs if s["status"] == "open" and (rule == "ALL" or s["rule"] == rule)]
        rs = [float(s["net_ret"]) for s in c]
        gp = sum(x for x in rs if x > 0); gl = -sum(x for x in rs if x < 0)
        ex = [float(s["excess"]) for s in c if s["excess"] != ""]
        out["rules"][rule] = dict(closed=len(c), open=len(o), mean_net=round(statistics.mean(rs), 5) if rs else None,
            win=round(sum(x > 0 for x in rs) / len(rs), 3) if rs else None, profit_factor=round(gp / gl, 3) if gl > 0 else None,
            mean_excess_vs_ew=round(statistics.mean(ex), 5) if ex else None, judgeable=len(c) >= 30)
    return out

def main():
    days = load_days()
    os.makedirs(os.path.join(ROOT, "forward"), exist_ok=True)
    logp = os.path.join(ROOT, "forward", "signals.csv")
    sigs = []
    if os.path.exists(logp):
        sigs = list(csv.DictReader(open(logp, encoding="utf-8")))
    logged = {s["id"] for s in sigs}
    for day in sorted(days):
        sigs += find_signals(days, day, logged)
    sigs = [evaluate(days, s) if s["status"] == "open" else s for s in sigs]
    with open(logp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(sigs)
    json.dump(summarize(sigs), open(os.path.join(ROOT, "forward", "summary.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(summarize(sigs)["rules"]["ALL"]), "signals:", len(sigs), "days:", len(days))

if __name__ == "__main__":
    main()
