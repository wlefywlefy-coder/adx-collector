import json, os, time
import requests

TICKERS = ["ADNOCGAS","ADNOCDRILL","ADIB","ALPHADHABI","BOROUGE","ALDAR","ADNOCLS","ADNOCDIST","FERTIGLB","PRESIGHT"]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
os.makedirs("data/history", exist_ok=True)
report = {}
for t in TICKERS:
    rec = {}
    for suffix in (".AE",):
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%s%s" % (t, suffix)
        try:
            r = requests.get(url, params={"range": "5y", "interval": "1d"}, headers={"User-Agent": UA}, timeout=30)
            rec["http"] = r.status_code
            if r.status_code == 200:
                j = r.json()["chart"]["result"][0]
                ts = j["timestamp"]
                q = j["indicators"]["quote"][0]
                rows = []
                for i, s in enumerate(ts):
                    o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
                    if None in (o, h, l, c):
                        continue
                    rows.append([time.strftime("%Y-%m-%d", time.gmtime(s)), o, h, l, c, v or 0])
                json.dump({"ticker": t, "source": "yahoo" + suffix, "rows": rows}, open("data/history/%s.json" % t, "w"))
                rec["rows"] = len(rows)
                rec["first"] = rows[0][0] if rows else None
                rec["last"] = rows[-1][0] if rows else None
                rec["currency"] = j["meta"].get("currency")
                break
            else:
                rec["err"] = r.text[:120]
        except Exception as e:
            rec["err"] = str(e)[:120]
    report[t] = rec
    time.sleep(1)
json.dump(report, open("data/history/_report.json", "w"), indent=1)
print(json.dumps(report))
