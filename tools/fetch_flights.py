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
# 成田発の国内線(格安航空が多い)
for d in ["CTS", "FUK", "OKA", "KIX", "KMJ", "KOJ", "NGS", "MYJ", "TAK", "OIT", "KMI", "ISG", "HKD", "SDJ", "HIJ"]:
    pairs += [("NRT", d)]

JST = datetime.timezone(datetime.timedelta(hours=9))
today = datetime.datetime.now(JST).date()
days = [today + datetime.timedelta(days=k) for k in (0, 1, 2)]

MONTH_CACHE = {}
def month_items(o, d, ym):
    """月単位で聞くと、同じ日の別の便も返ることがある(日付ごとだと最安1便だけのことが多い)"""
    key = (o, d, ym)
    if key in MONTH_CACHE:
        return MONTH_CACHE[key]
    q = urllib.parse.urlencode({"origin": o, "destination": d, "departure_at": ym, "one_way": "true", "direct": "false",
                                "sorting": "route", "unique": "false", "limit": 1000, "market": "jp", "currency": "jpy", "token": TOKEN})
    req = urllib.request.Request("https://api.travelpayouts.com/aviasales/v3/prices_for_dates?" + q, headers={"User-Agent": "officetravel-flights/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            MONTH_CACHE[key] = json.load(r).get("data", []) or []
    except Exception as e:  # noqa
        print("month fail", o, d, ym, e)
        MONTH_CACHE[key] = []
    time.sleep(0.25)
    return MONTH_CACHE[key]

def fetch(o, d, day):
    out = fetch_day(o, d, day)
    seen = {(x["airline"], x["flight_number"], x["departure_at"]) for x in out}
    for x in month_items(o, d, day.isoformat()[:7]):
        if not x.get("departure_at") or not x.get("airline") or not str(x["departure_at"]).startswith(day.isoformat()):
            continue
        k = (x.get("airline"), str(x.get("flight_number") or ""), x.get("departure_at"))
        if k in seen:
            continue
        seen.add(k)
        out.append({"price": x.get("price"), "airline": x.get("airline"), "flight_number": str(x.get("flight_number") or ""),
                    "departure_at": x.get("departure_at"), "duration": x.get("duration_to") or x.get("duration") or 0,
                    "transfers": x.get("transfers") or 0, "link": x.get("link") or ""})
    out.sort(key=lambda x: x["departure_at"])
    return out

def fetch_day(o, d, day):
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
index = {"updated": now, "pairs": [], "days": [d.isoformat() for d in days], "min": {}}
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
    # 路線ごとの最安(片道・乗り継ぎ1回まで): アプリが遠出の行き先を選ぶ目安に使う
    best = None
    for day, arr in rec["days"].items():
        for x in arr or []:
            try:
                pr = int(x.get("price") or 0)
            except Exception:
                continue
            if pr > 0 and (x.get("transfers") or 0) <= 1 and (best is None or pr < best[0]):
                best = (pr, day)
    if best:
        index["min"][f"{o}-{d}"] = [best[0], best[1]]
with open("data/flights/index.json", "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False)
print("done", len(pairs), "pairs,", errors, "errors")
for p in ("HND-CTS", "HND-FUK", "HND-OKA", "HND-ICN"):
    try:
        j = json.load(open(f"data/flights/{p}.json", encoding="utf-8"))
        print(p, {k: len(v or []) for k, v in j["days"].items()})
    except Exception as e:  # noqa
        print(p, e)
