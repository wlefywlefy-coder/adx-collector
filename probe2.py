import json, re, time
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
out = {"adx": {}, "dfm": {}}

def run(name, start, link_pat, wait_ms=7000):
    rec = out[name]
    rec["xhr"] = []
    rec["links"] = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(user_agent=UA)
        pg = ctx.new_page()
        def on_resp(r):
            ct = r.headers.get("content-type", "")
            if "json" in ct and r.status == 200:
                u = r.url.split("?")[0]
                if not re.search(r"set-cookie|get-cookie|\.svg|_next/data|lucide|locales", u):
                    try:
                        n = len(r.text())
                    except Exception:
                        n = -1
                    rec["xhr"].append([u[:140], n])
        pg.on("response", on_resp)
        try:
            pg.goto(start, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(wait_ms)
            hrefs = pg.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            cand = [h for h in dict.fromkeys(hrefs) if re.search(link_pat, h)]
            rec["links"] = cand[:12]
            rec["xhr_before_click"] = len(rec["xhr"])
            if cand:
                pg.goto(cand[0], wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(wait_ms + 3000)
                rec["opened"] = cand[0]
                rec["title"] = pg.title()
        except Exception as e:
            rec["error"] = str(e)[:200]
        b.close()

run("adx", "https://www.adx.ae/all-equities", r"adx\.ae/.*(equit|security|company|issuer).*/[A-Za-z0-9-]+/?$")
run("dfm", "https://www.dfm.ae/market-data/stocks", r"dfm\.ae/.*(stock|security|securities|company|issuer|market-data).*")
json.dump(out, open("probe2_output.json", "w"), ensure_ascii=False, indent=1)
print({k: (len(v.get("xhr", [])), v.get("opened"), v.get("error")) for k, v in out.items()})
