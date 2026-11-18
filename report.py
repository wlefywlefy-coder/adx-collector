"""Daily report builder: reads data/latest.json + forward/summary.json, writes report/latest.json and report/latest.png.
Report only. Does not touch forward.py or its frozen rules."""
import json, os, sys
from datetime import datetime, timezone

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
U = json.load(open(os.path.join(ROOT, "universe.json"), encoding="utf-8"))
ALIAS = U.get("ALIAS", {})

def num(x):
    try: return float(x)
    except Exception: return 0.0


# ADIB Securities schedule (adibsecurities.ae pricing page): ADX total max 0.150%, DFM 0.275% per executed order,
# plus AED 10 fixed per order per side, plus 5% VAT on fees (assumed to apply to all). Reference position size assumed.
POS_AED = 50000
SIDE_PCT = {"ADX": 0.00150, "DFM": 0.00275}
SPREAD_DEF = .003
def side_cost(m): return SIDE_PCT[m] * 1.05 + 10 * 1.05 / POS_AED
def rt_cost(m): return 2 * side_cost(m) + SPREAD_DEF
def net_ret(m, entry, exit_):
    c = side_cost(m)
    return exit_ * (1 - SPREAD_DEF / 2) * (1 - c) / (entry * (1 + SPREAD_DEF / 2) * (1 + c)) - 1

def day_series(day, m, s):
    import glob
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", day, "????.json"))):
        try:
            j = json.load(open(p, encoding="utf-8"))
            if m == "ADX":
                r = {x["companySymbol"]: x for x in j["sources"]["adx"]["parts"]["stocks"]["response"]["results"]}.get(ALIAS.get(s, s))
                v = num(r.get("last")) if r else 0
            else:
                r = {x["id"]: x for x in j["sources"]["dfm"]["parts"]["stocks"]}.get(s)
                v = (num(r.get("lastradeprice")) or num(r.get("closingprice"))) if r else 0
            if v > 0: out.append((os.path.basename(p)[:4], v))
        except Exception: continue
    return out

def prev_close(day, m, s):
    import glob
    ps = sorted(glob.glob(os.path.join(ROOT, "data", day, "????.json")))
    if not ps: return 0
    try:
        j = json.load(open(ps[0], encoding="utf-8"))
        if m == "ADX":
            r = {x["companySymbol"]: x for x in j["sources"]["adx"]["parts"]["stocks"]["response"]["results"]}.get(ALIAS.get(s, s)); return num(r.get("previousClose")) if r else 0
        r = {x["id"]: x for x in j["sources"]["dfm"]["parts"]["stocks"]}.get(s); return num(r.get("previousclosingprice")) if r else 0
    except Exception: return 0

def evaluate_watch(log, today):
    import glob
    days = sorted(os.path.basename(d) for d in glob.glob(os.path.join(ROOT, "data", "????-??-??")))
    for d, items in log.items():
        nxt = [x for x in days if x > d]
        if not nxt or nxt[0] >= today and not any(os.path.exists(p) for p in [os.path.join(ROOT, "data", nxt[0], "1045.json")]) and nxt[0] == today:
            pass
        for it in items:
            if it.get("result") or not nxt: continue
            nd = nxt[0]
            ser = day_series(nd, it["m"], it["s"])
            if not ser or ser[-1][0] < "1045": continue   # next day not finished yet
            pcl = prev_close(nd, it["m"], it["s"])
            ent = max(it["entry"], pcl); trig = None; res = None   # entry level cannot be below the real previous close (snapshot precedes closing auction)
            for hhmm, v in ser:
                if trig is None:
                    if v > ent: trig = (hhmm, v)
                    continue
                if v >= trig[1] * 1.01: res = ("target", hhmm, v); break
                if v <= trig[1] * 0.992: res = ("stop", hhmm, v); break
            hi = max(v for _, v in ser)
            if trig is None:
                it["result"] = dict(day=nd, status="لم يُفعَّل", net=None, why="لم يكسر السهم مستوى الدخول %s (أعلى إغلاق لحظي %s)" % (ent, round(hi, 3)))
            else:
                if res is None: res = ("close", ser[-1][0], ser[-1][1])
                n = net_ret(it["m"], trig[1], res[2]) * 100
                label = {"target": "أصاب الهدف", "stop": "ضرب الوقف", "close": "أُغلق بنهاية اليوم"}[res[0]]
                it["result"] = dict(day=nd, status=label, net=round(n, 2), entry_px=trig[1], exit_px=res[2],
                                    why="كسر المستوى عند %s بسعر %s ثم %s بسعر %s (الصافي بعد عمولة مصرف أبوظبي الإسلامي ورسوم السوق وVAT والفارق السعري)" % (trig[0], trig[1], label, res[2]))
    return log

def reason(r):
    p = (r["last"] - r["lo"]) / (r["hi"] - r["lo"]) * 100 if r["hi"] > r["lo"] else 0
    return "ارتفع %.1f%% وأغلق عند %d%% من مدى اليوم مع سيولة %.1f م" % (r["ch"], p, r["v"] / 1e6)


def value_series(day, m, s):
    import glob
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", day, "????.json"))):
        try:
            j = json.load(open(p, encoding="utf-8"))
            if m == "ADX":
                r = {x["companySymbol"]: x for x in j["sources"]["adx"]["parts"]["stocks"]["response"]["results"]}.get(ALIAS.get(s, s)); v = num(r.get("value")) if r else 0
            else:
                r = {x["id"]: x for x in j["sources"]["dfm"]["parts"]["stocks"]}.get(s); v = num(r.get("totalvalue")) if r else 0
            out.append(v)
        except Exception: continue
    return out

def spiky(day, r):
    """Devil filter: one snapshot interval carrying >40% of the day's total traded value = isolated spike, not steady build-up."""
    try:
        v = value_series(day, r["m"], r["s"])
        if len(v) < 6 or v[-1] <= 0: return False
        return max(b - a for a, b in zip(v, v[1:])) > 0.4 * v[-1]
    except Exception:
        return False

def build():
    j = json.load(open(os.path.join(ROOT, "data", "latest.json"), encoding="utf-8"))
    ts = j["ts_utc"]
    rows, missing = [], []
    adx = {r["companySymbol"]: r for r in j["sources"]["adx"]["parts"]["stocks"]["response"]["results"]}
    for s in U["ADX"]:
        r = adx.get(ALIAS.get(s, s))
        if not r: missing.append("ADX:" + s); continue
        last, prev = num(r.get("last")), num(r.get("previousClose"))
        if last > 0 and prev > 0: rows.append(dict(m="ADX", s=s, last=last, ch=(last / prev - 1) * 100, v=num(r.get("value")), hi=num(r.get("high")), lo=num(r.get("low"))))
    dfm = {r["id"]: r for r in j["sources"]["dfm"]["parts"]["stocks"]}
    for s in U["DFM"]:
        r = dfm.get(s)
        if not r: missing.append("DFM:" + s); continue
        last = num(r.get("lastradeprice")) or num(r.get("closingprice")); prev = num(r.get("previousclosingprice"))
        if last > 0 and prev > 0: rows.append(dict(m="DFM", s=s, last=last, ch=(last / prev - 1) * 100, v=num(r.get("totalvalue")), hi=num(r.get("highestprice")), lo=num(r.get("lowestprice"))))
    universe_n = len(U["ADX"]) + len(U["DFM"])
    traded = [r for r in rows if r["v"] > 0]
    gain = sorted(traded, key=lambda r: -r["ch"])[:5]
    lose = sorted(traded, key=lambda r: r["ch"])[:5]
    val = sorted(traded, key=lambda r: -r["v"])[:5]
    def pos(r): return (r["last"] - r["lo"]) / (r["hi"] - r["lo"]) if r["hi"] > r["lo"] > 0 else 0
    watch = sorted([r for r in traded if 0.5 <= r["ch"] <= 4 and r["v"] >= 1e6 and pos(r) >= 0.7], key=lambda r: -r["v"])
    watch = [r for r in watch if not spiky(ts[:10], r)][:5]
    for r in watch: lv = max(r["hi"], r["last"]); r["entry"] = lv; r["tgt"] = round(lv * 1.01, 3); r["stp"] = round(lv * 0.992, 3)
    core = [r for r in rows if r["m"] == "ADX" and r["s"] in U["CORE10"]]
    core.sort(key=lambda r: -r["ch"])
    try: fs = json.load(open(os.path.join(ROOT, "forward", "summary.json"), encoding="utf-8"))["rules"]
    except Exception: fs = {}
    now = datetime.now(timezone.utc)
    fresh = ts[:10] == now.strftime("%Y-%m-%d") and ts[11:16] >= "10:30"
    logp = os.path.join(ROOT, "report", "watch_log.json")
    try: log = json.load(open(logp, encoding="utf-8"))
    except Exception: log = {}
    day = ts[:10]
    log = evaluate_watch(log, day)
    if fresh:
        log[day] = [dict(m=r["m"], s=r["s"], entry=r["entry"], tgt=r["tgt"], stp=r["stp"], reason=reason(r)) for r in watch]
    os.makedirs(os.path.dirname(logp), exist_ok=True)
    json.dump(log, open(logp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    prev = [d for d in sorted(log) if d < day and any(i.get("result") for i in log[d])]
    watch_eval = [dict(s=i["s"], m=i["m"], nom_day=d, reason=i["reason"], **i["result"]) for d in prev[-1:] for i in log[d] if i.get("result")]
    for r in watch: r["reason"] = reason(r)
    tb = ["قائمة مراقبة لغدٍ (وصفية، غير مختبرة؛ الدخول = كسر أعلى سعر اليوم، هدف +1%%، وقف -0.8%%، وتكلفة الذهاب والإياب حسب مصرف أبوظبي الإسلامي: ADX نحو %.2f%% و DFM نحو %.2f%% شاملة الرسوم وVAT والفارق السعري، ولم تُخصم من المستويات)" % (rt_cost("ADX") * 100, rt_cost("DFM") * 100)]
    for r in watch: tb.append("%s: دخول فوق %s | هدف %s | وقف %s | السبب: %s" % (r["s"], r["entry"], r["tgt"], r["stp"], r["reason"]))
    if not watch: tb.append("لا يوجد سهم يحقق الشروط اليوم")
    if watch_eval:
        tb.append("نتيجة ترشيحات الجلسة السابقة (صافي بعد العمولة):")
        for e in watch_eval: tb.append("%s: %s%s - %s" % (e["s"], e["status"], (" %+.2f%%" % e["net"]) if e.get("net") is not None else "", e["why"]))
    return dict(date=ts[:10], text_block="\n".join(tb), watch_eval=watch_eval, ts_utc=ts, collector_ok=fresh, universe=universe_n, priced=len(rows), traded=len(traded), missing=missing,
                gainers=gain, losers=lose, top_value=val, watch=watch, core10=core, forward=fs)

def fmt_ch(x): return ("+" if x >= 0 else "−") + "%.2f%%" % abs(x)
def fmt_v(v): return ("%.1f م" % (v / 1e6)) if v >= 1e6 else ("%d ألف" % round(v / 1e3))

def wlines(items, ev=None):
    out = ""
    for r in items:
        out += '<div class="r" style="flex-wrap:wrap"><span><b>%s</b> <i>%s</i></span><span style="direction:ltr;unicode-bidi:isolate;font-size:17px">دخول فوق %s · هدف %s · وقف %s</span><span style="width:100%%;font-size:14px;color:#9fb3cc">السبب: %s</span></div>' % (r["s"], r["m"], r["entry"], r["tgt"], r["stp"], r.get("reason", ""))
    if not items: out = '<div class="r"><span>لا يوجد</span><span></span></div>'
    if ev:
        out += '<div class="ct" style="padding-top:14px">✅ نتيجة ترشيحات الجلسة السابقة (صافي بعد العمولة)</div>'
        for e in ev:
            cls = "up" if (e.get("net") or 0) > 0 else ("dn" if (e.get("net") or 0) < 0 else "")
            nt = ("%+.2f%%" % e["net"]) if e.get("net") is not None else "—"
            out += '<div class="r" style="flex-wrap:wrap"><span><b>%s</b> · %s</span><span class="%s">%s</span><span style="width:100%%;font-size:14px;color:#9fb3cc">%s</span></div>' % (e["s"], e["status"], cls, nt, e["why"])
    return out

def html(d):
    def lines(items, kind):
        out = ""
        for r in items:
            cls = "up" if r["ch"] >= 0 else "dn"
            right = fmt_ch(r["ch"]) if kind == "ch" else fmt_v(r["v"])
            out += '<div class="r"><span><b>%s</b> <i>%s</i></span><span class="%s">%s</span></div>' % (r["s"], r["m"], cls if kind == "ch" else "", right)
        return out or '<div class="r"><span>لا يوجد</span><span></span></div>'
    f = d["forward"]; r1, r2 = f.get("R1", {}), f.get("R2", {})
    health = ('<span class="ok">سليم</span>' if d["collector_ok"] else '<span class="wn">متأخر</span>')
    return """<!doctype html><html dir="rtl" lang="ar"><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0}
body{width:900px;background:#0f1b2d;font-family:"Noto Sans Arabic","Noto Naskh Arabic","DejaVu Sans",sans-serif;color:#e8eef7;padding:34px}
.h{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.t{font-size:32px;font-weight:700}.dd{font-size:19px;color:#9fb3cc}
.row{display:flex;gap:12px;margin-bottom:16px}
.box{flex:1;background:#17283f;border-radius:14px;padding:14px 16px}
.l{font-size:15px;color:#9fb3cc;margin-bottom:5px}.v{font-size:23px;font-weight:700}
.ok{color:#4ade80}.wn{color:#fbbf24}.up{color:#4ade80;direction:ltr;unicode-bidi:isolate}.dn{color:#f87171;direction:ltr;unicode-bidi:isolate}
.cols{display:flex;gap:12px;margin-bottom:16px}.col{flex:1;background:#17283f;border-radius:14px;padding:6px 16px 8px}
.ct{font-size:17px;color:#9fb3cc;padding:8px 0 2px}
.r{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #243750;font-size:19px}
.r:last-child{border:0}.r i{font-style:normal;font-size:12px;color:#7f93ad;border:1px solid #33495f;border-radius:6px;padding:0 5px}
.f{margin-top:14px;font-size:14px;color:#7f93ad;text-align:center}
</style><body>
<div class="h"><div class="t">📊 تقرير نهاية اليوم · صياد</div><div class="dd">%s</div></div>
<div class="row">
<div class="box"><div class="l">حالة الجامع</div><div class="v">%s</div></div>
<div class="box"><div class="l">الأسهم المتداولة اليوم</div><div class="v">%d من %d</div></div>
<div class="box"><div class="l">الاختبار التجريبي (ورقي) · إشارات مغلقة</div><div class="v">R1: %s · R2: %s</div></div>
</div>
<div class="cols">
<div class="col"><div class="ct">🟢 الأكثر ارتفاعًا</div>%s</div>
<div class="col"><div class="ct">🔴 الأكثر انخفاضًا</div>%s</div>
</div>
<div class="cols"><div class="col"><div class="ct">💧 الأعلى سيولة (قيمة التداول)</div>%s</div></div>
<div class="cols"><div class="col"><div class="ct">👁 قائمة مراقبة لليوم التالي (وصفية، ليست توصية)</div>%s<div class="l" style="padding:6px 0">التكلفة ذهابًا وإيابًا (مصرف أبوظبي الإسلامي): ADX ~0.66%% · DFM ~0.92%% · مستوى الدخول = كسر أعلى سعر اليوم · هدف +1%% · وقف −0.8%%. الشروط: لا قفزة سيولة مفاجئة · ارتفاع 0.5–4%% · إغلاق قرب أعلى اليوم · سيولة ≥ 1م · غير مختبرة</div></div></div>
<div class="f">تحليل وصفي وليس توصية شراء أو بيع · الاختبار التجريبي ورقي ولا يُحكم عليه قبل 30 إشارة مغلقة لكل قاعدة</div>
</body></html>""" % (d["date"], health, d["traded"], d["universe"],
        r1.get("closed", "؟"), r2.get("closed", "؟"),
        lines(d["gainers"], "ch"), lines(d["losers"], "ch"), lines(d["top_value"], "v"), wlines(d.get("watch", []), d.get("watch_eval")))

def main():
    d = build()
    out = os.path.join(ROOT, "report"); os.makedirs(out, exist_ok=True)
    json.dump(d, open(os.path.join(out, "latest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    h = os.path.join(out, "card.html"); open(h, "w", encoding="utf-8").write(html(d))
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 968, "height": 700}, device_scale_factor=2)
            pg.goto("file://" + os.path.abspath(h)); pg.locator("body").screenshot(path=os.path.join(out, "latest.png")); b.close()
    except Exception as e:
        print("png failed:", e)
    os.remove(h)
    print("report ok", d["date"], "traded", d["traded"], "missing", len(d["missing"]))

if __name__ == "__main__":
    main()
