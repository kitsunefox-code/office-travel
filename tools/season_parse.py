import re, urllib.request
BASE = 'https://www.data.jma.go.jp/sakura/data/'
def get(name):
    raw = urllib.request.urlopen(urllib.request.Request(BASE + name, headers={'User-Agent': 'officetravel-season/1.0'}), timeout=60).read()
    return raw.decode('utf-8', errors='replace')
def pre_rows(html):
    """sakura003/004: pre text, name then month/day pairs (2021..2026 + normal)"""
    m = re.search(r'<pre[^>]*>(.*?)</pre>', html, re.S | re.I)
    out = {}
    for line in (m.group(1) if m else '').splitlines():
        line = re.sub(r'<[^>]+>', '', line).rstrip()
        mm = re.match(r'^\s*([^\s\d\*\-]+)\s*\*?\s+(.*)$', line)
        if not mm: continue
        name, rest = mm.group(1), mm.group(2)
        toks = re.findall(r'\d+|-', rest)
        vals, i = [], 0
        while i < len(toks):
            if toks[i] == '-': vals.append(None); i += 1
            elif i + 1 < len(toks) and toks[i+1] != '-': vals.append((int(toks[i]), int(toks[i+1]))); i += 2
            else: vals.append(None); i += 1
        if len(vals) >= 7: out[name] = {'y2026': vals[5], 'normal': vals[6]}
    return out
def phn_rows(html):
    """phn_0xx: table rows 地点名 | 2025 観測日 平年差 昨年差 | 2026 観測日 平年差 昨年差 | 代替種目"""
    out = {}
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S | re.I):
        cells = [re.sub(r'<[^>]+>|&nbsp;', ' ', c).strip() for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S | re.I)]
        if len(cells) < 4 or not cells[0] or '地点' in cells[0]: continue
        def md(s):
            m = re.match(r'(\d+)月\s*(\d+)日', s or '')
            return (int(m.group(1)), int(m.group(2))) if m else None
        def num(s):
            m = re.match(r'([+-]?\d+)$', (s or '').strip())
            return int(m.group(1)) if m else None
        d25, diff25 = md(cells[1]), num(cells[2])
        d26 = md(cells[4]) if len(cells) > 4 else None
        normal = None
        if d25 and diff25 is not None:
            import datetime
            nd = datetime.date(2025, d25[0], d25[1]) - datetime.timedelta(days=diff25)
            normal = (nd.month, nd.day)
        out[cells[0].replace(' ', '')] = {'y2026': d26, 'normal': normal}
    return out
if __name__ == '__main__':
    import json
    a = pre_rows(get('sakura003_07.html')); b = phn_rows(get('phn_014.html')); c = phn_rows(get('phn_012.html'))
    print(len(a), len(b), len(c))
    print('tokyo', a.get('東京'), b.get('東京'), c.get('東京'))
    names = sorted(set(a) | set(b) | set(c))
    print(' '.join(names))
