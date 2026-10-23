// Cache the shell only. Game state, access tokens and AI responses stay out of caches.
const CACHE='voyager-shell-v3';
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(c=>c.addAll(['./styles.css','./app.js','./icon.svg','./manifest.webmanifest']))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))));
self.addEventListener('fetch',event=>{const u=new URL(event.request.url);if(u.origin!==location.origin||event.request.method!=='GET'||!['/styles.css','/app.js','/icon.svg','/manifest.webmanifest'].includes(u.pathname))return;event.respondWith(fetch(event.request).then(r=>{if(r.ok){const copy=r.clone();caches.open(CACHE).then(c=>c.put(event.request,copy));}return r;}).catch(()=>caches.match(event.request)));});
