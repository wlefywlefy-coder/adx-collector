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
    watch = sorted([r for r in traded if 0.5 <= r["ch"] <= 4 and r["v"] >= 1e6 and pos(r) >= 0.7], key=lambda r: -r["v"])[:5]
    core = [r for r in rows if r["m"] == "ADX" and r["s"] in U["CORE10"]]
    core.sort(key=lambda r: -r["ch"])
    try: fs = json.load(open(os.path.join(ROOT, "forward", "summary.json"), encoding="utf-8"))["rules"]
    except Exception: fs = {}
    now = datetime.now(timezone.utc)
    fresh = ts[:10] == now.strftime("%Y-%m-%d") and ts[11:16] >= "10:30"
    return dict(date=ts[:10], ts_utc=ts, collector_ok=fresh, universe=universe_n, priced=len(rows), traded=len(traded), missing=missing,
                gainers=gain, losers=lose, top_value=val, watch=watch, core10=core, forward=fs)

def fmt_ch(x): return ("+" if x >= 0 else "−") + "%.2f%%" % abs(x)
def fmt_v(v): return ("%.1f م" % (v / 1e6)) if v >= 1e6 else ("%d ألف" % round(v / 1e3))

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
<div class="cols"><div class="col"><div class="ct">👁 قائمة مراقبة لليوم التالي (وصفية، ليست توصية)</div>%s<div class="l" style="padding:6px 0">الشروط: ارتفاع 0.5–4%% · إغلاق قرب أعلى اليوم · سيولة ≥ 1م · غير مختبرة</div></div></div>
<div class="f">تحليل وصفي وليس توصية شراء أو بيع · الاختبار التجريبي ورقي ولا يُحكم عليه قبل 30 إشارة مغلقة لكل قاعدة</div>
</body></html>""" % (d["date"], health, d["traded"], d["universe"],
        r1.get("closed", "؟"), r2.get("closed", "؟"),
        lines(d["gainers"], "ch"), lines(d["losers"], "ch"), lines(d["top_value"], "v"), lines(d.get("watch", []), "ch"))

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
