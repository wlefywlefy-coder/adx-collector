import json, os, sys, time, datetime
import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
SOURCES = {
    "adx": {
        "url": "https://apigateway.adx.ae/adx/marketwatch/1.1/securityBoards/mainMarket",
        "status_url": "https://apigateway.adx.ae/adx/marketwatch/1.1/trading-status",
        "referer": "https://www.adx.ae/",
    },
    "dfm": {
        "url": "https://www.dfm.ae/mw/v1/stocks",
        "status_url": "https://www.dfm.ae/mw/v1/status",
        "referer": "https://www.dfm.ae/",
    },
}

def fetch(url, referer):
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Referer": referer, "Origin": referer.rstrip("/")}
    r = requests.get(url, headers=h, timeout=30)
    return r.status_code, r.text

now = datetime.datetime.now(datetime.timezone.utc)
out = {"ts_utc": now.isoformat(timespec="seconds"), "sources": {}}
for name, s in SOURCES.items():
    rec = {"ok": False}
    try:
        code, body = fetch(s["url"], s["referer"])
        rec["http"] = code
        rec["bytes"] = len(body)
        if code == 200:
            rec["data"] = json.loads(body)
            rec["ok"] = True
        else:
            rec["error"] = body[:200]
        try:
            c2, b2 = fetch(s["status_url"], s["referer"])
            rec["status_http"] = c2
            if c2 == 200:
                rec["market_status"] = json.loads(b2)
        except Exception as e:
            rec["status_error"] = str(e)[:150]
    except Exception as e:
        rec["error"] = str(e)[:200]
    out["sources"][name] = rec

os.makedirs("data", exist_ok=True)
day = now.strftime("%Y-%m-%d")
os.makedirs("data/" + day, exist_ok=True)
txt = json.dumps(out, ensure_ascii=False)
open("data/latest.json", "w", encoding="utf-8").write(txt)
open("data/%s/%s.json" % (day, now.strftime("%H%M")), "w", encoding="utf-8").write(txt)
print({k: (v.get("ok"), v.get("http"), v.get("bytes"), (v.get("error") or "")[:80]) for k, v in out["sources"].items()})
