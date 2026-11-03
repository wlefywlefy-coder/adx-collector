import json, time
from playwright.sync_api import sync_playwright

TARGETS = [
    "https://www.adx.ae/",
    "https://www.adx.ae/main-market/",
    "https://www.dfm.ae/",
    "https://marketwatch.dfm.ae/",
]
out = {"ts": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "targets": []}

with sync_playwright() as p:
    b = p.chromium.launch()
    for url in TARGETS:
        rec = {"url": url, "status": None, "title": None, "text": None, "xhr": [], "error": None}
        try:
            ctx = b.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36")
            pg = ctx.new_page()
            def on_resp(r, rec=rec):
                ct = r.headers.get("content-type", "")
                if "json" in ct or "xml" in ct:
                    try:
                        body = r.text()[:400]
                    except Exception:
                        body = None
                    rec["xhr"].append({"url": r.url[:200], "status": r.status, "snippet": body})
            pg.on("response", on_resp)
            resp = pg.goto(url, wait_until="networkidle", timeout=45000)
            rec["status"] = resp.status if resp else None
            pg.wait_for_timeout(4000)
            rec["title"] = pg.title()
            rec["text"] = pg.inner_text("body")[:1500]
            ctx.close()
        except Exception as e:
            rec["error"] = str(e)[:300]
        out["targets"].append(rec)
    b.close()

json.dump(out, open("probe_output.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({t["url"]: (t["status"], t["error"], len(t["xhr"])) for t in out["targets"]}))
