import json, os, re, time, datetime
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PAGES = {
    "adx": {
        "page": "https://www.adx.ae/",
        "want": {
            "stocks": r"/marketwatch/1\.1/securityBoards/mainMarket",
            "status": r"/marketwatch/1\.1/trading-status",
        },
    },
    "dfm": {
        "page": "https://www.dfm.ae/",
        "want": {
            "stocks": r"/mw/v1/stocks",
            "status": r"/mw/v1/status",
            "indices": r"/mw/v1/indices",
        },
    },
}

now = datetime.datetime.now(datetime.timezone.utc)
out = {"ts_utc": now.isoformat(timespec="seconds"), "sources": {}}

with sync_playwright() as p:
    b = p.chromium.launch()
    for name, cfg in PAGES.items():
        rec = {"ok": False, "parts": {}}
        got = {}
        try:
            ctx = b.new_context(user_agent=UA)
            pg = ctx.new_page()
            def on_resp(r, got=got, cfg=cfg):
                for key, pat in cfg["want"].items():
                    if re.search(pat, r.url) and r.status == 200 and key not in got:
                        try:
                            got[key] = json.loads(r.text())
                        except Exception:
                            pass
            pg.on("response", on_resp)
            pg.goto(cfg["page"], wait_until="domcontentloaded", timeout=60000)
            for _ in range(20):
                if "stocks" in got:
                    break
                pg.wait_for_timeout(1500)
            pg.wait_for_timeout(1500)
            ctx.close()
        except Exception as e:
            rec["error"] = str(e)[:200]
        rec["parts"] = got
        rec["ok"] = "stocks" in got
        out["sources"][name] = rec
    b.close()

os.makedirs("data", exist_ok=True)
day = now.strftime("%Y-%m-%d")
os.makedirs("data/" + day, exist_ok=True)
txt = json.dumps(out, ensure_ascii=False)
open("data/latest.json", "w", encoding="utf-8").write(txt)
open("data/%s/%s.json" % (day, now.strftime("%H%M")), "w", encoding="utf-8").write(txt)
print({k: (v["ok"], list(v["parts"].keys()), v.get("error")) for k, v in out["sources"].items()})
