# Travelpayouts(Aviasales Data API v3)から、今日と明日の最安便を取って data/flights/*.json に書く。
# ブラウザから直接呼べない(CORS)ので、GitHub Actions が定期的にこれを動かして静的ファイルにする。
import json, os, sys, time, urllib.parse, urllib.request, datetime

TOKEN = os.environ.get("TP_TOKEN", "").strip()
if not TOKEN:
    print("TP_TOKEN is not set; nothing to do")
    sys.exit(0)

HOME = ["HND", "NRT"]
WORLD = ["ICN","PUS","TPE","HKG","PVG","PEK","BKK","HAN","SGN","SIN","KUL","MNL","GUM","HNL","SYD","LAX","SFO","JFK","LHR","CDG","FCO","BCN","BER","AMS","IST","DXB"]
DOMESTIC = ["CTS","FUK","ITM","KIX","NGO","OKA","HIJ","SDJ","KMQ","KOJ","NGS","KMJ","HKD","AKJ","KIJ","OKJ","MYJ","TAK","OIT","KMI","ISG","UBJ","KCZ","TOY"]

pairs = []
for d in WORLD:
    pairs += [("HND", d), ("NRT", d), (d, "HND")]
for d in DOMESTIC:
    pairs += [("HND", d), (d, "HND")]

JST = datetime.timezone(datetime.timedelta(hours=9))
today = datetime.datetime.now(JST).date()
days = [today + datetime.timedelta(days=k) for k in (0, 1, 2)]

def fetch(o, d, day):
    q = urllib.parse.urlencode({"origin": o, "destination": d, "departure_at": day.isoformat(), "one_way": "true",
                                "direct": "false", "sorting": "price", "limit": 30, "currency": "jpy", "token": TOKEN})
    url = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates?" + q
    req = urllib.request.Request(url, headers={"User-Agent": "officetravel-flights/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.load(r)
    out = []
    for x in j.get("data", []) or []:
        if not x.get("departure_at") or not x.get("airline"):
            continue
        out.append({"price": x.get("price"), "airline": x.get("airline"), "flight_number": str(x.get("flight_number") or ""),
                    "departure_at": x.get("departure_at"), "duration": x.get("duration_to") or x.get("duration") or 0,
                    "transfers": x.get("transfers") or 0, "link": x.get("link") or ""})
    return out

os.makedirs("data/flights", exist_ok=True)
now = datetime.datetime.now(JST).isoformat(timespec="minutes")
index = {"updated": now, "pairs": [], "days": [d.isoformat() for d in days]}
errors = 0
for (o, d) in pairs:
    rec = {"updated": now, "origin": o, "destination": d, "days": {}}
    for day in days:
        try:
            rec["days"][day.isoformat()] = fetch(o, d, day)
        except Exception as e:  # noqa
            errors += 1
            print("fail", o, d, day, e)
            rec["days"][day.isoformat()] = None
        time.sleep(0.25)
    with open(f"data/flights/{o}-{d}.json", "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, separators=(",", ":"))
    index["pairs"].append(f"{o}-{d}")
with open("data/flights/index.json", "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False)
print("done", len(pairs), "pairs,", errors, "errors")
