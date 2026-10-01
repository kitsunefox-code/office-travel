# 農林水産省「うちの郷土料理」から、都道府県ごとの郷土料理の名前・短い説明・ページURLを集める(年に数回で十分)
# 出典: 農林水産省「うちの郷土料理」 https://www.maff.go.jp/j/keikaku/syokubunka/k_ryouri/ (政府標準利用規約に従い出典を表示)
import json, os, re, time, urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
BASE = 'https://www.maff.go.jp/j/keikaku/syokubunka/k_ryouri/search_menu/area/'
UA = 'OfficeTravel/1.0 (https://kusayakyu-navi.com/office-travel/)'

def get(u):
    req = urllib.request.Request(u, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode('utf-8', 'replace')

def main():
    idx = get(BASE + 'index.html')
    prefs = []
    for href, name in re.findall(r'href="(/j/keikaku/syokubunka/k_ryouri/search_menu/area/([a-z]+)\.html)"[^>]*>\s*([^<]{2,5})<', idx) and [] or []:
        pass
    for m in re.finditer(r'href="/j/keikaku/syokubunka/k_ryouri/search_menu/area/([a-z]+)\.html"[^>]*>\s*([^<]{2,5})<', idx):
        slug, ja = m.group(1), m.group(2).strip()
        if (slug, ja) not in prefs and slug != 'index':
            prefs.append((slug, ja))
    out = {}
    for slug, ja in prefs:
        try:
            h = get(BASE + slug + '.html')
        except Exception as e:  # noqa
            print('fail', slug, e)
            continue
        items = []
        for m in re.finditer(r'<a class="hover" href="\.\./menu/([^"]+\.html)">\s*<p><img[^>]*></p>\s*<p class="tit">(.*?)</p>\s*<p class="txt">(.*?)</p>', h, re.S):
            n = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            d = re.sub(r'<[^>]+>|\s+', '', m.group(3)).replace('...', '…')
            items.append({'n': n, 'd': d[:70], 'u': 'https://www.maff.go.jp/j/keikaku/syokubunka/k_ryouri/search_menu/menu/' + m.group(1)})
        key = ja if ja == '北海道' else re.sub(r'(都|府|県)$', '', ja)
        out[key] = {'full': ja, 'items': items[:40]}
        print(ja, len(items))
        time.sleep(1.0)
    json.dump({'src': '農林水産省「うちの郷土料理」', 'url': 'https://www.maff.go.jp/j/keikaku/syokubunka/k_ryouri/', 'at': time.strftime('%Y-%m-%d'), 'prefs': out},
              open(os.path.join(ROOT, 'data', 'kyodo.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('prefs', len(out))

if __name__ == '__main__':
    main()
