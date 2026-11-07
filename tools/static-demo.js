// The live demo (GitHub Pages): the dashboard's pages unchanged, with this loaded first. Reads from the dashboard's
// API come from the JSON files tools/export_static.py saved; anything that would change something gets a polite
// "this is a demo" reply instead. Keep fileFor() in step with key() in export_static.py.
(function(){
  const fileFor = url => {
    const u = new URL(url, location.href);
    let name = u.pathname.replace(/^.*?\/api\//, '').replace(/\/+$/, '').replace(/\//g, '_');
    const q = [...u.searchParams.entries()].filter(([, v]) => v !== '').sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0);
    if(q.length) name += '__' + q.map(([k, v]) => `${k}-${v}`).join('_');
    return 'data/' + name.replace(/[^A-Za-z0-9_.-]/g, '-') + '.json';
  };
  const json = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), {status, headers:{'Content-Type':'application/json'}}));
  const real = window.fetch.bind(window);
  window.BK_STATIC = true;
  window.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    const path = new URL(url, location.href).pathname;
    if(!/\/api\//.test(path)) return real(input, init);
    if(/\/api\/session$/.test(path)) return json({token: 'demo'});
    if((init.method || 'GET').toUpperCase() !== 'GET')
      return json({error: 'This is a demo with made-up data, so nothing can be changed or synced here. Install Body Kaizen to use your own.', demo: true}, 403);
    return real(fileFor(url), {cache: 'force-cache'});
  };
  const banner = () => {
    if(document.getElementById('bk-demo-banner')) return;
    const b = document.createElement('div'); b.id = 'bk-demo-banner';
    const REPO = 'https://github.com/craigbennett1981/body-kaizen';
    const gh = '<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" style="vertical-align:-2px;margin-right:5px;fill:currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>';
    b.innerHTML = '<span>Live demo with made-up data for Sam, a fictional person. Nothing you click is saved.</span>' +
      `<a href="${REPO}#quick-start">Use it with your own data →</a>` +
      `<a href="${REPO}" class="gh">${gh}Body Kaizen on GitHub · ★ Star it</a>`;
    b.style.cssText = 'position:sticky;top:0;z-index:50;display:flex;flex-wrap:wrap;justify-content:center;align-items:center;gap:6px 16px;' +
      'padding:8px 16px;font:500 13px/1.4 Archivo,system-ui,sans-serif;background:#2F5BEA;color:#fff';
    b.querySelectorAll('a').forEach(a => a.style.cssText = 'color:#fff;font-weight:700;text-decoration:none;white-space:nowrap');
    b.querySelector('a.gh').style.cssText += ';padding:3px 10px;border:1px solid rgba(255,255,255,.6);border-radius:999px';
    document.body.prepend(b);
  };
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', banner); else banner();
})();
