# 美術館・博物館・水族館・動物園の「いまの展示」を、各館の公式サイトから集める(週1回、GitHub Actions)。
# - 対象: OpenStreetMap で website の登録がある館(全国)
# - 読むもの: 検索エンジン向けのイベント情報(JSON-LD の Event)と、「◯◯展 2026年9月1日〜11月3日」のような会期の記載
# - robots.txt を守る。1つのサイトに読むのは最大4ページ。名前・会期・公式ページのURLだけを残す(本文は保存しない)
# - 公式X・Instagram は OSM に登録がある時だけリンクとして残す(SNS自体は読まない)
import json, os, re, sys, time, datetime, urllib.request, urllib.parse, urllib.robotparser, concurrent.futures as cf
from html.parser import HTMLParser

UA = "OfficeTravelBot/1.0 (+https://kusayakyu-navi.com/office-travel/)"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "exhibits.json")
JST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(JST).date()
HORIZON = TODAY + datetime.timedelta(days=75)
LIMIT = int(os.environ.get("EX_LIMIT", "0") or 0)          # テスト用: 館の数を絞る
PREF = os.environ.get("EX_AREA", "")                          # テスト用: 例 "東京都"

def http(url, timeout=12, maxbytes=1_500_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ct = r.headers.get("Content-Type", "")
        if "html" not in ct and "xml" not in ct and ct:
            return None, r.geturl()
        raw = r.read(maxbytes)
        m = re.search(r"charset=([\w-]+)", ct, re.I) or re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw[:4000], re.I)
        enc = (m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)).lower() if m else "utf-8"
        if enc in ("shift_jis", "sjis", "x-sjis", "shift-jis"): enc = "cp932"
        for e in (enc, "utf-8", "cp932", "euc-jp"):
            try: return raw.decode(e), r.geturl()
            except Exception: pass
        return raw.decode("utf-8", "ignore"), r.geturl()

VCACHE = os.path.join(os.path.dirname(__file__), "..", "data", "exhibit_venues.json")
REGIONS = [(24.0,122.9,31.0,132.0),(31.0,128.0,34.7,134.5),(33.0,130.8,36.2,136.0),(34.2,135.9,36.2,139.2),(35.0,139.2,36.0,140.9),(36.0,136.0,38.7,142.2),(38.7,139.0,41.6,142.2),(41.3,139.3,45.8,146.0)]
def overpass():
    """全国の館を地域ごとに取る。どこかで失敗したら、保存しておいた一覧を使う"""
    out = []; ok = True
    for (a, b, c, d) in REGIONS:
        q = f'[out:json][timeout:120];nwr({a},{b},{c},{d})[tourism~"^(museum|gallery|aquarium|zoo)$"][website][name];out tags center qt;'
        got = None
        for host in ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"):
            try:
                req = urllib.request.Request(host, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": UA, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=150) as r:
                    got = json.loads(r.read().decode("utf-8"))["elements"]; break
            except Exception as e:
                print("overpass", host, (a, b), e, file=sys.stderr); time.sleep(5)
        if got is None: ok = False; break
        out += got
    if ok and len(out) > 500:
        seen = set(); uniq = []
        for e in out:
            k = (e.get("type"), e.get("id"))
            if k in seen: continue
            seen.add(k); uniq.append(e)
        with open(VCACHE, "w", encoding="utf-8") as f:
            json.dump({"updated": TODAY.isoformat(), "elements": [{"lat": e.get("lat") or (e.get("center") or {}).get("lat"), "lon": e.get("lon") or (e.get("center") or {}).get("lon"), "tags": e.get("tags", {})} for e in uniq]}, f, ensure_ascii=False, separators=(",", ":"))
        return uniq
    try:
        with open(VCACHE, encoding="utf-8") as f: cached = json.load(f)["elements"]
        print("use cached venues", len(cached), file=sys.stderr); return cached
    except Exception as e:
        print("no venue cache", e, file=sys.stderr); return []

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.links = []; self.ld = []; self.lines = []; self._a = None; self._ld = False; self._skip = 0; self._buf = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"): self._a = [a["href"], ""]
        if tag == "script": self._ld = (a.get("type", "").lower() == "application/ld+json"); self._skip += 0 if self._ld else 1
        if tag == "style": self._skip += 1
        if tag in ("br", "p", "div", "li", "h1", "h2", "h3", "h4", "dt", "dd", "tr", "td", "section", "article", "span"): self._flush()
    def handle_endtag(self, tag):
        if tag == "a" and self._a: self.links.append(tuple(self._a)); self._a = None
        if tag == "script":
            if self._ld: self._ld = False
            else: self._skip = max(0, self._skip - 1)
        if tag == "style": self._skip = max(0, self._skip - 1)
        if tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "dt", "dd", "tr", "td"): self._flush()
    def handle_data(self, d):
        if self._ld: self.ld.append(d); return
        if self._skip: return
        if self._a is not None: self._a[1] += d
        self._buf.append(d)
    def _flush(self):
        t = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if t: self.lines.append(t)
        self._buf = []
    def close(self):
        super().close(); self._flush()

KEY = re.compile(r"(exhibit|exhibition|special|event|展覧会|企画展|特別展|展示|イベント|current|schedule)", re.I)
Z = str.maketrans("０１２３４５６７８９／．", "0123456789/.")
SEP = r"\s*(?:～|〜|~|－|—|―|‐|-|–|から|より|＿)\s*"
DATE = r"(?:(\d{4})\s*[年./]\s*)?(\d{1,2})\s*[月./]\s*(\d{1,2})\s*日?(?:\s*[（(][^)）]{1,4}[)）])?"
RANGE = re.compile(DATE + SEP + DATE)

def mkdate(y, m, d, ref_year):
    try: return datetime.date(int(y) if y else ref_year, int(m), int(d))
    except Exception: return None

BAD = re.compile(r"(お知らせ|ご案内|案内|一覧|次回|会期|会場|展示替|休止|休館|募集|期間|※|開催日|について|のみ|終了|延期|中止|日程|スケジュール|アーカイブ|過去の|詳しく|詳細|こちら|チラシ|PDF|ページ)")
GENERIC = {"特別展","企画展","企画展示","イベント","展覧会","常設展","特集展示","テーマ展","展示","特別展示","コレクション展","収蔵品展","イベント情報","展覧会情報","現在の特別展","現在の企画展","開催中の展覧会","今後の展覧会","これからの展覧会","開催中の展示","現在の展示","Exhibition","Exhibitions","EXHIBITION"}
def good_title(t):
    if not t or "。" in t or "ます" in t or t.endswith(("を","に","は","が","で")): return False
    core = re.sub(r"[「『」』（）()<>＜＞【】\[\]\s・:：]", "", t)
    if core in GENERIC or len(core) < 3: return False
    ns = re.sub(r"\s+", "", t)
    if BAD.search(ns) and not re.search(r"[「『].{2,}[」』]", t): return False
    if re.search(r"(を終えて|について|のお知らせ|レポート|ブログ|記事|更新|トップ|ニュース)", ns): return False
    return True
def clean_title(t):
    t = re.sub(r"\s+", " ", t).strip(" 　:：|｜-–—")
    t = re.sub(r"^[^「『]{0,8}】\s*", "", t)
    t = re.sub(r"^【[^】]{0,12}】\s*", "", t)
    t = re.sub(r"^[^\w「『（(]+", "", t)
    t = re.sub(r"[（(\[【]\s*$", "", t).strip()
    t = re.sub(r"^(開催中|会期中|終了間近|NEW|new|特集|お知らせ|展覧会|企画展|特別展)[\s:：・|｜]+", "", t)
    return t[:60]

def looks_title(t):
    if not (3 <= len(t) <= 70): return False
    if re.search(r"(休館|開館時間|料金|アクセス|チケット|お問い合わせ|Copyright|©|http|予約|メール|電話|TEL|住所)", t, re.I): return False
    return bool(re.search(r"(展|フェア|まつり|祭|特集|コレクション|企画|イベント|ウィーク|フェス|Exhibition|exhibition)", t))

def extract(html, url):
    p = Page()
    try: p.feed(html); p.close()
    except Exception: pass
    items = []
    for blob in p.ld:                                  # 1) JSON-LD の Event
        try: data = json.loads(blob.strip())
        except Exception: continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                if "@graph" in o: stack.extend(o["@graph"] if isinstance(o["@graph"], list) else [o["@graph"]])
                ty = o.get("@type"); ty = ty if isinstance(ty, list) else [ty]
                if any(str(x).endswith("Event") for x in ty) and o.get("name"):
                    try:
                        s = datetime.date.fromisoformat(str(o.get("startDate", ""))[:10]); e = datetime.date.fromisoformat(str(o.get("endDate", o.get("startDate", "")))[:10])
                        items.append({"t": clean_title(str(o["name"])), "s": s.isoformat(), "e": e.isoformat(), "u": o.get("url") or url})
                    except Exception: pass
            elif isinstance(o, list): stack.extend(o)
    lines = [l.translate(Z) for l in p.lines]        # 2) 会期の記載の近くの「◯◯展」
    for i, l in enumerate(lines):
        for m in RANGE.finditer(l):
            y1, m1, d1, y2, m2, d2 = m.groups()
            ry = int(y1) if y1 else (int(y2) if y2 else TODAY.year)
            s = mkdate(y1, m1, d1, ry); e = mkdate(y2 or (y1 if not y2 else None), m2, d2, ry)
            if not s or not e: continue
            if e < s: e = mkdate(ry + 1, m2, d2, ry + 1) or e
            if (e - s).days > 400 or (e - s).days < 0: continue
            title = None
            same = l[:m.start()].strip()
            cands = [same] + [lines[k] for k in range(i - 1, max(-1, i - 4), -1)] + [lines[k] for k in range(i + 1, min(len(lines), i + 2))]
            for c in cands:
                q = re.search(r"((?:[^\s「『、。]{0,10}(?:展|展示|企画|特集))?[「『][^」』]{2,50}[」』](?:展)?)", c)
                if q: title = q.group(1); break
                if looks_title(c): title = c; break
            if title: items.append({"t": clean_title(title), "s": s.isoformat(), "e": e.isoformat(), "u": url})
    return items, p.links

def allowed(rp, url):
    try: return rp.can_fetch(UA, url)
    except Exception: return True

def crawl(v):
    t = v["tags"]; site = t.get("website") or t.get("contact:website") or t.get("url")
    if not site: return None
    if not site.startswith("http"): site = "http://" + site
    host = urllib.parse.urlsplit(site).netloc
    rp = urllib.robotparser.RobotFileParser(); rp.set_url(urllib.parse.urljoin(site, "/robots.txt"))
    try: rp.read()
    except Exception: pass
    items = []; seen = set(); pages = 0
    queue = [site]
    while queue and pages < 4:
        u = queue.pop(0)
        if u in seen or not allowed(rp, u): continue
        seen.add(u)
        try: html, final = http(u)
        except Exception: continue
        pages += 1
        if not html: continue
        got, links = extract(html, final)
        items += got
        if pages == 1:
            ranked = []
            for href, txt in links:
                full = urllib.parse.urljoin(final, href).split("#")[0]
                if urllib.parse.urlsplit(full).netloc != urllib.parse.urlsplit(final).netloc: continue
                if KEY.search(href) or KEY.search(txt or ""): ranked.append(full)
            for r in ranked[:3]:
                if r not in seen: queue.append(r)
        time.sleep(0.6)
    out = {}
    for it in items:
        try: s = datetime.date.fromisoformat(it["s"]); e = datetime.date.fromisoformat(it["e"])
        except Exception: continue
        vn = re.sub(r"\s+", "", t.get("name", ""))
        if e < TODAY or s > HORIZON or not good_title(it["t"]) or re.sub(r"[「『」』\s]", "", it["t"]) in vn: continue
        k = it["t"]
        if k not in out or (out[k]["u"] == site and it["u"] != site): out[k] = it
    lat = v.get("lat") or (v.get("center") or {}).get("lat"); lon = v.get("lon") or (v.get("center") or {}).get("lon")
    sns = {}
    for k, name in (("contact:twitter", "x"), ("contact:x", "x"), ("contact:instagram", "ig"), ("contact:facebook", "fb")):
        if t.get(k): sns[name] = t[k]
    vals = sorted(out.values(), key=lambda x: (x["s"], -len(x["t"])))
    keep = []
    for it in vals:
        core = re.sub(r"[「『」』\s]", "", it["t"])
        if any((core in re.sub(r"[「『」』\s]", "", k["t"]) or re.sub(r"[「『」』\s]", "", k["t"]) in core) and k["e"] == it["e"] for k in keep): continue
        keep.append(it)
    items = keep[:6]
    if not items and not sns: return None
    return {"n": t.get("name:ja") or t.get("name"), "k": t.get("tourism"), "la": round(lat, 5) if lat else None, "lo": round(lon, 5) if lon else None, "url": site, "sns": sns or None, "items": items}

def main():
    vs = overpass()
    if PREF: vs = [v for v in vs if PREF in json.dumps(v.get("tags", {}), ensure_ascii=False)]
    bb = os.environ.get("EX_BBOX")
    if bb:
        a, b, c, d = map(float, bb.split(","))
        def ll(v): return (v.get("lat") or (v.get("center") or {}).get("lat") or 0, v.get("lon") or (v.get("center") or {}).get("lon") or 0)
        vs = [v for v in vs if a <= ll(v)[0] <= c and b <= ll(v)[1] <= d]
    vs.sort(key=lambda v: ("wikidata" not in v["tags"], v["tags"].get("name", "")))
    uniq = {}
    for v in vs:
        k = (v["tags"].get("name"), (v["tags"].get("website") or "").rstrip("/"))
        if k not in uniq: uniq[k] = v
    vs = list(uniq.values())
    if LIMIT: vs = vs[:LIMIT]
    print("venues", len(vs), file=sys.stderr)
    res = []
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(lambda v: (lambda: crawl(v))() if True else None, vs):
            if r: res.append(r)
    with_items = sum(1 for r in res if r["items"])
    if not res or with_items == 0:
        print("nothing collected; keep previous data", file=sys.stderr); sys.exit(1)
    data = {"updated": datetime.datetime.now(JST).strftime("%Y-%m-%dT%H:%M+09:00"), "source": "各館の公式サイト(JSON-LDと会期の記載)。OpenStreetMap の website/SNS タグ", "venues": res}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("venues with exhibits", with_items, "total kept", len(res), file=sys.stderr)

if __name__ == "__main__":
    main()
