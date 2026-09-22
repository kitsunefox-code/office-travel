/* オフィストラベル service worker
   - 本体(index.html 等)は「まずネット、だめならキャッシュ」: 新しい版がすぐ届く。電波が無くても部屋までは開ける
   - data/ 配下(便のデータ・街の初期データ)は「まずネット、だめならキャッシュ」
   - 他サイト(地図タイル・乗換案内・天気)は触らない
*/
const VER='ot-v67';
const SHELL=['./','index.html','manifest.webmanifest','icon-192.png','icon-512.png','data/kichijoji.js'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(VER).then(c=>c.addAll(SHELL).catch(()=>{})).then(()=>self.skipWaiting()));});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==VER).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(u.origin!==location.origin||e.request.method!=='GET')return;
  e.respondWith((async()=>{try{const isDoc=e.request.mode==='navigate'||e.request.destination==='document'||/\.(html|js|webmanifest)$/.test(u.pathname)||u.pathname.endsWith('/');const r=await fetch(isDoc?new Request(e.request,{cache:'no-cache'}):e.request);if(r&&r.ok){const c=await caches.open(VER);c.put(e.request,r.clone()).catch(()=>{});}return r;}
    catch(err){const c=await caches.open(VER);const hit=await c.match(e.request,{ignoreSearch:true});if(hit)return hit;if(e.request.mode==='navigate'){const idx=await c.match('index.html');if(idx)return idx;}throw err;}})());});
self.addEventListener('notificationclick',e=>{e.notification.close();e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(cs=>{for(const c of cs){if('focus' in c)return c.focus();}return self.clients.openWindow('./');}));});
