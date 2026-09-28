# 海外の街の情報をまとめる(週1回 GitHub Actions)
#  - 外務省 海外安全情報オープンデータ: 危険レベル・感染症レベル・見出し(出典: 外務省海外安全ホームページ)
#  - Wikidata(CC0): 通貨・コンセントの形・緊急番号・車の通行側
#  - Wikivoyage 英語版(CC BY-SA 4.0): 見る・食べる・飲む・する・買う・泊まる の掲載(座標のあるものだけ)
# 出力: data/world.json, data/wv/<空港コード>.json
import json, re, time, os, sys, urllib.request, urllib.parse, xml.etree.ElementTree as ET

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
UA = 'OfficeTravel/1.0 (https://kusayakyu-navi.com/office-travel/; data refresh)'

# 国: ISO2, 外務省の国コード, 日本語名, 主に使われる配車アプリ(一般的な傾向), Uber が使えるか, タクシー代の目安(日本=1)
COUNTRIES = {
 'KR': ('0082', '韓国', 'カカオT', True, 0.7), 'TW': ('0886', '台湾', 'Uber', True, 0.6), 'HK': ('0852', '香港', 'Uber', True, 0.75),
 'CN': ('0086', '中国', 'DiDi', False, 0.45), 'TH': ('0066', 'タイ', 'Grab', False, 0.35), 'VN': ('0084', 'ベトナム', 'Grab', False, 0.3),
 'SG': ('0065', 'シンガポール', 'Grab', False, 0.8), 'MY': ('0060', 'マレーシア', 'Grab', False, 0.4), 'PH': ('0063', 'フィリピン', 'Grab', False, 0.35),
 'GU': ('1000', 'グアム(米国)', 'タクシー', False, 1.2), 'US': ('1000', 'アメリカ', 'Uber', True, 1.3), 'AU': ('0061', 'オーストラリア', 'Uber', True, 1.2),
 'GB': ('0044', 'イギリス', 'Uber', True, 1.4), 'FR': ('0033', 'フランス', 'Uber', True, 1.2), 'IT': ('0039', 'イタリア', 'タクシー(FreeNow など)', False, 1.2),
 'ES': ('0034', 'スペイン', 'Uber', True, 1.0), 'DE': ('0049', 'ドイツ', 'Uber', True, 1.2), 'NL': ('0031', 'オランダ', 'Uber', True, 1.3),
 'TR': ('0090', 'トルコ', 'Uber', True, 0.4), 'AE': ('0971', 'アラブ首長国連邦', 'Uber / Careem', True, 0.6)}
# 街: 空港コード → (ISO2, Wikivoyage の記事名)
CITIES = {'ICN': ('KR', 'Seoul'), 'PUS': ('KR', 'Busan'), 'TPE': ('TW', 'Taipei'), 'HKG': ('HK', 'Hong Kong'), 'PVG': ('CN', 'Shanghai'), 'PEK': ('CN', 'Beijing'),
 'BKK': ('TH', 'Bangkok'), 'HAN': ('VN', 'Hanoi'), 'SGN': ('VN', 'Ho Chi Minh City'), 'SIN': ('SG', 'Singapore'), 'KUL': ('MY', 'Kuala Lumpur'), 'MNL': ('PH', 'Manila'),
 'GUM': ('GU', 'Guam'), 'HNL': ('US', 'Honolulu'), 'SYD': ('AU', 'Sydney'), 'LAX': ('US', 'Los Angeles'), 'SFO': ('US', 'San Francisco'), 'JFK': ('US', 'New York City'),
 'LHR': ('GB', 'London'), 'CDG': ('FR', 'Paris'), 'FCO': ('IT', 'Rome'), 'BCN': ('ES', 'Barcelona'), 'BER': ('DE', 'Berlin'), 'AMS': ('NL', 'Amsterdam'),
 'IST': ('TR', 'Istanbul'), 'DXB': ('AE', 'Dubai')}

def get(url, data=None, tries=3, timeout=60):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={'User-Agent': UA, 'Accept': '*/*'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            print('  retry', i, url[:90], e, file=sys.stderr); time.sleep(3 + i * 4)
    return None

# ---------- 外務省 ----------
def mofa(code):
    b = get('https://www.ezairyu.mofa.go.jp/opendata/country/%sL.xml' % code)
    if not b or not b.lstrip().startswith(b'<?xml'): return None
    try: root = ET.fromstring(b)
    except Exception: return None
    t = lambda k: (root.findtext(k) or '').strip()
    lv = lambda p: max([n for n in (1, 2, 3, 4) if t('%s%d' % (p, n)) == '1'] or [0])
    lead = re.sub(r'\s+', ' ', t('riskLead'))[:260]
    return {'risk': lv('riskLevel'), 'inf': lv('infectionLevel'), 'title': t('riskTitle'), 'lead': lead,
            'url': t('riskMapUrl') or t('infoUrl'), 'at': root.get('lastModified', '')}

# ---------- Wikidata ----------
def wikidata():
    q = '''SELECT ?iso ?plugLabel ?emer ?driveLabel ?cur WHERE {
 VALUES ?iso { %s }
 ?c wdt:P297 ?iso .
 OPTIONAL { ?c wdt:P2853 ?plug . }
 OPTIONAL { ?c wdt:P2852 ?ei . ?ei wdt:P1329 ?emer . }
 OPTIONAL { ?c wdt:P1622 ?drive . }
 OPTIONAL { ?c wdt:P38 ?cu . ?cu wdt:P498 ?cur . }
 SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }''' % ' '.join('"%s"' % k for k in COUNTRIES)
    b = get('https://query.wikidata.org/sparql?format=json&query=' + urllib.parse.quote(q))
    out = {}
    if not b: return out
    for r in json.loads(b)['results']['bindings']:
        iso = r['iso']['value']; o = out.setdefault(iso, {'plug': set(), 'emer': set(), 'drive': set(), 'cur': set()})
        if 'plugLabel' in r:
            lab = r['plugLabel']['value']
            PM = {'NEMA 1-15': 'A', 'NEMA 5-15': 'B', 'Europlug': 'C', 'CEE 7/16': 'C', 'BS 546': 'D', 'CEE 7/5': 'E', 'Schuko': 'F', 'CEE 7/4': 'F', 'BS 1363': 'G', 'SI 32': 'H', 'AS/NZS 3112': 'I', 'SEV 1011': 'J', 'Danish': 'K', 'CEI 23-50': 'L', 'SANS 164': 'N', 'NBR 14136': 'N'}
            for k, v in PM.items():
                if k.lower() in lab.lower(): o['plug'].add(v)
            m = re.fullmatch(r'[Tt]ype ([A-O])', lab.strip())
            if m: o['plug'].add(m.group(1))
        if 'emer' in r and re.fullmatch(r'\d{2,4}', r['emer']['value']): o['emer'].add(r['emer']['value'])
        if 'driveLabel' in r: o['drive'].add('右' if 'right' in r['driveLabel']['value'] else '左')
        if 'cur' in r: o['cur'].add(r['cur']['value'])
    return {k: {kk: sorted(v) for kk, v in o.items()} for k, o in out.items()}

# ---------- Wikivoyage ----------
def wv_text(title):
    u = 'https://en.wikivoyage.org/w/api.php?action=parse&format=json&redirects=1&prop=wikitext&page=' + urllib.parse.quote(title)
    b = get(u)
    if not b: return None, title
    j = json.loads(b)
    if 'parse' not in j: return None, title
    return j['parse']['wikitext']['*'], j['parse']['title']

def templates(txt):
    i = 0
    while True:
        m = re.search(r'\{\{\s*(see|do|eat|drink|buy|sleep|listing)\s*\|', txt[i:], re.I)
        if not m: return
        st = i + m.start(); j = st + 2; d = 1
        while j < len(txt) and d:
            if txt.startswith('{{', j): d += 1; j += 2
            elif txt.startswith('}}', j): d -= 1; j += 2
            else: j += 1
        yield m.group(1).lower(), txt[st + 2:j - 2]
        i = j

def params(body):
    parts, d, cur = [], 0, ''
    k = 0
    while k < len(body):
        c2 = body[k:k + 2]
        if c2 in ('{{', '[['): d += 1; cur += c2; k += 2; continue
        if c2 in ('}}', ']]'): d -= 1; cur += c2; k += 2; continue
        if body[k] == '|' and d == 0: parts.append(cur); cur = ''
        else: cur += body[k]
        k += 1
    parts.append(cur)
    out = {}
    for p in parts[1:]:
        if '=' in p:
            a, b = p.split('=', 1); out[a.strip().lower()] = b.strip()
    return out

def clean(s):
    s = re.sub(r'<ref[^>]*>.*?</ref>|<ref[^>]*/>', '', s, flags=re.S)
    s = re.sub(r'\{\{[^{}]*\}\}', '', s)
    s = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', s)
    s = re.sub(r'\[https?://\S+ ([^\]]*)\]', r'\1', s)
    s = re.sub(r"'{2,}", '', s); s = re.sub(r'<[^>]+>', '', s)
    return re.sub(r'\s+', ' ', s).strip()

def listings(title):
    txt, real = wv_text(title)
    if not txt: return [], []
    items = []
    for kind, body in templates(txt):
        p = params(body)
        if kind == 'listing': kind = (p.get('type') or 'see').lower()
        if kind not in ('see', 'do', 'eat', 'drink', 'buy', 'sleep'): continue
        try: la, lo = float(p.get('lat', '')), float(p.get('long', ''))
        except ValueError: continue
        n = clean(p.get('name', ''))
        if not n or abs(la) > 90: continue
        it = {'n': n[:60], 'k': kind, 'la': round(la, 6), 'lo': round(lo, 6), 'pg': real}
        for key, lim in (('alt', 60), ('price', 90), ('hours', 90), ('content', 240)):
            v = clean(p.get(key, ''))
            if v: it[{'content': 'd'}.get(key, key[0] if key != 'alt' else 'alt')] = v[:lim]
        if p.get('url', '').startswith('http'): it['u'] = p['url'][:200]
        items.append(it)
    # 地区の記事へのリンク(大きな街は地区ごとに書かれている)
    subs = []
    for m in re.finditer(r'region\d+name\s*=\s*\[\[([^\]|#]+)', txt):
        subs.append(m.group(1).strip())
    for m in re.finditer(r'\[\[(%s/[^\]|#]+)' % re.escape(real), txt):
        subs.append(m.group(1).strip())
    seen = []
    for s in subs:
        if s not in seen and s != real: seen.append(s)
    return items, seen

def city_listings(title):
    items, subs = listings(title)
    for s in subs[:10]:
        if len(items) >= 400: break
        time.sleep(0.6)
        more, _ = listings(s)
        items += more
    uniq, keys = [], set()
    for it in items:
        k = (it['n'].lower(), it['k'])
        if k in keys: continue
        keys.add(k); uniq.append(it)
    return uniq

def main():
    os.makedirs(os.path.join(ROOT, 'data', 'wv'), exist_ok=True)
    wd = wikidata(); print('wikidata', len(wd))
    old = {}
    try: old = json.load(open(os.path.join(ROOT, 'data', 'world.json'), encoding='utf-8'))
    except Exception: pass
    world = {'at': time.strftime('%Y-%m-%d'), 'countries': {}, 'cities': {},
             'src': {'mofa': '外務省海外安全ホームページ', 'wikidata': 'Wikidata (CC0)', 'wv': 'Wikivoyage (CC BY-SA 4.0)'}}
    mcache = {}
    for iso, (code, ja, app, uber, fare) in COUNTRIES.items():
        if code not in mcache: mcache[code] = mofa(code); time.sleep(0.5)
        m = mcache[code] or (old.get('countries', {}).get(iso, {}).get('mofa'))
        w = wd.get(iso) or old.get('countries', {}).get(iso, {}).get('wd') or {}
        world['countries'][iso] = {'ja': ja, 'app': app, 'uber': uber, 'fare': fare, 'mofa': m, 'wd': w}
        print(iso, ja, 'mofa' if mcache[code] else 'mofa(旧)', w.get('cur'), w.get('plug'), w.get('emer'), w.get('drive'))
    total = 0
    if '--safety-only' in sys.argv:
        world['cities'] = old.get('cities', {})
        json.dump(world, open(os.path.join(ROOT, 'data', 'world.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('safety only'); return
    for iata, (iso, title) in CITIES.items():
        ls = city_listings(title)
        path = os.path.join(ROOT, 'data', 'wv', iata + '.json')
        if len(ls) < 10 and os.path.exists(path):
            print(iata, title, '少ないので前回のまま', len(ls)); n = len(json.load(open(path, encoding='utf-8')).get('items', []))
        else:
            json.dump({'city': title, 'at': world['at'], 'lic': 'Wikivoyage contributors, CC BY-SA 4.0', 'items': ls}, open(path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
            n = len(ls)
        world['cities'][iata] = {'iso': iso, 'wv': title, 'n': n}
        total += n; print(iata, title, n); time.sleep(0.8)
    json.dump(world, open(os.path.join(ROOT, 'data', 'world.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('total listings', total)
    if total < 200: sys.exit(1)

if __name__ == '__main__':
    main()
