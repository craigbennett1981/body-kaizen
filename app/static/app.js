const $ = s => document.querySelector(s);
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
// ↑ / ↓ next to a value that missed its target (only once the day is judged)
const ARROW = e => e && e.ok===false && e.dir ? `<span class="dir" title="${e.dir==='over'?'Above':'Below'} target" aria-label="${e.dir==='over'?'above':'below'} target">${e.dir==='over'?'↑':'↓'}</span>` : '';
const api = p => fetch(p).then(r => { if(!r.ok) throw new Error(p+' '+r.status); return r.json(); });
const fmt = (v, d=0) => v==null ? '–' : Number(v).toLocaleString('en-GB',{maximumFractionDigits:d,minimumFractionDigits:d});
const fmtDate = s => new Date(s+'T00:00').toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'});
const shortDate = s => new Date(s+'T00:00').toLocaleDateString('en-GB',{day:'numeric',month:'short'});
const pace = s => `${Math.floor(s/60)}:${String(Math.round(s%60)).padStart(2,'0')}`;
const toSecs = t => { const p = String(t).split(':').map(Number); return p.length===3 ? p[0]*3600+p[1]*60+p[2] : p[0]*60+p[1]; };
let SUMMARY = [], charts = {};

/* ---------- theme: dark only (set on <html>) ---------- */

/* ---------- tabs ---------- */
document.querySelectorAll('nav button').forEach(b => b.onclick = () => showTab(b.dataset.tab));
function showTab(t){
  if(!document.getElementById('tab-'+t)) t = 'day';
  document.querySelectorAll('nav button').forEach(b => b.setAttribute('aria-selected', b.dataset.tab===t));
  document.querySelectorAll('main > section').forEach(s => s.hidden = s.id !== 'tab-'+t);
  placeSync(t);
  history.replaceState(null,'','#'+t);
  renderTab(t);
}
// On the Day tab the sync status sits at the right of the date row, so the header stays on one line;
// on other tabs it goes back to the header.
function placeSync(t){
  const s = document.getElementById('sync'), row = document.querySelector('#tab-day .daynav');
  const home = t === 'day' && row ? row : document.querySelector('header');
  if(s && s.parentNode !== home) home.appendChild(s);
}
function chart(id){
  const el = document.getElementById(id);
  if(charts[id]) charts[id].dispose();
  charts[id] = echarts.init(el, null, {renderer:'canvas'});
  return charts[id];
}
addEventListener('resize', () => Object.values(charts).forEach(c => c.resize()));
function theme(){
  return {ink:css('--ink'),muted:css('--muted'),rule:css('--rule'),accent:css('--accent'),good:css('--good'),bad:css('--bad'),
          warn:css('--warn'),soft:css('--accent-soft'),surface:css('--surface')};
}
// Requests that change something carry the per-start token the server wrote into this page (see server.py _write_ok).
let BK_TOKEN = (document.querySelector('meta[name="bk-token"]')||{}).content || '';
const post = async (url, body) => {
  const send = () => fetch(url, {method:'POST', headers:{'Content-Type':'application/json', 'X-BK-Token':BK_TOKEN}, body: JSON.stringify(body||{})});
  let r = await send();
  if(r.status === 403){   // the server restarted since this page loaded: fetch the new token and try once more
    const s = await fetch('/api/session', {cache:'no-store'}).then(x => x.json()).catch(() => null);
    if(s && s.token && s.token !== BK_TOKEN){ BK_TOKEN = s.token; r = await send(); }
  }
  return r;
};
const MOTION = !matchMedia('(prefers-reduced-motion: reduce)').matches;
const ring = c => ({borderColor:c.surface, borderWidth:2});
// 45° hatch: second encoding for "missed" so it never relies on red alone.
const _hatch = {};
function hatch(col, bg){
  const k = col+bg; if(_hatch[k]) return _hatch[k];
  const cv = document.createElement('canvas'), r = window.devicePixelRatio||1, n = 8*r; cv.width = cv.height = n;
  const g = cv.getContext('2d'); g.fillStyle = col; g.fillRect(0,0,n,n);
  g.strokeStyle = bg; g.globalAlpha = .45; g.lineWidth = 2*r;
  for(const o of [-n, 0, n]){ g.beginPath(); g.moveTo(o, n); g.lineTo(o+n, 0); g.stroke(); }
  return _hatch[k] = {image: cv, repeat: 'repeat'};
}
const statusFill = (c, ok, partial) => partial ? c.rule : ok===true ? c.good : ok===false ? hatch(c.bad, c.surface) : c.muted;
// Clean axis: round min/max out to a tidy step so labels read 0, 500, 1,000 rather than 2,939.
function niceRange(lo, hi, ticks=4, zero=false){
  if(zero) lo = 0;
  if(!isFinite(lo) || !isFinite(hi)) return {};
  if(hi <= lo){ hi = lo + 1; }
  const mag = Math.pow(10, Math.floor(Math.log10((hi - lo) / ticks)));
  const steps = [0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20].map(m => m*mag);
  const step = steps.find(st => Math.ceil(hi/st - 1e-9) - Math.floor(lo/st + 1e-9) <= ticks + 1) || steps[steps.length-1];
  return {min: zero ? 0 : Math.floor(lo/step + 1e-9)*step, max: Math.ceil(hi/step - 1e-9)*step, interval: step};
}
const tip = c => ({backgroundColor:c.surface,borderColor:c.rule,borderWidth:1,padding:[10,12],textStyle:{color:c.ink,fontSize:12.5,fontFamily:'Archivo'},extraCssText:'border-radius:10px;box-shadow:0 10px 30px rgba(15,25,40,.14);line-height:1.5'});

/* ---------- day ---------- */
const METRICS = [
  ['kcal','Calories','',0,'kcal'],
  ['protein_g','Protein','g',0,'protein_min'],
  ['carbs_g','Carbs','g',0,'carbs'],
  ['fat_g','Fat','g',0,'fat'],
  ['satfat_g','Saturated fat','g',1,'satfat_max'],
  ['fibre_g','Fibre','g',0,'fibre_min'],
];
function tgtText(key, t){
  const v = t[key];
  if(v==null) return 'no target';
  if(Array.isArray(v)) return `target ${fmt(v[0])}–${fmt(v[1])}`;
  if(key.endsWith('_min')) return `at least ${fmt(v)}`;
  if(key.endsWith('_max')) return `at most ${fmt(v)}`;
  return fmt(v);
}
function barPct(key, val, t){
  const v = t[key]; if(v==null||val==null) return 0;
  const ref = Array.isArray(v) ? v[1] : v;
  return Math.min(100, 100*val/(ref*1.25));
}
// live status against target: green on target, amber within 10% of it, red further off, grey no target
function liveStatus(key, val, t){
  const v = t[key]; if(v==null || val==null) return 'none';
  const lo = Array.isArray(v) ? v[0] : key.endsWith('_min') ? v : null;
  const hi = Array.isArray(v) ? v[1] : key.endsWith('_max') ? v : null;
  if((lo==null || val >= lo) && (hi==null || val <= hi)) return 'good';
  const miss = lo!=null && val < lo ? (lo - val) / lo : (val - hi) / hi;
  return miss <= 0.10 ? 'warn' : 'bad';
}
const LIVE_TITLE = {good:'On target', warn:'Within 10% of target', bad:'More than 10% off target', none:'No target'};
let currentDate = null;
async function renderDay(date){
  const dates = SUMMARY.map(d => d.date);
  date = date || dates[dates.length-1];
  currentDate = date;
  $('#pick').value = date; $('#pick').min = dates[0]; $('#pick').max = dates[dates.length-1];
  const [d, PC] = await Promise.all([api('/api/day?date='+date).catch(()=>null), api('/api/pace?date='+date).catch(()=>null)]);
  if(!d){ $('#day').innerHTML = `<h1>${fmtDate(date)}</h1><p class="empty">Nothing recorded for this date.</p>`; return; }
  const t = d.targets || {}, tot = d.totals || {}, ev = d.eval || {};
  const cls = k => ev[k] ? (ev[k].ok===true?'good':ev[k].ok===false?'bad':'') : '';
  let h = `<div class="day-head"><div><h1>${fmtDate(date)}</h1>
    <div><span class="chip">${esc(d.day_type||'rest')} day</span><span class="chip ${esc(d.status)}">${esc(d.status)}</span>${d.note?`<span class="sub">${esc(d.note)}</span>`:''}</div></div>
    <a id="hs-tile" class="hs-tile" href="#longevity" title="Health score: open the breakdown"></a></div><div id="nextmove"></div>`;
  if(d.totals){
    const live = PC && !PC.complete;   // in progress: colour by pace through the day, not by the full-day total
    const stat = (k,tk) => live && PC.macros[k] ? PC.macros[k].status : liveStatus(tk,tot[k],t);
    const ttl = (k,tk,dp,u) => { const m = live && PC.macros[k]; if(!m) return LIVE_TITLE[liveStatus(tk,tot[k],t)];
      const w = m.kind==='max' ? 'allowed' : 'expected';
      return `${m.status==='good'?'On pace':m.status==='warn'?'Behind pace':'Well off pace'}: ${fmt(m.eaten,dp)}${u} vs ${fmt(m.expected,dp)}${u} ${w} by ${esc(PC.now)}`; };
    const pw = (k,dp) => { const m = PC && PC.macros[k]; if(!m) return '';
      return `<div class="pw">${m.windows.map((w,i) => { const W = PC.windows[i];
        const st = w.state==='now' ? 'now lv-'+m.status : w.state==='later' ? 'later' : 'lv-'+w.state;
        const body = w.state==='later' ? `<b>${fmt(w.plan,dp)}</b>` : `<b>${fmt(w.eaten,dp)}</b><small>/${fmt(w.plan,dp)}</small>`;
        return `<span class="pw-s ${st}" title="${esc(W.name)} (${esc(W.from)}–${esc(W.until)}): ${w.state==='later'?'plan '+fmt(w.plan,dp):fmt(w.eaten,dp)+' eaten, plan '+fmt(w.plan,dp)}${m.kind==='max'?' (limit)':''}">${body}</span>`; }).join('')}</div>`; };
    h += `<div class="macros">` + METRICS.map(([k,lab,u,dp,tk]) =>
      `<div class="m"><div class="lab">${lab}</div>
        <div class="val-row"><div class="val lv-${stat(k,tk)}" title="${ttl(k,tk,dp,u)}">${fmt(tot[k],dp)}<small>${u}</small>${ARROW(ev[k])}</div>${k==='kcal'?'<div class="eb-side" id="kcal-eb"></div>':''}</div>
        <div class="tgt">${tgtText(tk,t)}</div>
        <div class="bar"><i class="lv-${stat(k,tk)}" style="width:${barPct(tk,tot[k],t)}%"></i></div>${pw(k,k==='satfat_g'?1:0)}</div>`).join('') + `</div>
      ${PC ? `<p class="sub pw-key">Under each macro: ${PC.windows.map(w=>`<span>${esc(w.name)} <small>${esc(w.from)}–${esc(w.until)}</small></span>`).join(' · ')}. Eaten / plan; what's left is re-spread over the windows still to come.${live?` Colours show pace at ${esc(PC.now)}.`:''}</p>`:''}
      <p class="sub daysub">${t.label?'Targets: '+esc(t.label)+'.':''}${d.status!=='complete'?' Not judged until the day is complete.':''}${tot.low_confidence_kcal_pct?` ${esc(tot.low_confidence_kcal_pct)}% of calories from guessed portions.`:''} Sodium ${fmt(tot.sodium_mg)} mg, caffeine ${fmt(tot.caffeine_mg)} mg.</p>`;
  } else h += `<p class="empty">No food logged.</p>`;

  // each number coloured by its share of the day's target: protein and fibre green (a big share helps),
  // calories, carbs, fat and saturated fat amber then red (a big share uses up the budget)
  const shareTd = (v, tk, dp, extra='') => {
    const T = t[tk], ref = T==null ? null : Array.isArray(T) ? T[1] : T, pc = ref && v ? 100*v/ref : 0;
    const goal = tk==='protein_min' || tk==='fibre_min', hi = tk==='satfat_max' ? [10,20] : goal ? [10,25] : [15,25];
    const c = !pc || pc < hi[0] ? '' : goal ? (pc >= hi[1] ? 'sh-g2' : 'sh-g1') : (pc >= hi[1] ? 'sh-b2' : 'sh-b1');
    return `<td class="${[extra,c].filter(Boolean).join(' ')}"${pc?` title="${Math.round(pc)}% of the day's ${goal?'target':'limit'}"`:''}>${fmt(v,dp)}</td>`; };
  let meals = '';
  for(const [meal, items] of Object.entries(d.meals||{})){
    if(!items || !items.length) continue;
    meals += `<div class="meal"><h3>${esc(meal[0].toUpperCase()+meal.slice(1))}</h3><table><tr><th>Item</th><th>kcal</th><th>Protein</th><th>Carbs</th><th>Fat</th><th>Sat</th><th>Fibre</th></tr>`;
    for(const it of items){
      const ps = it.parsed||[]; const sum = {k:0,p:0,c:0,f:0,sf:0,fib:0}; let low=false;
      ps.forEach(c => { for(const k in sum) sum[k]+= (c.macros||{})[k]||0; if(c.conf==='low') low=true; });
      const what = ps.filter(c=>c.item!=='creatine').map(c => `${esc(c.name)}${c.g!=null?` ${c.g}g`:c.ml!=null?` ${c.ml}ml`:c.n!=null?` ×${c.n}`:c.kcal!=null?` (${c.kcal} kcal)`:''}`).join(' + ');
      meals += `<tr><td>${it.time?`<span class="it-time">${esc(String(it.time).slice(0,5))}</span>`:''}${what||'<em>unresolved</em>'}<span class="raw">${esc(it.raw)}${it.after?` · after ${esc(it.after)}`:''}</span></td>
        ${shareTd(sum.k,'kcal',0,low?'low':'')}${shareTd(sum.p,'protein_min',1)}${shareTd(sum.c,'carbs',0)}${shareTd(sum.f,'fat',1)}${shareTd(sum.sf,'satfat_max',1)}${shareTd(sum.fib,'fibre_min',1)}</tr>`;
    }
    meals += `</table></div>`;
  }
  let side = `<h2>Training</h2>`;
  const ex = d.exercise||[];
  side += ex.length ? ex.map(e => {
    const bits = [];
    if(e.mode) bits.push(e.mode);
    if(e.distance_km) bits.push(`${esc(e.distance_km)} km`);
    if(e.distance_m) bits.push(`${esc(e.distance_m)} m`);
    if(e.time) bits.push(e.time);
    if(e.distance_km && e.time) bits.push(pace(toSecs(e.time)/e.distance_km)+'/km');
    if(e.duration_min) bits.push(`${esc(e.duration_min)} min`);
    if(e.hr&&e.hr.avg) bits.push(`HR ${esc(e.hr.avg)}${e.hr.max?'/'+e.hr.max:''}`);
    if(e.kcal&&e.kcal.total) bits.push(`${esc(e.kcal.total)} kcal`);
    if(e.load_kg) bits.push(`${esc(e.load_kg)} kg pack`);
    const lifts = (e.lifts||[]).map(l => { const pr = (d.prs||{})[l.ex];
      return `<tr${pr?' class="pr"':''}><td>${esc(l.ex.replace(/-/g,' '))}${pr?` <span class="pr-star" title="Personal best: ${esc(pr.kg)} kg${pr.reps?' × '+pr.reps:pr.metres?' for '+pr.metres+' m':''}" aria-label="personal best">★</span>`:''}${l.note?`<div class="lift-note">💬 ${esc(l.note)}</div>`:''}</td><td>${(l.sets||[]).map(x=>String(x).replace(/^0x/,'bw×')).join(', ')}</td></tr>`; }).join('');
    const nPr = (e.lifts||[]).filter(l => (d.prs||{})[l.ex]).length;
    return `<div class="session"><b>${esc(e.type)}${e.effort?', '+esc(e.effort):''}</b> <span class="sub">${bits.join(' · ')}${nPr?` · <span class="pr-star">★</span> ${nPr} personal best${nPr>1?'s':''}`:''}</span>${e.note?`<div class="sub">${esc(e.note)}</div>`:''}${coachList(e.coach)}${lifts?`<table>${lifts}</table>`:''}</div>`;
  }).join('') : `<p class="empty">No training recorded.</p>`;
  const kv = [];
  if(d.weight) kv.push(['Weight', `${esc(d.weight.kg)} kg${d.weight.fasted===false?' (not fasted)':''}${d.weight.bf_pct?`, ${esc(d.weight.bf_pct)}% fat`:''}`]);
  ((d.vitals||{}).bp||[]).forEach(b => kv.push([`BP ${b.time||''}`, `${esc(b.sys)}/${esc(b.dia)}${b.pulse?`, pulse ${esc(b.pulse)}`:''}`]));
  if(d.steps) kv.push(['Steps', fmt(d.steps)]);
  side += `<h2>Body</h2>` + (kv.length ? `<dl class="kv">${kv.map(([a,b])=>`<dt>${a}</dt><dd>${b}</dd>`).join('')}</dl>` : `<p class="empty">Nothing recorded.</p>`);
  h += `<div id="ready"></div><div id="daytl"></div><div id="glucose"></div><div class="notes-tasks"><div id="notes"></div><div id="tasks"></div></div>`;
  h += `<div class="cols"><div>${meals?'<h2>Food</h2><p class="sub sh-key">Numbers are coloured by their share of today\'s target: <span class="sh-g1">protein and fibre</span> greener as they fill more of it; <span class="sh-b1">calories, carbs, fat</span> and <span class="sh-b2">saturated fat</span> amber, then red, as they use up more of the limit. Hover a number for its %.</p>'+meals:''}</div><div>${side}</div></div>`;
  $('#day').innerHTML = h;
  renderNotes(date); renderTasks(); renderHsTile(); renderDayTimeline(date); renderGlucose(date); renderGlance(date); renderEnergyToday(date);
}
/* ---------- energy today, in the Calories box: deficit so far and for the day, from Garmin's burn ---------- */
async function renderEnergyToday(date){
  const E = await api('/api/energy?date='+date).catch(()=>null);
  const el = $('#kcal-eb'); if(date !== currentDate || !el) return;
  const t = E && E.today;
  if(!t || !t.available){ el.innerHTML = ''; return; }
  const bal = v => v >= 0 ? `${fmt(v)} deficit` : `${fmt(-v)} surplus`;
  const live = !t.complete && t.sync;
  const word = v => v >= 0 ? 'deficit' : 'surplus';
  if(!live){ el.innerHTML = `<span class="eb-h">${t.deficit_so_far >= 0 ? 'Deficit' : 'Surplus'}</span><span><b>${fmt(Math.abs(t.deficit_so_far))}</b> day</span><span>burnt ${fmt(t.burnt_so_far)}</span>`;
    el.title = "Garmin's total burn for the day minus what was eaten."; return; }
  const a = t.deficit_so_far, b = t.deficit_day;
  const head = a < 0 && b < 0 ? 'Surplus' : a >= 0 && b >= 0 ? 'Deficit' : 'Balance';
  const one = (v, lab) => `<span><b>${v < 0 && head === 'Balance' ? '+' : ''}${fmt(Math.abs(v))}</b> ${lab}</span>`;   // in a mixed column, + marks a surplus
  el.innerHTML = `<span class="eb-h">${head}</span>${one(a, 'now')}${one(b, 'day').replace('<b>', '<b>~')}`;
  el.title = `Now: burnt ${fmt(t.burnt_so_far)} kcal to ${t.sync} (last watch sync) minus ${fmt(t.eaten)} eaten.\n` +
    `Day: projected burn ${fmt(t.projected)} kcal by midnight (resting ${fmt(t.rest_of_day_resting)} + your usual ${fmt(t.rest_of_day_active||0)} active after ${t.sync}, median of ${t.typical_days} days) ` +
    `minus ${t.target_mid && t.target_mid > t.eaten ? 'your target, ' + fmt(t.target_mid) : 'what you\'ve eaten'} kcal.`;
}
/* ---------- next move + readiness strip ---------- */
async function renderGlance(date){
  const G = await api('/api/glance?date='+date).catch(()=>null);
  if(date !== currentDate || !G) return;
  const nm = $('#nextmove'), rd = $('#ready');
  if(nm) nm.innerHTML = G.move ? `<div class="nextmove nm-${esc(G.move.kind)}"><span class="nm-k">${G.move.text.startsWith('Day done')?'Verdict':'Next move'}</span>${esc(G.move.text)}</div>` : '';
  const R = G.ready;
  if(!rd) return;
  if(!R || !R.has_data){ rd.innerHTML = ''; return; }
  const vs = (v, b, unit, higherGood) => { if(v==null) return '<span class="rv">–</span>';
    if(b==null) return `<span class="rv">${v}<small>${unit}</small></span>`;
    const diff = v - b, good = higherGood ? diff >= 0 : diff <= 0, big = Math.abs(diff) >= (unit==='ms'?5:3);
    return `<span class="rv">${v}<small>${unit}</small></span><span class="rb ${big?(good?'good':'bad'):''}">${diff>0?'▲':diff<0?'▼':'▬'} vs ${b} normal</span>`; };
  const cells = [
    ['Sleep', R.sleep ? `<span class="rv">${R.sleep.replace('h','h ')}</span>${R.sleep_score?`<span class="rb ${R.sleep_score>=80?'good':R.sleep_score<60?'bad':''}">score ${esc(R.sleep_score)}</span>`:''}` : '<span class="rv">–</span><span class="rb">no sleep data</span>'],
    ['HRV', vs(R.hrv, R.hrv_base, 'ms', true)],
    ['Resting HR', vs(R.rhr, R.rhr_base, 'bpm', false)],
    ['Body battery', R.bb_now!=null ? `<span class="rv">${esc(R.bb_now)}</span><span class="rb">${R.bb_charge?`+${esc(R.bb_charge)} overnight`:R.bb_charge===0?'no overnight charge':'latest'}</span>` : R.bb_charge!=null ? `<span class="rv">+${esc(R.bb_charge)}</span><span class="rb">overnight</span>` : '<span class="rv">–</span>'],
  ];
  const sc = R.score!=null ? `<div class="rcell rscore r-${esc(R.band)}"><span class="rl">Readiness</span><span class="rv">${esc(R.score)}</span><span class="rb">${R.drivers&&R.drivers.length?'held back by '+R.drivers.map(k=>({rhr:'resting HR',hrv:'HRV',sleep_debt_h:'sleep debt',load:'training load',stress:'stress',bb:'body battery',feel:'how you feel'})[k]||k).join(', '):'nothing off'}</span></div>` : '';
  rd.innerHTML = `<div class="ready">${sc}${cells.map(([l,v])=>`<div class="rcell"><span class="rl">${l}</span>${v}</div>`).join('')}</div>`;
}
/* ---------- day timeline ---------- */
const TL_LANES = ['Sleep', 'Training', 'Food', 'Health'];
const TL_COL = {sleep:'#6250d6', sleep_deep:'#3d2fb0', sleep_light:'#7a6ae0', sleep_rem:'#b3a6ff', sleep_awake:'#5b6475',
  gym:'#2a78d6', run:'#eb6834', swim:'#1baf7a', ruck:'#eda100', yoga:'#e87ba4', walk:'#6250d6', other:'#008300', food:'#eda100', bp:'#e87ba4', symptom:'#C8372D', weight:'#2a78d6'};
const SF_HIGH = 3;   // a food item with this much saturated fat or more is tinted red on the timeline
const mmhm = m => `${String(Math.floor(((m%1440)+1440)%1440/60)).padStart(2,'0')}:${String(((m%60)+60)%60).padStart(2,'0')}`;
// value of a series at minute t: step = last point at or before t; otherwise linear between neighbours
const tlAt = (pts, t, step) => { if(!pts || !pts.length || t < pts[0][0]) return null;
  let i = 0; while(i+1 < pts.length && pts[i+1][0] <= t) i++;
  if(step || i+1 >= pts.length) return (step || t - pts[i][0] <= 20) ? pts[i][1] : null;
  const [x0,y0] = pts[i], [x1,y1] = pts[i+1]; return y0 + (y1-y0) * (t-x0) / ((x1-x0)||1); };
async function renderDayTimeline(date){
  const el = $('#daytl'); if(!el) return;
  const T = await api('/api/daytimeline?date='+date).catch(()=>null);
  if(date !== currentDate) return;
  const hasWatch = T && ((T.body_battery||[]).length || (T.steps||[]).length);
  if(!T || (!T.events.length && !hasWatch)){
    el.innerHTML = T && T.untimed ? `<div class="notes-h"><h2>Timeline</h2><span class="sub">${esc(T.untimed)} item${T.untimed!==1?'s':''} logged without a time</span></div>` : ''; return; }
  const c = theme(), P = T.protein, isToday = date === new Date(Date.now()+8*3600e3).toISOString().slice(0,10);
  const nowMin = isToday ? (()=>{ const n = new Date(Date.now()+8*3600e3); return n.getUTCHours()*60+n.getUTCMinutes(); })() : null;
  const lanes = TL_LANES.filter(l => T.events.some(e => e.lane === l));
  const LANE = 38, L = 92, R = 44;
  const panels = [];   // [key, height]
  const C = T.calories && ((T.calories.eaten||[]).length > 1 || (T.calories.burnt||[]).length > 1) ? T.calories : null;
  if(P) panels.push(['protein', 92]);
  if(C) panels.push(['calories', 92]);
  if(hasWatch) panels.push(['energy', 74]);
  if(lanes.length) panels.push(['lanes', lanes.length*LANE]);
  const G = T.glucose && T.glucose.readings.length ? T.glucose : null;
  const GP = G ? G.readings.map(([t,v]) => [+t.slice(0,2)*60 + +t.slice(3,5), v]) : [];
  if(G) panels.push(['glucose', 140]);
  const gap = 22; let top = 8; const grids = [], xA = [], yA = [], series = []; const hovers = {};
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11,fontFamily:'Archivo'},splitLine:{lineStyle:{color:c.rule,opacity:.4}}};
  const xBase = {type:'value',min:0,max:1440,interval:180,...ax,axisLabel:{...ax.axisLabel,formatter:v=>mmhm(v)}};
  const nowLine = nowMin!=null ? {silent:true,symbol:'none',label:{show:false},lineStyle:{color:c.accent,type:'solid',width:1.5,opacity:.7},data:[{xAxis:nowMin}]} : undefined;
  const titles = [];
  panels.forEach(([key, h], i) => {
    const last = i === panels.length-1;
    grids.push({left:L,right:R,top,height:h});
    xA.push({...xBase,gridIndex:i,axisLabel:{...xBase.axisLabel,show:last},axisTick:{show:last},splitLine:{show:true,lineStyle:{color:c.rule,opacity:.3}}});
    if(key==='protein'){
      const ymax = Math.max(P.target, ...P.points.map(p=>p[1])) * 1.1;
      yA.push({type:'value',gridIndex:i,min:0,max:ymax,interval:50,...ax,axisLabel:{...ax.axisLabel,showMaxLabel:false,formatter:v=>v+' g'}});
      titles.push({text:'Protein',top:top+h/2-8,left:6,textStyle:{color:c.ink,fontSize:12,fontWeight:600,fontFamily:'Archivo'}});
      const pts = P.points.slice(); const endX = nowMin!=null ? Math.max(nowMin, pts[pts.length-1][0]) : 1440;
      pts.push([endX, pts[pts.length-1][1]]);
      series.push({type:'line',name:'Protein so far',xAxisIndex:i,yAxisIndex:i,step:'end',data:pts,showSymbol:false,lineStyle:{color:c.good,width:2.5},
        areaStyle:{color:c.good,opacity:.12},markLine:nowLine,z:3});
      series.push({type:'line',name:'Pace',xAxisIndex:i,yAxisIndex:i,data:[[P.wake,0],[P.by,P.target],[1440,P.target]],showSymbol:false,
        lineStyle:{color:c.muted,width:1.5,type:'dashed'},tooltip:{show:false},
        markLine:{silent:true,symbol:'none',label:{show:true,position:'end',formatter:`${P.target} g`,color:c.muted,fontSize:10},lineStyle:{color:c.muted,opacity:.5,type:'dotted'},data:[{yAxis:P.target}]}});
    } else if(key==='calories'){
      const all = [...C.eaten, ...C.burnt].map(p=>p[1]);
      yA.push({type:'value',gridIndex:i,min:0,max:Math.max(500, ...all)*1.1,interval:Math.max(500, ...all)>2400?1000:500,...ax,axisLabel:{...ax.axisLabel,showMaxLabel:false,formatter:v=>v>=1000?(v/1000)+'k':v}});
      titles.push({text:'Calories',top:top+h/2-8,left:6,textStyle:{color:c.ink,fontSize:12,fontWeight:600,fontFamily:'Archivo'}});
      const ea = C.eaten.slice(); const eEnd = nowMin!=null ? Math.max(nowMin, ea[ea.length-1][0]) : 1440; ea.push([eEnd, ea[ea.length-1][1]]);
      series.push({type:'line',name:'Eaten',xAxisIndex:i,yAxisIndex:i,step:'end',data:ea,showSymbol:false,lineStyle:{color:TL_COL.food,width:2.5},z:3});
      const cut = C.estimated_after;
      const solid = cut!=null ? C.burnt.filter(p=>p[0]<=cut) : C.burnt, dash = cut!=null ? C.burnt.filter(p=>p[0]>=cut-15) : [];
      series.push({type:'line',name:'Burnt',xAxisIndex:i,yAxisIndex:i,data:solid,showSymbol:false,lineStyle:{color:'#eb6834',width:2,type:C.source==='garmin'?'solid':'dashed'},markLine:nowLine});
      if(dash.length) series.push({type:'line',name:'Burnt (estimated)',xAxisIndex:i,yAxisIndex:i,data:dash,showSymbol:false,lineStyle:{color:'#eb6834',width:2,type:'dashed',opacity:.8}});
    } else if(key==='energy'){
      yA.push({type:'value',gridIndex:i,min:0,max:100,interval:50,...ax,axisLabel:{...ax.axisLabel,formatter:v=>v}});
      const smax = Math.max(500, ...(T.steps||[]).map(s=>s[1]));
      yA.push({type:'value',gridIndex:i,min:0,max:smax,show:false});
      titles.push({text:'Energy',top:top+h/2-8,left:6,textStyle:{color:c.ink,fontSize:12,fontWeight:600,fontFamily:'Archivo'}});
      series.push({type:'bar',name:'Steps',xAxisIndex:i,yAxisIndex:yA.length-1,data:(T.steps||[]).map(([m,v])=>[m+7.5,v]),barWidth:'60%',
        itemStyle:{color:c.accent,opacity:.35},barMaxWidth:6,z:1});
      series.push({type:'line',name:'Body battery',xAxisIndex:i,yAxisIndex:yA.length-2,data:T.body_battery||[],showSymbol:false,smooth:.2,
        lineStyle:{color:'#1baf7a',width:2},areaStyle:{color:'#1baf7a',opacity:.10},markLine:nowLine,z:3});
    } else if(key==='glucose'){
      const [lo, hi] = G.range, gmax = Math.max(9, Math.ceil(Math.max(...GP.map(p=>p[1])) + 0.5));
      yA.push({type:'value',gridIndex:i,min:3,max:gmax,interval:2,...ax,axisLabel:{...ax.axisLabel,showMaxLabel:false}});
      const yi = yA.length-1;
      titles.push({text:'Glucose',top:top+h/2-16,left:6,textStyle:{color:c.ink,fontSize:12,fontWeight:600,fontFamily:'Archivo'},subtext:'mmol/L',subtextStyle:{color:c.muted,fontSize:10}});
      series.push({type:'line',name:'Glucose',xAxisIndex:i,yAxisIndex:yi,data:GP,showSymbol:false,smooth:.3,lineStyle:{color:c.accent,width:2},z:3,markLine:nowLine,
        markArea:{silent:true,label:{show:false},data:[[{yAxis:lo,itemStyle:{color:c.good,opacity:.08}},{yAxis:hi}]]}});
      // one dot on the curve per mealtime, sized by its carbs
      const eats = [];
      T.events.filter(e => e.kind==='food').forEach(e => { const prev = eats.find(x => x.start===e.start);
        if(prev){ prev.items.push(e); prev.carbs += e.carbs||0; } else eats.push({start:e.start, meal:e.meal, approx:e.approx, carbs:e.carbs||0, items:[e]}); });
      series.push({type:'scatter',name:'Meal on glucose',xAxisIndex:i,yAxisIndex:yi,z:21,
        data:eats.map(m => ({value:[m.start, tlAt(GP, m.start, false) ?? tlAt(GP, m.start, true)], eat:m})).filter(d => d.value[1]!=null)
          .map(d => ({...d, symbolSize:Math.max(8, Math.min(22, Math.sqrt(d.eat.carbs+4)*2.2)),
            itemStyle:{color:TL_COL.food,borderColor:c.surface,borderWidth:1.5,opacity:d.eat.approx?.7:1}}))});
    } else {
      yA.push({type:'category',gridIndex:i,data:lanes,inverse:true,...ax,axisTick:{show:false},splitLine:{show:true,lineStyle:{color:c.rule,opacity:.3}},axisLabel:{color:c.ink,fontSize:12,fontWeight:600,fontFamily:'Archivo'}});
      const yi = yA.length-1;
      const spans = T.events.filter(e => e.end != null), points = [];
      T.events.filter(e => e.end == null).forEach(e => {   // one dot per mealtime: items eaten together are summed
        const prev = e.kind==='food' && points.find(x => x.kind==='food' && x.start===e.start);
        if(prev){ prev.kcal = (prev.kcal||0)+(e.kcal||0); prev.satfat = Math.round(((prev.satfat||0)+(e.satfat||0))*10)/10; prev.approx = prev.approx && e.approx; }
        else points.push({...e}); });
      series.push({type:'custom',xAxisIndex:i,yAxisIndex:yi,name:'spans',
        renderItem:(p, api) => { const lane = api.value(0), s = api.coord([api.value(1), lane]), e = api.coord([api.value(2), lane]), hh = api.size([0,1])[1]*0.56;
          const ev = spans[p.dataIndex], w = Math.max(ev.kind.startsWith('sleep_') ? 1 : 3, e[0]-s[0]);
          const stage = ev.kind.startsWith('sleep_'), sh = stage ? hh * ({sleep_deep:1, sleep_light:.75, sleep_rem:.55, sleep_awake:.3})[ev.kind] : hh;
          const txt = !stage && w > 60 ? ev.label + (w > 150 && ev.detail ? ' · ' + ev.detail : '') : '';
          return {type:'group',children:[{type:'rect',shape:{x:s[0],y:s[1]+hh/2-sh,width:w,height:sh,r:stage?1:4},style:{fill:api.visual('color')}},
            {type:'text',style:{x:s[0]+6,y:s[1],text:txt,fill:'#fff',font:'600 11px Archivo',verticalAlign:'middle',width:w-10,overflow:'truncate'}}]}; },
        encode:{x:[1,2],y:0},
        data:spans.map(e => ({value:[lanes.indexOf(e.lane), e.start, e.end], ev:e, itemStyle:{color:TL_COL[e.kind]||c.accent}}))});
      series.push({type:'scatter',xAxisIndex:i,yAxisIndex:yi,name:'points',markLine:nowLine,
        data:points.map(e => ({value:[e.start, lanes.indexOf(e.lane)], ev:e,
          symbol:e.kind==='bp'?'diamond':e.kind==='symptom'?'triangle':e.kind==='weight'?'rect':'circle',
          symbolSize:e.kind==='food'?Math.max(9, Math.min(26, Math.sqrt(e.kcal||40)*1.3)):13,
          itemStyle:{color:e.kind==='food' && (e.satfat||0) >= SF_HIGH ? c.bad : TL_COL[e.kind]||c.accent,borderColor:c.surface,borderWidth:1.5,opacity:e.approx?.7:1}}))});
    }
    if(key !== 'lanes'){   // invisible 15-min strips so hovering anywhere in a line panel shows its values
      hovers[i] = key;
      const stop = nowMin!=null ? Math.ceil(nowMin/15)*15 : 1440;
      series.push({type:'custom',name:'hover',xAxisIndex:i,yAxisIndex:yA.length-1,z:20,
        renderItem:(p, api) => { const x0 = api.coord([api.value(0), 0])[0], x1 = api.coord([api.value(0)+15, 0])[0], cs = p.coordSys;
          return {type:'rect',shape:{x:x0,y:cs.y,width:Math.max(1,x1-x0),height:cs.height},style:{fill:'rgba(127,127,127,0.001)'},
            emphasis:{style:{fill:'rgba(127,127,127,0.12)'}}}; },
        encode:{x:0},data:Array.from({length:stop/15},(_,k)=>({value:[k*15], panel:key}))});
    }
    top += h + (last ? 0 : gap);
  });
  const H = top + 44;
  const notes = [T.untimed ? `${esc(T.untimed)} food item${T.untimed!==1?'s':''} without a time` : '', T.bp_untimed ? `${esc(T.bp_untimed)} BP reading${T.bp_untimed!==1?'s':''} without a time` : ''].filter(Boolean);
  const key = [P ? `<span class="k"><i style="background:${c.good}"></i>protein so far</span><span class="k"><i class="dash"></i>pace to ${esc(P.target)} g by 21:00</span>` : '',
    lanes.includes('Food') ? `<span class="k"><i class="dot" style="background:${c.bad}"></i>food with ${SF_HIGH} g+ saturated fat</span>` : '',
    C ? `<span class="k"><i style="background:${TL_COL.food}"></i>eaten ${fmt(C.eaten_now)}</span><span class="k"><i style="background:#eb6834"></i>burnt ${fmt(C.burnt_now)}${C.source!=='garmin'?' (estimated, no watch data)':C.estimated_after!=null?` (Garmin to ${mmhm(C.sync)}, estimated after)`:' (Garmin)'}</span><span class="k"><b style="color:${C.eaten_now-C.burnt_now>=0?c.good:c.warn}">${C.eaten_now-C.burnt_now>=0?'+':''}${fmt(C.eaten_now-C.burnt_now)} kcal</b>&nbsp;${isToday?'so far':'for the day'}</span>` : '',
    hasWatch ? `<span class="k"><i style="background:#1baf7a"></i>body battery</span><span class="k"><i style="background:${c.accent};opacity:.4"></i>steps</span>` : '',
    G ? `<span class="k"><i style="background:${c.accent}"></i>glucose</span><span class="k"><i class="dot" style="background:${TL_COL.food}"></i>meal, sized by carbs</span><span class="k"><i style="background:${c.good};opacity:.35"></i>range ${G.range[0]}–${G.range[1]}</span>` : ''].join('');
  el.innerHTML = `<div class="notes-h"><h2>Timeline</h2><span class="sub">${notes.join(' · ') || 'everything logged, at its time'}</span></div><div class="tl-key">${key}</div><div id="tlday" class="chart" style="height:${H}px"></div>`;
  chart('tlday').setOption({animation:MOTION,textStyle:{fontFamily:'Archivo'},title:titles,grid:grids,xAxis:xA,yAxis:yA,series,
    axisPointer:{link:[{xAxisIndex:'all'}]},
    tooltip:{trigger:'item',...tip(c),formatter:p => {
      if(p.seriesName==='hover'){
        const t = p.value[0] + 7.5, k = p.data.panel, head = `<b>${mmhm(p.value[0])}–${mmhm(p.value[0]+15)}</b>`, mu = s => `<span style="color:${c.muted}">${s}</span>`;
        if(k==='protein'){ const so = tlAt(P.points, t, true), pace = t < P.wake ? 0 : t >= P.by ? P.target : P.target*(t-P.wake)/(P.by-P.wake);
          return `${head}<br>Protein so far <b>${fmt(so??0)} g</b><br>${mu(`On pace: ${fmt(pace)} g`)}${so!=null?`<br>${mu(so>=pace?`${fmt(so-pace)} g ahead`:`${fmt(pace-so)} g behind`)}`:''}`; }
        if(k==='calories'){ const e = tlAt(C.eaten, t, true), b = tlAt(C.burnt, t, false);
          const est = C.source!=='garmin' || (C.estimated_after!=null && t > C.estimated_after);
          return `${head}<br>Eaten <b>${fmt(e??0)}</b> kcal<br>Burnt <b>${b!=null?fmt(b):'–'}</b> kcal${est?mu(' (estimated)'):''}${b!=null?`<br>${mu(`Balance ${(e??0)-b>=0?'+':''}${fmt((e??0)-b)} kcal`)}`:''}`; }
        if(k==='energy'){ const bb = tlAt(T.body_battery, t, false), st = (T.steps||[]).find(x => x[0] <= p.value[0] && p.value[0] < x[0]+15);
          const cum = (T.steps||[]).filter(x => x[0] <= p.value[0]).reduce((a,x) => a + x[1], 0);
          return `${head}<br>Body battery <b>${bb!=null?Math.round(bb):'–'}</b><br>Steps <b>${st?fmt(st[1]):0}</b> <span style="color:${c.muted}">· ${fmt(cum)} for the day so far</span>`; }
        if(k==='glucose'){ const g = tlAt(GP, t, false);
          return `${head}<br>Glucose <b>${g!=null?fmt(g,1):'–'}</b> mmol/L${g!=null&&(g<G.range[0]||g>G.range[1])?mu(' (out of range)'):''}`; }
        return '';
      }
      if(p.seriesName==='Glucose') return `${mmhm(p.value[0])} · glucose <b>${fmt(p.value[1],1)}</b> mmol/L`;
      if(p.seriesName==='Meal on glucose'){ const m = p.data.eat, r = (G.meals||[]).find(x => !x.pending && x.time===mmhm(m.start));
        return `<b>${mmhm(m.start)}</b>${m.approx?' (about)':''} · ${esc(m.meal)} · <b>${fmt(m.carbs,0)} g</b> carbs<br>${m.items.map(x => `${esc(x.label)} <span style="color:${c.muted}">${fmt(x.carbs||0,0)} g carbs</span>`).join('<br>')}`
          + (r ? `<br>Glucose ${fmt(r.base,1)} → ${fmt(r.peak,1)} <b>(${r.rise>=0?'+':''}${fmt(r.rise,1)})</b> <span style="color:${c.muted}">peak at ${esc(r.peak_min)} min${r.back_min!=null?`, back down at ${esc(r.back_min)} min`:''}</span>` : ''); }
      if(p.seriesName==='Protein so far') return `${mmhm(p.value[0])} · <b>${fmt(p.value[1],0)} g</b> protein so far`;
      if(p.seriesName==='Eaten') return `${mmhm(p.value[0])} · <b>${fmt(p.value[1])}</b> kcal eaten so far`;
      if(p.seriesName.startsWith('Burnt')) return `${mmhm(p.value[0])} · <b>${fmt(p.value[1])}</b> kcal burnt so far${p.seriesName.includes('est')||C.source!=='garmin'?' (estimated)':''}`;
      if(p.seriesName==='Body battery') return `${mmhm(p.value[0])} · body battery <b>${p.value[1]}</b>`;
      if(p.seriesName==='Steps') return `${mmhm(p.value[0]-7.5)}–${mmhm(p.value[0]+7.5)} · <b>${fmt(p.value[1])}</b> steps`;
      const e = p.data && p.data.ev; if(!e) return '';
      const same = e.kind==='food' ? T.events.filter(x => x.kind==='food' && x.start===e.start) : [e];
      if(e.kind==='food') return `<b>${mmhm(e.start)}</b>${e.approx?' (about)':''} · ${esc(e.meal)}<br>${same.map(x => `${esc(x.label)} <span style="color:${c.muted}">${esc(x.kcal)} kcal, ${esc(x.protein)} g protein, ${x.satfat||0} g sat fat</span>`).join('<br>')}`;
      return `<b>${mmhm(e.start)}${e.end!=null?'–'+mmhm(e.end):''}</b> · ${esc(e.label)}${e.detail?`<br><span style="color:${c.muted}">${esc(e.detail)}</span>`:''}`; }}});
}

/* ---------- glucose (FreeStyle Libre) ---------- */
async function renderGlucose(date){
  const el = $('#glucose'); if(!el) return;
  const G = await api('/api/glucose?date='+date).catch(()=>null);
  if(date !== currentDate) return;
  if(!G || !G.readings.length){ el.innerHTML = ''; return; }
  const c = theme(), s = G.stats, [lo, hi] = G.range;
  const chip = (lab, v, cls='') => `<span class="g-chip ${cls}"><small>${lab}</small> <b>${v}</b></span>`;
  el.innerHTML = `<div class="notes-h"><h3 class="g-h3" style="margin:0">Glucose</h3><span class="sub">FreeStyle Libre · mmol/L${G.settling?' · <b>sensor settling in</b>: first-day readings run a little off':''}</span></div>
    ${(()=>{ const L = G.readings[G.readings.length-1]; return `<div class="g-chips">${chip('latest', `${fmt(L[1],1)} <small>at ${L[0]}</small>`, L[1]>hi||L[1]<lo?'bad':'')}${s?'':chip('readings', `${G.readings.length} <small>· stats after ~2 h</small>`)}</div>`; })()}
    ${s?`<div class="g-chips">${chip('average', fmt(s.mean,1))}${chip('in range 3.9–7.8', fmt(s.tir,0)+'%', s.tir>=95?'good':s.tir<85?'bad':'')}${chip('variability (CV)', fmt(s.cv,0)+'%', s.cv<=18?'good':s.cv>25?'bad':'')}${chip('high / low', `${fmt(s.max,1)} / ${fmt(s.min,1)}`)}${s.overnight?chip('overnight 3–6am', fmt(s.overnight,1)):''}</div>`:''}
    ${G.meals.length?`<table class="g-meals"><tr><th>Meal</th><th class="num">Before</th><th class="num">Peak</th><th class="num">Rise</th><th class="num">Peak at</th><th class="num">Back down</th></tr>${G.meals.map(m => m.pending
      ? `<tr><td>${esc(m.time)} ${esc(m.meal)}<br><span class="sub">${esc(m.label)}</span></td><td colspan="5" class="sub">${esc(m.why||'waiting for 2 hours of readings')}</td></tr>`
      : `<tr><td>${esc(m.time)} ${esc(m.meal)}<br><span class="sub">${esc(m.label)}</span></td><td class="num">${fmt(m.base,1)}</td><td class="num">${fmt(m.peak,1)}</td>
         <td class="num ${m.rise>=3?'bad':m.rise<=1.5?'good':''}"><b>${m.rise>=0?'+':''}${fmt(m.rise,1)}</b></td><td class="num">${esc(m.peak_min)} min</td><td class="num">${m.back_min!=null?m.back_min+' min':'>2½ h'}</td></tr>`).join('')}</table>`
      : `<p class="sub">Add a time to meals when you log them (e.g. "L 13:10: rice 102, beef 125") to see each meal's spike here.</p>`}`;
}

/* ---------- health score ---------- */
let HS = null;
const hsGet = async () => HS = HS || await api('/api/healthscore').catch(()=>null);
const hsFmtV = v => v==null ? '–' : (typeof v === 'number' ? fmt(v, Math.abs(v) < 10 && v % 1 ? 2 : v % 1 ? 1 : 0) : v);
const hsDelta = (d, lab) => d ? `<span class="hs-d ${d.change>0.4?'up':d.change<-0.4?'down':''}" tabindex="0">${d.change>0.4?'▲':d.change<-0.4?'▼':'▬'} ${d.change>0?'+':''}${fmt(d.change,1)} <small>${lab}</small><span class="hs-tip" role="tooltip"><b>Since ${shortDate(d.date_from)}</b>: ${fmt(d.from,1)} → ${fmt(d.from+d.change,1)}${d.coverage_from<0.5?' (fewer inputs then)':''}
  ${(d.drivers||[]).length ? `<table>${d.drivers.map(x => `<tr><td class="${x.change>0?'good':'bad'}">${x.change>0?'+':''}${fmt(x.change,1)}</td><td>${esc(x.name)}<br><span>${x.why ? x.why : `${hsFmtV(x.from)} → ${hsFmtV(x.to)}`} · ${esc(x.domain)}</span></td></tr>`).join('')}</table>` : '<br><span>No single input moved much; small changes across several.</span>'}</span></span>`
                                : `<span class="hs-d none" title="Not enough history yet"><small>${lab}</small> –</span>`;
// "% measured", with a hover list of what's left to measure, biggest share of the score first
const hsCov = H => { const L = H.to_measure || [], pct = `${Math.round(H.coverage*100)}% measured`;
  if(!L.length) return pct;
  return `<span class="hs-d" tabindex="0">${pct} <small>· ${L.length} to go</small><span class="hs-tip" role="tooltip"><b>Still to measure</b>, biggest share of the score first. Each counts as average (50) until measured.
    <table>${L.map(x => `<tr><td>${fmt(x.share,1)}%</td><td>${esc(x.name)}<br><span>${esc(x.domain)}${x.last?` · last ${shortDate(x.last)}, now out of date`:''}</span></td></tr>`).join('')}</table></span></span>`; };
async function renderHsTile(){
  const el = $('#hs-tile'); if(!el) return;
  const H = await hsGet(); if(!H || H.score==null){ el.remove(); return; }
  el.innerHTML = `<div class="hs-lab">Health score <small>vs athlete</small></div><div class="hs-row"><div class="hs-num">${fmt(H.score,0)}</div>
    <div class="hs-ds">${hsDelta(H.delta.week,'7 days')}${hsDelta(H.delta.month,'30 days')}${hsDelta(H.delta.year,'year')}</div></div>
    <div class="hs-cov">${hsCov(H)}</div>`;
  el.onclick = e => { e.preventDefault(); showTab('longevity'); };
}
function hsPanel(H){
  const c = theme();
  const bar = d => `<div class="hs-dom" role="button" tabindex="0" data-dom="${esc(d.key)}" title="Show what makes up ${esc(d.label)}"><span class="nm">${esc(d.label)} <small>${esc(d.weight)}%</small></span>
    <span class="tr"><i style="width:${d.score??0}%;background:${d.score==null?c.rule:d.score>=80?c.good:d.score>=55?c.warn:c.bad}"></i></span>
    <span class="v">${d.score==null?'no data':fmt(d.score,0)}</span><span class="cv">${Math.round(d.coverage*100)}% measured</span></div>`;
  const a = H.ages, age = (v, lab, why) => `<div class="hs-age"><div class="lab">${lab}</div><div class="big">${v??'–'}</div><div class="sub">${why}</div></div>`;
  return `<div class="hs-panel"><div class="hs-left">
      <div class="lab">Health score · vs ${athleteWho(H)} athlete</div><div class="hs-big">${fmt(H.score,0)}<small>/100</small></div>
      <div class="hs-ds">${hsDelta(H.delta.week,'7 days')}${hsDelta(H.delta.month,'30 days')}${hsDelta(H.delta.year,'year')}</div>
      <div class="sub">${Math.round(H.coverage*100)}% measured. Counted as average until measured: ${esc(H.missing.slice(0,6).join(', '))}${H.missing.length>6?` and ${H.missing.length-6} more`:''}.</div>
      <div class="hs-ages">${age(a.actual,'Your age','')}${age(a.fitness_age?fmt(a.fitness_age.age,1):null,'Fitness age', a.fitness_age?`Garmin, ${shortDate(a.fitness_age.date)}${a.fitness_age.achievable?` · could reach ${fmt(a.fitness_age.achievable,1)}`:''}`:'from Garmin at the next sync')}${age(a.phenoage.age!=null?fmt(a.phenoage.age,1):null,'PhenoAge', a.phenoage.age!=null?'from blood tests':`needs ${esc(a.phenoage.missing)} more blood markers`)}</div>
    </div><div class="hs-right"><div id="hschart" class="chart" style="height:170px"></div>${H.domains.map(bar).join('')}
      <p class="sub"><b>Biggest drags:</b> ${H.drags.map(d=>`${esc(d.name)} (−${fmt(d.cost,1)})`).join(', ')}.</p></div></div>
    <p class="disclaimer">100 = a fit, athletic ${athleteWho(H, true)}; 50 = a typical one. Unmeasured markers count as 50. Weighted toward fitness and strength because they predict long-term health most strongly. The reference points (athlete.yaml) and weights are a judgement from published norms, not a validated model: use it to track your own change over time.</p>`;
}
function hsChart(id, H, events){
  const c = theme(), ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule,opacity:.5}}};
  const col = k => (TL_KIND[k]||[])[1] || c.muted;
  chart(id).setOption({animation:MOTION,textStyle:{fontFamily:'Archivo'},grid:{left:40,right:16,top:12,bottom:24},
    xAxis:{type:'time',...ax,splitLine:{show:false},axisLabel:{...ax.axisLabel,hideOverlap:true,formatter:v=>new Date(v).toLocaleDateString('en-GB',{day:'numeric',month:'short'})}},
    yAxis:{type:'value',min:v=>Math.max(0,Math.floor((v.min-5)/10)*10),max:100,...ax},
    tooltip:{trigger:'axis',...tip(c),formatter:ps=>{ const p = ps[0].value; return `<b>${fmtDate(String(p[0]).slice(0,10))}</b><br>Health score ${fmt(p[1],0)}<br><span style="color:${c.muted}">${Math.round(p[2]*100)}% measured</span>${(events||[]).filter(e=>e.date===String(p[0]).slice(0,10)).map(e=>`<br>● ${esc(e.what)}`).join('')}`; }},
    series:[{type:'line',data:H.history,showSymbol:false,smooth:.2,lineStyle:{color:c.accent,width:2},areaStyle:{color:c.soft,opacity:.5},
      markLine: events ? {symbol:'none',silent:true,label:{show:false},data:events.filter(e=>e.kind!=='episode'&&e.date>=H.history[0][0]).map(e=>({xAxis:e.date,lineStyle:{color:col(e.kind),width:1,type:e.kind==='target'?'dashed':'solid'}}))} : undefined}]});
}

function openDomain(key){
  const d = (HS?.domains||[]).find(x => x.key === key); if(!d) return;
  const c = theme(), by = Object.fromEntries((LV_DATA?.markers||[]).map(m => [m.id, m]));
  const sw = d.markers.reduce((a,p) => a + p.weight, 0);
  const col = s => s==null ? c.rule : s>=80 ? c.good : s>=40 ? c.warn : c.bad;
  const dp = v => Math.abs(v)<10 && !Number.isInteger(v) ? 2 : Math.abs(v)<100 && !Number.isInteger(v) ? 1 : 0;
  const how = {lab:'blood test', inbody:'InBody scan', manual:'your own test', garmin:'the watch', derived:'your logs'};
  const rows = [...d.markers].sort((a,b) => (a.score==null) - (b.score==null) || b.weight - a.weight).map(p => {
    const m = by[p.id] || {}, share = Math.round(p.weight / sw * 100);
    const pts = p.used * p.weight / sw, r = p.ref, f = v => v==null ? '–' : fmt(v, dp(v));
    return `<tr class="${p.score==null?'miss':''}" data-mk="${esc(p.id)}" tabindex="0" title="Open ${esc(p.name)} history">
      <td><b>${esc(p.name)}</b>${m.source?`<br><span class="sub">from ${how[m.source]||m.source}</span>`:''}</td>
      <td class="num">${p.value==null?'<span class="sub">not measured</span>':`${fmt(p.value, dp(p.value))} <span class="sub">${m.unit||''}</span>`}${p.date?`<br><span class="sub">${shortDate(p.date)}</span>`:''}</td>
      <td class="num">${r?f(r.top):'–'}</td><td class="num">${r?f(r.avg):'–'}</td>
      <td class="sc">${p.assumed?`<span class="sub">50 assumed</span>`:`<span class="hs-mini"><i style="width:${esc(p.score)}%;background:${col(p.score)}"></i></span> ${fmt(p.score,0)}`}</td>
      <td class="num">${share}%</td><td class="num">${fmt(pts,1)}</td></tr>`;
  }).join('');
  $('#mk-body').innerHTML = `<div class="mk-h"><div><h2 id="mk-title">${esc(d.label)}</h2>
      <div class="sub">${esc(d.weight)}% of your health score · ${Math.round(d.coverage*100)}% measured</div></div><button class="mk-x" aria-label="Close">✕</button></div>
    <div class="mk-now">${d.score==null?'<span class="empty-v">No data yet</span>':`<b style="font-size:34px">${fmt(d.score,0)}</b><span class="sub">/100</span>`}</div>
    <table class="hs-tbl"><tr><th>Marker</th><th class="num">Latest</th><th class="num">Athlete</th><th class="num">Average</th><th>Score</th><th class="num">Weight</th><th class="num">Points</th></tr>${rows}</table>
    <p class="sub">Scored against a fit, athletic ${athleteWho(HS, true)}: 100 at athlete level, 50 at a typical ${athleteWho(HS)}, 0 at poor, straight-line in between. Markers you haven't measured count as 50 (average) until you do. Points add up to the area's score. Lab results count for 400 days, watch and log data for 21. Click a marker for its history.</p>`;
  const dlg = $('#mk-dlg'); if(!dlg.open) dlg.showModal();
  $('#mk-body .mk-x').onclick = () => dlg.close();
  dlg.onclick = e => { if(e.target === dlg) dlg.close(); };
  document.querySelectorAll('#mk-body tr[data-mk]').forEach(r => { r.onclick = () => openMarker(r.dataset.mk); r.onkeydown = e => { if(e.key==='Enter') openMarker(r.dataset.mk); }; });
}

/* ---------- your tasks (todo.yaml) ---------- */
let SHOW_DONE = false;
const TASK_OPEN = new Set(), JUST_DONE = {};   // expanded items; items ticked in the last few seconds (undo window)
const UNDO_MS = 8000;
const esc = s => String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
const PRI = {high:0, normal:1, low:2};
async function toggleTask(id){
  const r = await post('/api/todo/toggle?id='+encodeURIComponent(id)).catch(()=>null);
  if(!r || !r.ok){ toast('todo:'+Date.now(), 'err', 'Could not update that task', 'Restart the dashboard service if this keeps happening.'); return null; }
  return r.json();
}
async function renderTasks(){
  const el = $('#tasks'); if(!el) return;
  const all = await api('/api/todo').catch(()=>null);
  if(!all){ el.innerHTML = `<div class="notes-h"><h2>For you to do</h2></div><p class="empty">Couldn’t load the list. The dashboard service needs a restart to pick up new code.</p>`; return; }
  const now = Date.now(), recent = t => t.done && JUST_DONE[t.id] && now - JUST_DONE[t.id] < UNDO_MS;
  const open = all.filter(t => !t.done || recent(t)).sort((a,b) => (PRI[a.priority]??1)-(PRI[b.priority]??1));
  const done = all.filter(t => t.done && !recent(t));
  const row = t => { const ex = TASK_OPEN.has(t.id), jd = recent(t);
    return `<li class="${t.done?'done':''} p-${['high','normal','low'].includes(t.priority)?t.priority:'normal'} ${ex?'open':''}" data-id="${esc(t.id)}">
      <input type="checkbox" aria-label="Mark ${esc(t.title)} done" ${t.done?'checked':''}>
      <div class="tk"><button class="tt" aria-expanded="${ex}"><b>${esc(t.title)}</b>${t.priority==='high'&&!t.done?'<span class="tag">Priority</span>':''}${t.area?`<span class="area">${esc(t.area)}</span>`:''}<span class="chev">${ex?'▾':'▸'}</span></button>
        ${ex&&t.detail?`<span class="td">${esc(t.detail)}</span>`:''}${t.done_on&&!jd?`<span class="td">Done ${shortDate(t.done_on)}</span>`:''}</div>
      ${jd?`<button class="undo">Undo</button>`:''}</li>`; };
  el.innerHTML = `<div class="notes-h"><h2>For you to do</h2><span class="sub">${all.filter(t=>!t.done).length} open${done.length?` · <a href="#" id="tdone">${SHOW_DONE?'hide':'show'} ${done.length} done</a>`:''}</span></div>
    <div class="tscroll">${open.length ? `<ul class="tasks">${open.map(row).join('')}</ul>` : `<p class="empty">Nothing waiting on you.</p>`}
    ${SHOW_DONE && done.length ? `<ul class="tasks">${done.map(row).join('')}</ul>` : ''}</div>`;
  el.querySelectorAll('.tasks li').forEach(li => {
    const id = li.dataset.id;
    li.querySelector('.tt').onclick = () => { TASK_OPEN.has(id) ? TASK_OPEN.delete(id) : TASK_OPEN.add(id); renderTasks(); };
    const cb = li.querySelector('input[type=checkbox]');
    cb.onchange = async () => { cb.disabled = true; const r = await toggleTask(id);
      if(r && r.done){ JUST_DONE[id] = Date.now(); setTimeout(renderTasks, UNDO_MS + 50); } else delete JUST_DONE[id];
      renderTasks(); };
    const u = li.querySelector('.undo');
    if(u) u.onclick = async () => { u.disabled = true; delete JUST_DONE[id]; await toggleTask(id); renderTasks(); };
  });
  const td = $('#tdone'); if(td) td.onclick = e => { e.preventDefault(); SHOW_DONE = !SHOW_DONE; renderTasks(); };
}
// "a 45-year-old" / "45-year-old man", from athlete.yaml (age, sex)
const athleteWho = (H, noun) => { const a = (H && H.athlete) || {}, age = a.age || 45;
  return noun ? `${age}-year-old ${a.sex === 'female' ? 'woman' : a.sex === 'male' ? 'man' : 'adult'}` : `a ${age}-year-old`; };
const NOTE_IC = {good:'✓', bad:'!', info:'•'};
// Claude's comments on a workout (exercise entry `coach:`), same look as the day notes
const coachList = cs => cs && cs.length ? `<ul class="notes wo-coach">${cs.map(x => `<li class="n-${x.kind||'info'}"><span class="ic" role="img" aria-label="${NOTE_LABEL[x.kind||'info']}">${NOTE_IC[x.kind||'info']}</span><span>${esc(x.text)}<span class="who">from Claude</span></span></li>`).join('')}</ul>` : '';
const NOTE_LABEL = {good:'Win', bad:'Warning', info:'Observation'};
async function renderNotes(date){
  const notes = await api('/api/insights?date='+date).catch(()=>[]);
  if(date !== currentDate) return;   // user already moved to another day
  const el = $('#notes'); if(!el) return;
  if(!notes.length){ el.innerHTML = ''; return; }
  const n = k => notes.filter(x => x.kind===k).length;
  el.innerHTML = `<div class="notes-h"><h2>Notes</h2><span class="sub">${n('bad')} warning${n('bad')!==1?'s':''} · ${n('good')} win${n('good')!==1?'s':''} · ${n('info')} observation${n('info')!==1?'s':''}</span></div>
    <ul class="notes${notes.length>3?' capped':''}">${notes.map(x => `<li class="n-${esc(x.kind)}"><span class="ic" role="img" aria-label="${NOTE_LABEL[x.kind]}">${NOTE_IC[x.kind]}</span><span>${esc(x.text)}${x.coach?'<span class="who">from Claude</span>':''}</span></li>`).join('')}</ul>${notes.length>3?`<button class="linkbtn" id="notes-more">Show ${notes.length-3} more</button>`:''}`;
  const more = $('#notes-more'); if(more) more.addEventListener('click', () => { const ul = more.previousElementSibling; ul.classList.toggle('capped'); more.textContent = ul.classList.contains('capped') ? `Show ${notes.length-3} more` : 'Show fewer'; });
}
function step(n){ const ds = SUMMARY.map(d=>d.date); const i = ds.indexOf(currentDate)+n; if(i>=0&&i<ds.length) renderDay(ds[i]); }
$('#prev').onclick = () => step(-1); $('#next').onclick = () => step(1);
$('#latest').onclick = () => renderDay(); $('#pick').onchange = e => renderDay(e.target.value);
addEventListener('keydown', e => { if($('#tab-day').hidden || e.target.tagName==='INPUT' || e.target.tagName==='SELECT') return; if(e.key==='ArrowLeft') step(-1); if(e.key==='ArrowRight') step(1); });

/* ---------- longevity ---------- */
const ST_IC = {green:'✓', amber:'!', red:'✕', grey:'–'};
const ST_LABEL = {green:'On target', amber:'Near', red:'Off target', grey:'No data'};
function zoneBar(m){
  if(m.value==null || m.bands==='none' || m.bands==='lab' && !m.lab_ref) return '';
  const g = m.bands==='lab' ? m.lab_ref : m.green, a = m.bands==='lab' ? null : m.amber, c = m.contested;
  const nums = [m.value, ...(g||[]), ...(a||[]), ...(c||[])].filter(v => v!=null && isFinite(v));
  let lo = Math.min(...nums), hi = Math.max(...nums); const pad = (hi-lo||Math.abs(hi)||1)*.25; lo -= pad; hi += pad;
  if(lo < 0 && Math.min(...nums) >= 0) lo = 0;
  const pc = v => Math.max(0, Math.min(100, (v-lo)/(hi-lo)*100));
  const seg = (b, cls) => b ? `<div class="${cls}" style="left:${pc(b[0]??lo)}%;width:${pc(b[1]??hi)-pc(b[0]??lo)}%"></div>` : '';
  return `<div class="zone" title="Green: target. Amber: near. Red: off target.${c?' Dashed: contested optimal range.':''}">${seg(a,'a')}${seg(g,'g')}${c?seg(c,'c'):''}<div class="mk" style="left:${pc(m.value)}%"></div></div>`;
}
function sparkline(h){
  if(!h || h.length < 2) return '';
  const vs = h.map(p => p[1]), lo = Math.min(...vs), hi = Math.max(...vs), r = hi-lo || 1;
  const t0 = new Date(h[0][0]).getTime(), t1 = new Date(h[h.length-1][0]).getTime(), rt = t1-t0 || 1;
  const pts = h.map(p => `${((new Date(p[0]).getTime()-t0)/rt*100).toFixed(1)},${(26-(p[1]-lo)/r*22).toFixed(1)}`).join(' ');
  const [lx, ly] = pts.split(' ').pop().split(',');
  return `<svg class="spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.5" vector-effect="non-scaling-stroke" style="color:var(--accent)"/><circle cx="${lx}" cy="${ly}" r="2.2" fill="var(--accent)"/></svg>`;
}
function trend(m){
  const h = m.history || []; if(h.length < 2) return '';
  const last = h[h.length-1], t = new Date(last[0]).getTime() - 28*864e5;
  const prev = [...h].reverse().find(p => new Date(p[0]).getTime() <= t) || h[0];
  const d = last[1] - prev[1]; if(Math.abs(d) < 1e-9) return '→ flat';
  const dp = Math.abs(d) >= 10 ? 0 : Math.abs(d) >= 1 ? 1 : 2;
  return `${d>0?'↑':'↓'} ${d>0?'+':''}${fmt(d,dp)} since ${shortDate(prev[0])}`;
}
function rangeText(b, unit){
  if(!b) return null;
  const u = unit ? ` ${unit}` : '', f = v => fmt(v, Math.abs(v) < 10 && !Number.isInteger(v) ? 2 : Math.abs(v) < 100 && !Number.isInteger(v) ? 1 : 0);
  if(b[0] != null && b[1] != null) return `${f(b[0])}–${f(b[1])}${u}`;
  if(b[0] != null) return `≥ ${f(b[0])}${u}`;
  if(b[1] != null) return `< ${f(b[1])}${u}`;
  return null;
}
function targetLine(m){
  if(m.bands === 'none') return '<div class="tgtline">No target: tracked for its trend</div>';
  if(m.bands === 'lab'){
    const r = m.lab_ref ? rangeText(m.lab_ref, m.unit) : null;
    return `<div class="tgtline">${r ? `Good: <b>${r}</b> <span class="sub">(lab reference range)</span>` : 'Good: within the lab’s reference range'}${m.contested ? ` · optimal <b>${rangeText(m.contested, m.unit)}</b> <span class="sub">(contested)</span>` : ''}</div>`;
  }
  const g = rangeText(m.green, m.unit), a = rangeText(m.amber, m.unit);
  if(!g) return '';
  return `<div class="tgtline">Good: <b>${g}</b>${a ? ` <span class="sub">· near ${a}</span>` : ''}${m.contested ? ` · optimal <b>${rangeText(m.contested, m.unit)}</b> <span class="sub">(contested)</span>` : ''}</div>`;
}
function tile(m, lever){
  const val = m.value==null ? `<div class="empty-v">${m.source==='lab'?'Needs a blood test':m.source==='manual'?'Not tested yet':m.source==='inbody'?'No scan yet':'No data yet'}</div>`
    : `<div class="val">${fmt(m.value, Math.abs(m.value)<10&&!Number.isInteger(m.value)?2:Math.abs(m.value)<100&&!Number.isInteger(m.value)?1:0)}<small>${m.unit||''}</small></div>`;
  const due = m.due ? (m.due.never ? 'never tested' : m.due.days < 0 ? `<b class="bad">overdue ${-m.due.days} d</b>` : m.due.days <= 30 ? `due in ${esc(m.due.days)} d` : `due ${shortDate(m.due.date)}`) : '';
  return `<div class="tile ${lever?'lever':''}" data-mk="${esc(m.id)}" tabindex="0" role="button" aria-label="${esc(m.name)}: open history" title="${esc(m.note||'')}">
    <div class="top"><span class="nm">${esc(m.name)}</span><span class="st ${esc(m.status)}" role="img" aria-label="${ST_LABEL[m.status]}">${ST_IC[m.status]}</span></div>
    ${val}${targetLine(m)}${zoneBar(m)}${sparkline(m.history)}
    <div class="meta">${m.date?shortDate(m.date):''}${m.value!=null&&trend(m)?' · '+trend(m):''}${m.z!=null?` · ${m.z>0?'+':''}${esc(m.z)} SD vs 60-day baseline`:''}${due?' · '+due:''}</div>
    <div>${m.verify?'<span class="tag">provisional target</span> ':''}${m.contested?'<span class="tag">dashed = contested optimum</span> ':''}${m.once?'<span class="tag">test once</span>':''}</div>
  </div>`;
}
let LV_DATA = null, LV_FILTER = null;
async function renderLongevity(refetch = true){
  const L = (!refetch && LV_DATA) || await api('/api/longevity').catch(()=>null);
  LV_DATA = L;
  if(!L){ $('#longevity').innerHTML = '<p class="empty">Couldn’t load longevity markers.</p>'; return; }
  const by = Object.fromEntries(L.markers.map(m => [m.id, m]));
  const pa = by.phenoage_gap, cnt = L.counts;
  let h = `<div class="lv-title"><h1>Longevity</h1><a class="btn-link" href="/doctor.html" target="_blank" rel="noopener">For my doctor (print view)</a></div><div class="lv-head">
      <div><div class="lab">Markers ${LV_FILTER?`· showing ${ST_LABEL[LV_FILTER].toLowerCase()} only`:'· click to filter'}</div><div class="lv-counts">${['green','amber','red','grey'].map(s => `<button class="lv-count" data-f="${s}" aria-pressed="${LV_FILTER===s}"><span class="st ${s}">${ST_IC[s]}</span><b>${cnt[s]}</b> ${ST_LABEL[s].toLowerCase()}</button>`).join('')}${LV_FILTER?'<button class="lv-count" data-f="">Show all</button>':''}</div></div>
    </div>
    <p class="sub">Next tests due: ${L.next_due.map(d => `<b>${esc(d.name)}</b> (${d.never?'never tested':d.days<0?'overdue':shortDate(d.date)})`).join(', ') || 'nothing due'}.</p>
`;
  const HSD = await hsGet();
  if(HSD && HSD.score!=null && !LV_FILTER) h += hsPanel(HSD);
  const LA = L.lab_alerts || [];
  if(LA.length && !LV_FILTER) h += `<h2>Blood results to act on</h2><ul class="notes">${LA.map(a => `<li class="n-bad"><span class="ic" role="img" aria-label="Warning">!</span><span><b>${esc(a.title)}.</b> ${esc(a.text)} ${esc(a.todo)}</span></li>`).join('')}</ul>`;
  const keep = m => !LV_FILTER || m.status === LV_FILTER;
  const lev = L.levers.map(id => by[id]).filter(m => m && keep(m));
  if(lev.length) h += `<h2>Top levers</h2><div class="tiles-g">${lev.map(m => tile(m, true)).join('')}</div>`;
  for(const [cat, label] of Object.entries(L.categories)){
    const all = L.markers.filter(m => m.cat === cat); const ms = all.filter(keep); if(!ms.length) continue;
    const c = {green:0, amber:0, red:0, grey:0}; all.forEach(m => c[m.status]++);
    const open = LV_FILTER ? true : ms.some(m => m.value != null);
    h += `<details class="cat" ${open?'open':''}><summary>${label} <span class="sub">${c.green} ✓ · ${c.amber} ! · ${c.red} ✕ · ${c.grey} no data</span></summary><div class="tiles-g">${ms.map(m => tile(m)).join('')}</div></details>`;
  }
  const bc = L.blood_checklist || [];
  if(bc.length && !LV_FILTER) h += `<details class="cat" open><summary>Next blood test: what to ask for <span class="sub">${bc.length} items · ◆ = PhenoAge input</span></summary>
    <ul class="tasks bc">${bc.map(b => `<li class="${b.reason==='never tested'?'':'p-high'}"><span><b>${esc(b.name)}</b>${b.pheno?' <span title="PhenoAge input">◆</span>':''}<span class="area">${esc(b.reason)}</span>${b.why?`<span class="td">${esc(b.why)}</span>`:''}</span></li>`).join('')}</ul>
    <p class="sub">Fast for 10–12 hours (glucose, insulin, lipids). PhenoAge needs all nine inputs within ${esc(L.phenoage.window_days)} days of each other.</p></details>`;
  const sched = L.markers.filter(m => m.due).sort((a,b) => (a.due.days??-9999) - (b.due.days??-9999));
  h += `<h2>Test schedule</h2><table><tr><th>Test</th><th>Last done</th><th>Every</th><th>Due</th></tr>` +
    sched.map(m => { const d = m.due; const cls = d.never ? '' : d.days < 0 ? 'bad' : d.days <= 30 ? '' : 'good';
      return `<tr><td>${esc(m.name)}</td><td>${m.date?shortDate(m.date):'–'}</td><td>${m.once?'once':m.interval_days>=365?'yearly':m.interval_days>=180?'6 months':m.interval_days>=85?'3 months':m.interval_days>=28?'monthly':'weekly'}</td><td class="${cls}">${d.never?'not yet tested':d.days<0?`overdue ${-d.days} days`:d.days<=30?`in ${esc(d.days)} days`:shortDate(d.date)}</td></tr>`; }).join('') + `</table>`;
  h += `<p class="disclaimer">Informational only, not medical advice. Targets marked provisional come from your longevity brief and are being checked against sources; contested optimal ranges never turn a value red. Discuss lab results with your doctor.</p>`;
  $('#longevity').innerHTML = h;
  if(HSD && HSD.score!=null && !LV_FILTER){
    hsChart('hschart', HSD);
    document.querySelectorAll('#longevity .hs-dom[data-dom]').forEach(el => {
      el.onclick = () => openDomain(el.dataset.dom);
      el.onkeydown = e => { if(e.key==='Enter' || e.key===' '){ e.preventDefault(); openDomain(el.dataset.dom); } };
    });
  }
  document.querySelectorAll('#longevity .tile[data-mk]').forEach(t => {
    t.onclick = () => openMarker(t.dataset.mk);
    t.onkeydown = e => { if(e.key==='Enter' || e.key===' '){ e.preventDefault(); openMarker(t.dataset.mk); } };
  });
  document.querySelectorAll('#longevity .lv-count[data-f]').forEach(b => b.onclick = () => {
    LV_FILTER = (b.dataset.f && LV_FILTER !== b.dataset.f) ? b.dataset.f : null;   // click again to clear
    renderLongevity(false);
  });
}

/* ---------- marker detail ---------- */
const SRC = {lab:'Blood test', garmin:'Garmin watch', manual:'Your own test', inbody:'InBody scan', derived:'Calculated', food:'Food log', bp:'BP monitor', nutrition:'Food log'};
function openMarker(id){
  const m = (LV_DATA?.markers||[]).find(x => x.id === id); if(!m) return;
  const dlg = $('#mk-dlg'), c = theme(), H = m.history || [];
  const dp = v => Math.abs(v)<10 && !Number.isInteger(v) ? 2 : Math.abs(v)<100 && !Number.isInteger(v) ? 1 : 0;
  const every = m.once ? 'once' : !m.interval_days ? 'continuous' : m.interval_days>=365 ? 'yearly' : m.interval_days>=180 ? 'every 6 months' : m.interval_days>=85 ? 'every 3 months' : 'monthly';
  const rows = [...H].reverse().slice(0, 40);
  $('#mk-body').innerHTML = `<div class="mk-h"><div><h2 id="mk-title">${esc(m.name)}</h2>
      <div class="sub">${SRC[m.source]||m.source||''}${m.unit?` · ${esc(m.unit)}`:''} · ${every}</div></div>
      <button class="mk-x" aria-label="Close">✕</button></div>
    <div class="mk-now">${m.value==null?'<span class="empty-v">No result yet</span>':`<span class="st ${esc(m.status)}" role="img" aria-label="${ST_LABEL[m.status]}">${ST_IC[m.status]}</span> <b>${fmt(m.value, dp(m.value))}</b> ${m.unit||''} <span class="sub">${ST_LABEL[m.status].toLowerCase()} · ${shortDate(m.date)}</span>`}</div>
    ${targetLine(m)}
    ${H.length ? `<div id="mkchart" class="chart" style="height:260px"></div>` : ''}
    ${m.note?`<p class="mk-note">${esc(m.note)}</p>`:''}
    <p class="sub">${m.verify?'<span class="tag">provisional target</span> Being checked against sources. ':''}${m.contested?'Dashed lines mark a contested “optimal” range; it never turns a value red. ':''}${m.lab_ref?`Lab reference range: ${m.lab_ref[0]!=null&&m.lab_ref[1]!=null?`${m.lab_ref[0]} to ${m.lab_ref[1]}`:m.lab_ref[1]!=null?`below ${m.lab_ref[1]}`:`above ${m.lab_ref[0]}`}. `:''}</p>
    ${rows.length ? `<table><tr><th>Date</th><th class="num">Value</th></tr>${rows.map(([d,v]) => `<tr><td>${shortDate(d)} ${String(d).slice(0,4)}</td><td class="num">${fmt(v, dp(v))}</td></tr>`).join('')}</table>${H.length>40?`<p class="sub">Showing the latest 40 of ${H.length}.</p>`:''}` : ''}`;
  if(!dlg.open) dlg.showModal();
  $('#mk-body .mk-x').onclick = () => dlg.close();
  dlg.onclick = e => { if(e.target === dlg) dlg.close(); };
  if(!H.length) return;
  const g = m.bands==='lab' ? m.lab_ref : m.green, a = m.bands==='lab' ? null : m.amber, ct = m.contested;
  const nums = [...H.map(p=>p[1]), ...(g||[]), ...(a||[]), ...(ct||[])].filter(v => v!=null && isFinite(v));
  let lo = Math.min(...nums), hi = Math.max(...nums); const pad = (hi-lo || Math.abs(hi) || 1) * .15; lo -= pad; hi += pad;
  if(lo < 0 && Math.min(...nums) >= 0) lo = 0;
  const band = (b, col, name) => b ? [[{yAxis: b[0]??lo, itemStyle:{color:col, opacity:.13}, name}, {yAxis: b[1]??hi}]] : [];
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule,opacity:.5}}};
  const x0 = new Date(H[0][0]).getTime(), x1 = new Date(H[H.length-1][0]).getTime(), xp = Math.max((x1-x0)*.04, 3*864e5);
  setTimeout(() => chart('mkchart').setOption({animation:MOTION,textStyle:{fontFamily:'Archivo'},grid:{left:48,right:24,top:16,bottom:28},
    xAxis:{type:'time',min:x0-xp,max:x1+xp,...ax,splitLine:{show:false},axisLabel:{...ax.axisLabel,formatter:v=>new Date(v).toLocaleDateString('en-GB',{day:'numeric',month:'short'})}},
    yAxis:{type:'value',min:+lo.toFixed(2),max:+hi.toFixed(2),...ax,name:m.unit||'',nameTextStyle:{color:c.muted,fontSize:11}},
    tooltip:{trigger:'axis',...tip(c),formatter:ps=>`<b>${fmtDate(String(ps[0].value[0]).slice(0,10))}</b><br>${fmt(ps[0].value[1], dp(ps[0].value[1]))} ${m.unit||''}`},
    series:[{type:'line',name:m.name,data:H.map(p=>[p[0],p[1]]),showSymbol:H.length<60,symbol:'circle',symbolSize:8,
      lineStyle:{color:c.ink,width:2},itemStyle:{color:c.accent,...ring(c)},
      markArea:{silent:true,label:{show:false},data:[...band(a,c.warn,'near'),...band(g,c.good,'target')]},
      markLine: ct ? {symbol:'none',silent:true,lineStyle:{type:'dashed',color:c.muted},label:{color:c.muted,fontSize:11,position:'insideEndTop'},
        data: ct.filter(v=>v!=null).map(v=>({yAxis:v,label:{formatter:'optimal '+v}}))} : undefined}]}), 30);
}

/* ---------- wellbeing ---------- */
const WB = {overall:['Overall','#3b4252'], mood:['Mood','#2a78d6'], energy:['Energy','#eda100'], gut:['Gut','#1baf7a'], stress:['Stress (5 = very stressed)','#e87ba4']};
const SEV_TXT = ['', 'mild', 'moderate', 'severe'];
async function renderWellbeing(){
  const W = await api('/api/wellbeing').catch(()=>null);
  if(!W){ $('#wb-head').innerHTML = '<p class="empty">Couldn’t load wellbeing data. The dashboard service may need a restart.</p>'; return; }
  const c = theme(), any = W.reports.length > 0;
  const how = `<div class="wb-how"><b>How to report</b> (any part, any day, in chat):<code>feel 4 mood 4 energy 3 gut 2 stress 3</code><code>sym headache mild 15:00, bloating moderate, sore shoulder (left) mild</code>
    <span class="sub">Scores are 1–5 (5 = great; for stress 5 = very stressed). Severity: mild, moderate or severe. Add a note in plain words and I'll file it.</span></div>`;
  const delta = s => s.now==null ? '–' : `${fmt(s.now,1)}${s.before!=null?` <span class="sub">${s.now>s.before?'↑':s.now<s.before?'↓':'→'} vs ${fmt(s.before,1)} before</span>`:''}`;
  $('#wb-head').innerHTML = `<p class="sub">Your mood scores and health issues as you report them, with off episodes shaded and sleep for context.</p>
    <div class="tiles-g wb-tiles">${['overall','mood','energy','gut','stress'].map(k => `<div class="t"><div class="lab">${WB[k][0].split(' (')[0]} · 7-day avg</div><div class="v">${delta(W.summary[k])}</div></div>`).join('')}
      <div class="t"><div class="lab">Logged</div><div class="v">${esc(W.logged_14d)}<small> of 14 days</small></div></div>
      <div class="t"><div class="lab">Days with symptoms</div><div class="v">${esc(W.symptom_days_30d)}<small> in 30 days</small></div></div></div>
    ${any ? '' : how}`;
  // chart: scores over time, episodes shaded, sleep as faint bars
  const first = W.days.findIndex(d => Object.keys(d.feel).length || d.symptoms.length);
  const D = W.days.slice(first < 0 ? -30 : Math.max(0, Math.min(first - 3, W.days.length - 30))), x = D.map(d => d.date);
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule,opacity:.5}}};
  const eps = W.episodes.filter(e => e.end >= x[0]).map(e => [{xAxis: x.find(d => d >= e.start) || x[0], itemStyle:{color:'rgba(200,55,45,.10)'}}, {xAxis: [...x].reverse().find(d => d <= e.end) || x[x.length-1]}]);
  const series = Object.entries(WB).map(([k,[name,col]]) => ({type:'line',name,connectNulls:true,symbol:'circle',symbolSize:7,yAxisIndex:0,
    lineStyle:{color:col,width:k==='overall'?2.8:1.4,opacity:k==='overall'?1:.55},itemStyle:{color:col,opacity:k==='overall'?1:.7,...ring(c)},z:k==='overall'?5:3,
    emphasis:{focus:'series'},data:D.map(d => d.feel[k] ?? null)}));
  series.push({type:'bar',name:'Sleep (h)',yAxisIndex:1,barMaxWidth:8,itemStyle:{color:c.rule,opacity:.6},data:D.map(d => d.sleep_h ? +d.sleep_h.toFixed(1) : null),z:1,
    markArea:{silent:true,label:{show:false},data:eps}});
  series.push({type:'scatter',name:'Symptoms',yAxisIndex:0,symbol:'triangle',symbolSize:v=>8+v[2]*3,itemStyle:{color:c.bad},
    data:D.filter(d => d.symptoms.length).map(d => [d.date, 5.6, Math.max(...d.symptoms.map(s=>s.severity))])});
  chart('wbchart').setOption({animation:MOTION,textStyle:{fontFamily:'Archivo'},grid:{left:36,right:40,top:36,bottom:28},
    legend:{top:0,left:0,itemWidth:14,itemHeight:8,textStyle:{color:c.muted,fontSize:11},selected:{'Stress (5 = very stressed)':false}},
    xAxis:{type:'category',data:x,...ax,axisTick:{show:false},axisLabel:{...ax.axisLabel,formatter:v=>shortDate(v)}},
    yAxis:[{type:'value',min:1,max:6,interval:1,...ax,axisLabel:{...ax.axisLabel,formatter:v=>v<=5?v:''}},{type:'value',min:0,max:12,show:false}],
    tooltip:{trigger:'axis',...tip(c),formatter:ps=>{ const d = D[ps[0].dataIndex]; const ep = W.episodes.find(e => d.date>=e.start && d.date<=e.end);
      return `<b>${fmtDate(d.date)}</b>${Object.entries(d.feel).map(([k,v])=>`<br>${WB[k][0].split(' (')[0]} ${v}`).join('')}${d.sleep_h?`<br>Sleep ${hm(d.sleep_h)}`:''}${d.symptoms.map(s=>`<br><span style="color:${c.bad}">▲</span> ${esc(s.what)} (${SEV_TXT[s.severity]})`).join('')}${d.note?`<br><i>${esc(d.note)}</i>`:''}${ep?`<br><b>Off episode:</b> ${esc(ep.what)}`:''}`; }},
    series});
  // symptom grid (last 60 days) + recent reports
  const last = D.slice(-60);
  let h = '';
  if(W.symptoms.length){
    h += `<h2>Symptoms, last 60 days</h2><div class="wrap"><table class="wb-grid"><tr><th></th>${last.map((d,i)=>`<th title="${shortDate(d.date)}"><span>${i%7===0?shortDate(d.date):''}</span></th>`).join('')}<th class="num">Total</th></tr>` +
      W.symptoms.map(s => `<tr><td class="nm">${esc(s.what)}</td>${last.map(d => { const m = d.symptoms.filter(z=>z.what===s.what); const v = m.length ? Math.max(...m.map(z=>z.severity)) : 0;
        return `<td class="c s${v}" title="${shortDate(d.date)}${v?': '+SEV_TXT[v]:''}"></td>`; }).join('')}<td class="num">${esc(s.count)}</td></tr>`).join('') + `</table></div>
      <p class="sub">Darker = more severe.${W.symptoms.filter(s=>s.context).map(s=>` <b>${esc(s.what)}</b>: ${esc(s.context)}`).join('')}</p>`;
  }
  if(W.reports.length) h += `<h2>Recent reports</h2><table class="wb-rep"><tr><th>Date</th><th>Scores</th><th>Symptoms</th><th>Note</th></tr>${W.reports.map(r => `<tr><td>${shortDate(r.date)}</td>
      <td>${Object.entries(r.feel).map(([k,v])=>`${WB[k][0].split(' (')[0].toLowerCase()} ${v}`).join(' · ')||'–'}</td>
      <td>${r.symptoms.map(s=>`${esc(s.what)} <span class="sub">${SEV_TXT[s.severity]}${s.time?' '+s.time:''}</span>`).join(', ')||'–'}</td><td>${esc(r.note||'')}</td></tr>`).join('')}</table>`;
  h += `<h2>Off episodes</h2><ul class="tl">${[...W.episodes].reverse().map(e => `<li><i style="background:${c.bad}"></i><span class="d">${shortDate(e.start)}${e.end!==e.start?'–'+shortDate(e.end):''}</span><span>${esc(e.what)}</span></li>`).join('')}</ul>`;
  if(any) h += how;
  $('#wb-body').innerHTML = h;
}

/* ---------- advice ---------- */
const ADV_LABEL = {act:'Act on this', keep:'Keep doing', info:'Worth knowing'};
async function renderAdvice(){
  const A = await api('/api/advice').catch(()=>null);
  if(!A){ $('#advice').innerHTML = '<p class="empty">Couldn’t load advice. The dashboard service may need a restart.</p>'; return; }
  const card = (i, sec) => `<div class="adv ${esc(i.level)}"><div class="adv-top"><span class="adv-lv">${ADV_LABEL[i.level]}</span>${sec?`<span class="area">${sec}</span>`:''}</div>
    <h3>${esc(i.title)}</h3><p class="why">${esc(i.why)}</p><ul>${i.do.map(d=>`<li>${esc(d)}</li>`).join('')}</ul></div>`;
  let h = `<h1>Advice</h1><p class="sub">Worked out from your own last 2–4 weeks of logs, watch data and blood tests (data to ${shortDate(A.as_of)}). It updates as you log. Not medical advice.</p>`;
  if(A.top.length) h += `<h2>Top ${A.top.length} for this week</h2><div class="adv-g top">${A.top.map(i => card(i, i.section)).join('')}</div>`;
  h += `<nav class="adv-jump">${A.sections.map(s => `<a href="#" data-j="${esc(s.name)}">${esc(s.name)} <b>${s.items.filter(i=>i.level==='act').length}</b></a>`).join('')}</nav>`;
  for(const s of A.sections) h += `<h2 id="adv-${esc(s.name.replace(/\W+/g,'-'))}">${esc(s.name)}</h2><div class="adv-g">${s.items.map(i => card(i)).join('')}</div>`;
  $('#advice').innerHTML = h;
  document.querySelectorAll('.adv-jump a').forEach(a => a.onclick = e => { e.preventDefault(); document.getElementById('adv-'+a.dataset.j.replace(/\W+/g,'-')).scrollIntoView({behavior:'smooth'}); });
}

/* ---------- timeline ---------- */
const TL_KIND = {lab:['Blood test','#2a78d6'], scan:['Scan','#1baf7a'], episode:['Off episode','#C8372D'], target:['Target change','#B7791F'], training:['Training','#6250d6'], health:['Health','#e87ba4'], setup:['Setup',null], life:['Life',null]};
async function renderTimeline(){
  const ev = await api('/api/timeline').catch(()=>[]); const c = theme();
  const col = k => (TL_KIND[k]||[])[1] || c.muted;
  const w = SUMMARY.filter(d => d.weight && d.weight.fasted !== false).map(d => [d.date, d.weight.kg]);
  const avg = w.map(([d], i) => { const t = new Date(d) - 6*864e5; const win = w.slice(0, i+1).filter(([dd]) => new Date(dd) >= t).map(p=>p[1]); return [d, +(win.reduce((a,b)=>a+b,0)/win.length).toFixed(2)]; });
  const start = w.length ? w[0][0] : null;
  const marks = ev.filter(e => start && e.date >= start && e.kind !== 'episode');
  const eps = ev.filter(e => e.kind === 'episode');
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule,opacity:.5}}};
  const plus1 = d => new Date(new Date(d+'T00:00').getTime()+864e5).toISOString().slice(0,10);
  if(w.length) chart('tlchart').setOption({animation:MOTION,textStyle:{fontFamily:'Archivo'},grid:{left:48,right:24,top:24,bottom:28},
    xAxis:{type:'time',...ax,splitLine:{show:false},axisLabel:{...ax.axisLabel,formatter:v=>new Date(v).toLocaleDateString('en-GB',{day:'numeric',month:'short'})}},
    yAxis:{type:'value',scale:true,...ax,name:'kg',nameTextStyle:{color:c.muted,fontSize:11}},
    tooltip:{trigger:'axis',...tip(c),formatter:ps=>{ const p = ps.find(x=>x.seriesName==='7-day average')||ps[0]; const d = String(p.value[0]).slice(0,10);
      const here = ev.filter(e => e.date===d || (e.end && e.date<=d && d<=e.end));
      const day = (w.find(x => String(x[0]).slice(0,10)===d)||[])[1];
      return `<b>${fmtDate(d)}</b>${day!=null?`<br>Weigh-in ${fmt(day,2)} kg`:''}<br>7-day average ${fmt(p.value[1],1)} kg${here.map(e=>`<br><span style="color:${col(e.kind)}">●</span> ${esc(e.what)}${e.kind==='episode'?': '+esc(e.detail):''}`).join('')}`; }},
    series:[{type:'scatter',name:'Daily',data:w,symbolSize:6,itemStyle:{color:c.accent,opacity:.85,borderColor:c.surface,borderWidth:1},silent:true},
      {type:'line',name:'7-day average',data:avg,showSymbol:false,lineStyle:{color:c.ink,width:2},
      markLine:{symbol:'none',label:{show:false},data:marks.map(e=>({xAxis:e.date,name:e.what,lineStyle:{color:col(e.kind),type:e.kind==='target'?'dashed':'solid',width:1.5}})),
        emphasis:{label:{show:true,formatter:p=>p.name,color:c.ink,fontSize:11,position:'insideEndTop'}}},
      markArea:{silent:true,label:{show:false},data:eps.map(e=>[{xAxis:e.date,itemStyle:{color:'rgba(200,55,45,.10)'}},{xAxis:plus1(e.end||e.date)}])}}]});
  const H = await hsGet(); if(H && H.history.length) hsChart('tlhs', H, ev);
  const months = {};
  ev.forEach(e => { const k = new Date(e.date+'T00:00').toLocaleDateString('en-GB',{month:'long',year:'numeric'}); (months[k] = months[k] || []).push(e); });
  $('#tllist').innerHTML = `<div class="tl-legend">${Object.entries(TL_KIND).filter(([k])=>ev.some(e=>e.kind===k)).map(([k,[l]])=>`<span><i style="background:${col(k)}"></i>${l}</span>`).join('')}</div>` +
    Object.entries(months).map(([m, es]) => `<h2>${m}</h2><ul class="tl">${es.map(e => `<li><i style="background:${col(e.kind)}" title="${(TL_KIND[e.kind]||[e.kind])[0]}"></i><span class="d">${shortDate(e.date)}${e.end&&e.end!==e.date?'–'+shortDate(e.end):''}</span><span><b>${esc(e.what)}</b>${e.detail?`<span class="td">${esc(e.detail)}</span>`:''}</span></li>`).join('')}</ul>`).join('');
}

/* ---------- week ---------- */
let WEEK = null;
async function renderWeek(start){
  const w = await api('/api/week' + (start ? '?start='+start : '')).catch(()=>null);
  if(!w){ $('#week').innerHTML = '<p class="empty">No data for this week.</p>'; return; }
  WEEK = w.start;
  const dm = s => new Date(s+'T00:00').toLocaleDateString('en-GB',{day:'numeric',month:'short'});
  const hitTile = (k, label) => { const h = w.hits[k], a = w.averages[k];
    const cls = !h.of ? '' : h.hit/h.of >= .7 ? 'good' : h.hit/h.of >= .4 ? '' : 'bad';
    return `<div class="t"><div class="lab">${label}</div><div class="v ${cls}">${h.of ? `${esc(h.hit)}/${esc(h.of)}` : '–'}</div><div class="s">${h.of ? 'days on target' : 'no target that week'} · avg ${a==null?'–':fmt(a, k==='satfat_g'?1:0)}${k==='kcal'?'':'g'}</div></div>`; };
  const tr = w.training, r = w.recovery, wt = w.weight;
  const dW = wt.avg!=null && wt.prev_avg!=null ? (wt.avg - wt.prev_avg) : null;
  let h = `<h1>Week of ${dm(w.start)} – ${dm(w.end)}</h1>
    <div><span class="chip">${esc(w.status.complete)} complete</span>${w.status.partial?`<span class="chip partial">${esc(w.status.partial)} partial</span>`:''}${w.status.unlogged?`<span class="chip unlogged">${esc(w.status.unlogged)} unlogged</span>`:''}</div>
    ${w.focus ? `<h2>Focus for next week</h2><div class="focus">${esc(w.focus)}</div>` : ''}
    <div class="wk-grid">${hitTile('kcal','Calories')}${hitTile('protein_g','Protein')}${hitTile('satfat_g','Saturated fat')}${hitTile('fibre_g','Fibre')}</div>
    <div class="wk-grid">
      <div class="t"><div class="lab">Weight, week average</div><div class="v">${wt.avg??'–'}</div><div class="s">${dW!=null?`${dW>0?'+':''}${dW.toFixed(1)} kg vs previous week`:'no comparison'}</div></div>
      <div class="t"><div class="lab">Sessions</div><div class="v">${Object.values(tr.sessions).reduce((a,b)=>a+b,0)}</div><div class="s">${Object.entries(tr.sessions).map(([k,v])=>`${v} ${k}`).join(', ')||'none'}${tr.run_km?` · ${esc(tr.run_km)} km run`:''}</div></div>
      <div class="t"><div class="lab">Sleep average</div><div class="v ${r.sleep_avg_h==null?'':r.sleep_avg_h>=7.5?'good':'bad'}">${r.sleep_avg_h!=null?hm(r.sleep_avg_h):'–'}</div><div class="s">${r.nights?`${esc(r.nights_ok)}/${esc(r.nights)} nights ≥ 7h30`:'no watch data'}</div></div>
      <div class="t"><div class="lab">HRV · resting HR</div><div class="v">${r.hrv_avg??'–'} · ${r.rhr_avg??'–'}</div><div class="s">steps ${r.steps_avg!=null?fmt(r.steps_avg):'–'} a day</div></div>
    </div>`;
  if(w.habits){
    const H = w.habits;
    h += `<h2>Habits</h2><table><tr><th>Habit</th><th>This week</th><th>Target</th><th></th></tr>` + H.weekly.map(r => {
      const tgt = r.green ? (r.green[0]!=null && r.green[1]!=null ? `${r.green[0]}–${r.green[1]}` : r.green[0]!=null ? `≥ ${r.green[0]}` : `< ${r.green[1]}`) : '–';
      return `<tr><td>${esc(r.label)}</td><td><b>${r.value==null?'–':fmt(r.value, r.value<10&&!Number.isInteger(r.value)?2:0)}</b></td><td class="sub">${tgt} ${r.unit||''}</td><td><span class="st ${esc(r.status)}" role="img" aria-label="${ST_LABEL[r.status]}">${ST_IC[r.status]}</span></td></tr>`; }).join('') + `</table>`;
    const G = H.grid;
    const cells = (k) => G.map((d, i) => `<i class="${d[k]===true?'y':d[k]===false?'n':''}${i%7===0&&i?' wk':''}" title="${shortDate(d.date)}: ${d[k]===true?'yes':d[k]===false?'no':'no data'}"></i>`).join('');
    const pct = (k) => { const v = G.filter(d => d[k]!=null); return v.length ? Math.round(100*v.filter(d=>d[k]).length/v.length) : null; };
    h += `<h2>Last 12 weeks</h2><p class="sub">Each square is a day: green met, hatched red missed, pale no data. ${shortDate(G[0].date)} to ${shortDate(G[G.length-1].date)}.</p>
      <div class="hm">${H.names.map(([k, lab]) => `<span class="lab">${lab} <span class="pct">${pct(k)!=null?pct(k)+'%':''}</span></span>${cells(k)}`).join('')}</div>`;
  }
  if(tr.prs.length) h += `<h2>New bests</h2><ul class="notes">${tr.prs.map(p => `<li class="n-good"><span class="ic">✓</span><span>${p.lift.replace(/-/g,' ')}: ${esc(p.kg)} kg${p.reps?' × '+p.reps:p.metres?' for '+p.metres+' m':''} <span class="who">${shortDate(p.date)}</span></span></li>`).join('')}</ul>`;
  const cols = [['kcal','Calories',0],['protein_g','Protein',0],['satfat_g','Sat fat',1],['fibre_g','Fibre',0]];
  h += `<h2>Days</h2><table class="wk"><tr><th>Day</th><th>Type</th>${cols.map(c=>`<th>${c[1]}</th>`).join('')}<th>Weight</th><th>Sleep</th><th>Steps</th><th>Training</th></tr>` +
    w.days.map(d => { const t = d.totals||{}, ev = d.eval||{};
      return `<tr><td><a href="#day" data-date="${esc(d.date)}">${new Date(d.date+'T00:00').toLocaleDateString('en-GB',{weekday:'short',day:'numeric'})}</a>${d.date===(w.best||{}).date?' <span class="who">best</span>':''}${d.date===(w.worst||{}).date?' <span class="who">worst</span>':''}</td><td>${esc(d.day_type)}${d.status!=='complete'?`, <span class="sub">${esc(d.status)}</span>`:''}</td>` +
        cols.map(([k,,dp]) => { const e = ev[k]; const cl = e&&e.ok===true?'good':e&&e.ok===false?'bad':''; return `<td class="${cl}">${d.totals?fmt(t[k],dp):'–'}${ARROW(e)}</td>`; }).join('') +
        `<td>${d.weight?d.weight.kg:'–'}</td><td>${d.sleep||'–'}</td><td>${d.steps?fmt(d.steps):'–'}</td><td>${esc(d.exercise.join(', ')||'–')}</td></tr>`; }).join('') + `</table>`;
  $('#week').innerHTML = h;
  document.querySelectorAll('#week a[data-date]').forEach(a => a.onclick = e => { e.preventDefault(); showTab('day'); renderDay(a.dataset.date); });
}
const shiftWeek = n => { const d = new Date(WEEK+'T00:00'); d.setDate(d.getDate()+7*n); renderWeek(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`); };
$('#wprev').onclick = () => shiftWeek(-1); $('#wnext').onclick = () => shiftWeek(1); $('#wlatest').onclick = () => renderWeek();

/* ---------- trends ---------- */
let RANGE = 30;
document.querySelectorAll('#range button').forEach(b => b.onclick = () => {
  document.querySelectorAll('#range button').forEach(x => x.setAttribute('aria-pressed', x===b)); RANGE = +b.dataset.d; renderTrends(); });

// Target that applied on each day, plus the latest target as a dotted reference where none applied yet.
function targetSeries(days, get){
  const applied = days.map(d => get(d.targets));
  let latest = null; for(const d of SUMMARY){ const v = get(d.targets); if(v!=null) latest = v; }
  const ref = applied.map(v => v==null ? latest : null);
  // extend reference one step so it joins the applied line
  const firstApplied = applied.findIndex(v => v!=null);
  if(firstApplied>0) ref[firstApplied] = applied[firstApplied];
  return {applied, ref, latest};
}
const bandTxt = v => v==null ? '' : Array.isArray(v) ? `${fmt(v[0])}–${fmt(v[1])}` : fmt(v);

function renderTrends(){
  const c = theme();
  let days = SUMMARY; if(RANGE) days = days.slice(-RANGE);
  const x = days.map(d => shortDate(d.date));
  const panels = [
    {key:'kcal', name:'Calories', kind:'band', get: t => t.kcal},
    {key:'protein_g', name:'Protein g', kind:'min', get: t => t.protein_min},
    {key:'carbs_g', name:'Carbs g', kind:'band', get: t => t.carbs},
    {key:'fat_g', name:'Fat g, saturated fat line', kind:'band', get: t => t.fat, sat:true},
    {key:'fibre_g', name:'Fibre g', kind:'min', get: t => t.fibre_min},
    {key:'weight', name:'Morning weight kg (filled = fasted, hollow = not fasted)', kind:'min', get: t => t.weight_kg},
  ];
  const H = $('#trend').clientHeight || 1040;
  const n = panels.length, top = 34, gap = 36, h = (H - top - 36 - gap*(n-1)) / n;
  const grids = [], xAxes = [], yAxes = [], series = [], titles = [];
  const ax = {axisLine:{lineStyle:{color:c.rule}}, axisLabel:{color:c.muted,fontSize:11}, splitLine:{lineStyle:{color:c.rule,opacity:.5}}};
  const endLab = (col) => ({show:true, color:c.ink, fontSize:11, fontWeight:600, fontFamily:'Archivo', formatter: p => fmt(p.value), offset:[4,0]});
  panels.forEach((p, i) => {
    const t = top + i*(h+gap);
    const ts = targetSeries(days, p.get);
    grids.push({left:52,right:58,top:t,height:h});
    titles.push({text:`${p.name}${p.key==='kcal'?' eaten (bars), burnt per Garmin (orange line)':''}   target ${p.key==='weight'?'':p.kind==='min'&&p.key!=='weight'?'≥ ':''}${bandTxt(ts.latest)}${p.sat?' · sat fat ≤ 20':''}`,
      left:52,top:t-21,textStyle:{fontSize:12.5,fontWeight:600,color:c.ink,fontFamily:'Archivo'}});
    xAxes.push({type:'category',gridIndex:i,data:x,...ax,axisLabel:{...ax.axisLabel,show:i===n-1},axisTick:{show:false}});
    // y-axis always wide enough to include the target
    const vals = days.flatMap(d => p.key==='weight' ? [(d.weight||{}).kg] : p.key==='kcal' ? [(d.totals||{}).kcal, d.burn] : [(d.totals||{})[p.key]]).filter(v => v!=null);
    const tv = [...ts.applied, ...ts.ref].flatMap(v => v==null?[]:Array.isArray(v)?v:[v]);
    const lo = Math.min(...vals, ...tv), hi = Math.max(...vals, ...tv);
    yAxes.push({type:'value',gridIndex:i,...ax, ...(p.key==='weight' ? niceRange(lo-0.2, hi+0.2, 3) : niceRange(0, hi, 4, true))});
    const common = {xAxisIndex:i,yAxisIndex:i,symbol:'none',silent:true,step:'middle',tooltip:{show:false}};
    if(p.kind==='band'){
      const loA = ts.applied.map(v => v?v[0]:null), hiA = ts.applied.map(v => v?v[1]:null);
      series.push({...common,type:'line',data:loA,stack:'band'+i,lineStyle:{opacity:0}});
      series.push({...common,type:'line',data:hiA.map((v,j)=>v==null?null:v-loA[j]),stack:'band'+i,lineStyle:{opacity:0},areaStyle:{color:c.soft}});
      series.push({...common,type:'line',data:loA,lineStyle:{color:c.accent,width:1,opacity:.6}});
      series.push({...common,type:'line',data:hiA,lineStyle:{color:c.accent,width:1,opacity:.6},endLabel:endLab(c.accent)});
      series.push({...common,type:'line',data:ts.ref.map(v=>v?v[0]:null),lineStyle:{color:c.muted,width:1,type:'dotted'}});
      series.push({...common,type:'line',data:ts.ref.map(v=>v?v[1]:null),lineStyle:{color:c.muted,width:1,type:'dotted'}});
    } else {
      series.push({...common,type:'line',data:ts.applied,lineStyle:{color:c.accent,type:'dashed',width:1.6},endLabel:endLab(c.accent),z:5});
      series.push({...common,type:'line',data:ts.ref,lineStyle:{color:c.muted,width:1.2,type:'dotted'},z:5});
    }
    if(p.key==='weight'){
      series.push({type:'line',xAxisIndex:i,yAxisIndex:i,name:'Fasted',connectNulls:true,symbol:'circle',symbolSize:9,lineStyle:{color:c.accent,width:2},itemStyle:{color:c.accent,...ring(c)},z:6,
        data:days.map(d => d.weight && d.weight.fasted!==false ? d.weight.kg : null)});
      series.push({type:'scatter',xAxisIndex:i,yAxisIndex:i,name:'Not fasted',symbolSize:9,itemStyle:{color:c.surface,borderColor:c.accent,borderWidth:2},z:6,
        data:days.map(d => d.weight && d.weight.fasted===false ? d.weight.kg : null)});
      return;
    }
    series.push({type:'bar',xAxisIndex:i,yAxisIndex:i,barMaxWidth:24,barCategoryGap:'28%',z:3,name:p.name,
      animationDelay: k => k*12,
      data: days.map(d => {
        const v = d.totals ? d.totals[p.key] : null; if(v==null) return null;
        const e = (d.eval||{})[p.key]; const ok = e ? e.ok : null;
        const arrow = ok===false && e.dir ? (e.dir==='over'?'↑':'↓') : null;
        return {value:v,itemStyle:{color:statusFill(c, ok, d.status!=='complete'),borderRadius:[4,4,0,0]},
          label:{show:!!arrow,position:'top',distance:2,formatter:arrow||'',color:c.bad,fontSize:14,fontWeight:800}};
      })});
    if(p.key==='kcal'){   // Garmin's measured total burn for the day; today's is only up to the last watch sync
      const today = new Date(Date.now()+8*3600e3).toISOString().slice(0,10);
      series.push({type:'line',xAxisIndex:i,yAxisIndex:i,z:8,name:'Burnt (Garmin)',connectNulls:false,symbol:'circle',symbolSize:7,
        lineStyle:{color:'#eb6834',width:2},itemStyle:{color:'#eb6834',...ring(c)},
        data: days.map(d => d.burn==null ? null : {value:d.burn, itemStyle: d.date===today ? {color:c.surface,borderColor:'#eb6834',borderWidth:2} : undefined})});
    }
    if(p.sat){
      const st = targetSeries(days, t => t.satfat_max);
      series.push({type:'line',xAxisIndex:i,yAxisIndex:i,z:7,name:'Saturated fat',symbol:'circle',symbolSize:9,lineStyle:{color:c.ink,width:2},
        data: days.map(d => { const v = d.totals ? d.totals.satfat_g : null; if(v==null) return null;
          const e = (d.eval||{}).satfat_g, ok = e ? e.ok : null;
          return {value:v, itemStyle:{color: d.status!=='complete' ? c.muted : ok===false ? c.bad : ok===true ? c.good : c.ink, ...ring(c)},
            label:{show:ok===false,position:'right',distance:3,formatter:'↑',color:c.bad,fontSize:14,fontWeight:800}}; })});
      series.push({...common,type:'line',data:st.applied,lineStyle:{color:c.ink,type:'dashed',width:1.4,opacity:.7},endLabel:{...endLab(c.ink),formatter:p=>'sat '+fmt(p.value)},z:6});
      series.push({...common,type:'line',data:st.ref,lineStyle:{color:c.ink,type:'dotted',width:1,opacity:.4},z:6});
    }
  });
  const ch = chart('trend');
  ch.setOption({animation:MOTION,animationDuration:550,animationEasing:'cubicOut',animationDurationUpdate:0,textStyle:{fontFamily:'Archivo'},title:titles,grid:grids,xAxis:xAxes,yAxis:yAxes,series,
    axisPointer:{link:[{xAxisIndex:'all'}],lineStyle:{color:c.muted}},
    tooltip:{trigger:'axis',...tip(c),
      formatter: ps => { const d = days[ps[0].dataIndex]; const t = d.totals||{}, g = d.targets||{};
        return `<b>${fmtDate(d.date)}</b><br>${esc(d.day_type)} day, ${esc(d.status)}<br>` +
          (d.totals?(()=>{ const E = d.eval||{}, a = k => ARROW(E[k]);
            const today = new Date(Date.now()+8*3600e3).toISOString().slice(0,10);
            const burn = d.burn!=null ? `<br><span style="color:#eb6834">●</span> burnt ${fmt(d.burn)} kcal (Garmin${d.date===today?', so far':''})${d.date!==today?` · balance <b>${t.kcal-d.burn>=0?'+':''}${fmt(t.kcal-d.burn)}</b>`:''}` : '';
            return `${fmt(t.kcal)}${a('kcal')} kcal eaten (target ${bandTxt(g.kcal)||'–'})${burn}<br>protein ${fmt(t.protein_g)}${a('protein_g')} (≥ ${g.protein_min??'–'}) · carbs ${fmt(t.carbs_g)}${a('carbs_g')} · fat ${fmt(t.fat_g)}${a('fat_g')} · sat ${fmt(t.satfat_g,1)}${a('satfat_g')}${g.satfat_max?' (≤ '+g.satfat_max+')':''} · fibre ${fmt(t.fibre_g)}${a('fibre_g')}`; })():'No food logged') +
          (d.weight?`<br>${esc(d.weight.kg)} kg${d.weight.fasted===false?' (not fasted)':''} · target ${esc(g.weight_kg)}`:'') +
          (d.exercise.length?`<br>${esc(d.exercise.map(e=>e.type+(e.distance_km?' '+e.distance_km+' km':'')).join(', '))}`:''); }}});
  ch.getZr().on('click', ev => {
    const idx = ch.convertFromPixel({xAxisIndex:0}, [ev.offsetX, ev.offsetY]);
    const i = Array.isArray(idx) ? idx[0] : idx;
    if(i!=null && days[i]){ showTab('day'); renderDay(days[i].date); }
  });
  renderDayTable(days);
}
function renderDayTable(days){
  const cols = [['kcal','Calories',0,'kcal'],['protein_g','Protein',0,'protein_min'],['carbs_g','Carbs',0,'carbs'],['fat_g','Fat',0,'fat'],['satfat_g','Sat fat',1,'satfat_max'],['fibre_g','Fibre',0,'fibre_min']];
  const cur = (SUMMARY[SUMMARY.length-1]||{}).targets||{};
  const tcell = k => { const v = cur[k]; if(v==null) return '–'; return Array.isArray(v)?`${v[0]}–${v[1]}`:k.endsWith('_min')?`≥ ${v}`:k.endsWith('_max')?`≤ ${v}`:v; };
  let h = `<table class="wk"><tr><th>Date</th><th>Day</th>${cols.map(c=>`<th>${c[1]}</th>`).join('')}<th>Weight</th><th>Training</th></tr>
    <tr class="tgtrow"><td>Current target</td><td class="sub">training day</td>${cols.map(c=>`<td>${tcell(c[3])}</td>`).join('')}<td>${cur.weight_kg??'–'}</td><td></td></tr>`;
  for(const d of [...days].reverse()){
    const t = d.totals||{}, ev = d.eval||{};
    h += `<tr><td><a href="#day" data-date="${esc(d.date)}">${shortDate(d.date)}</a></td><td>${esc(d.day_type)}${d.status!=='complete'?`, <span class="sub">${esc(d.status)}</span>`:''}</td>` +
      cols.map(([k,,dp]) => { const e = ev[k]; const cl = e&&e.ok===true?'good':e&&e.ok===false?'bad':''; return `<td class="${cl}">${d.totals?fmt(t[k],dp):'–'}${ARROW(e)}</td>`; }).join('') +
      `<td>${d.weight?d.weight.kg+(d.weight.fasted===false?'*':''):'–'}</td><td>${esc(d.exercise.map(e=>e.type).join(', ')||'–')}</td></tr>`;
  }
  $('#weektable').innerHTML = h + `</table><p class="sub">* not fasted. Green is on target, red is missed, judged against the target that applied that day. Partial days aren't judged.</p>`;
  document.querySelectorAll('#weektable a').forEach(a => a.onclick = e => { e.preventDefault(); showTab('day'); renderDay(a.dataset.date); });
}

/* ---------- training ---------- */
let TRAIN = null, TVIEW = 'energy', TRANGE = 30;
const TYPE_LABEL = {gym:'Gym', run:'Run', swim:'Swim', ruck:'Ruck', yoga:'Yoga', walk:'Walking (steps)', other:'Other'};
const typeCol = t => css('--t-'+t);
document.querySelectorAll('#trange button').forEach(b => b.onclick = () => {
  document.querySelectorAll('#trange button').forEach(x => x.setAttribute('aria-pressed', x===b)); TRANGE = +b.dataset.d; renderTrainChart(); });
function showTrainView(v){ TVIEW = v; renderTrainChips(); renderTrainChart(); renderLiftTable();
  const el = $('#trainchart'); if(el.getBoundingClientRect().top < 0) el.scrollIntoView({behavior: MOTION?'smooth':'auto', block:'center'}); }
function liftNames(){ return Object.keys(TRAIN.lifts).sort((a,b)=>TRAIN.lifts[b].length-TRAIN.lifts[a].length || a.localeCompare(b)); }
function renderTrainChips(){
  const lifts = liftNames();
  $('#trainchips').innerHTML = `<button role="tab" data-v="energy" aria-selected="${TVIEW==='energy'}">Energy burnt</button><span class="sep"></span>` +
    lifts.map(n => `<button role="tab" data-v="${n}" aria-selected="${TVIEW===n}">${n.replace(/-/g,' ')}</button>`).join('');
  document.querySelectorAll('#trainchips button').forEach(b => b.onclick = () => showTrainView(b.dataset.v));
}
async function renderTraining(){
  TRAIN = TRAIN || await api('/api/training');
  renderTrainChips(); renderTrainChart(); renderPlan(); renderLiftTable(); renderRuns(); renderWorkouts().then(() => { renderCalendar(); renderMuscles(); });
}
/* ---------- workouts: one session in detail, Hevy + Garmin ---------- */
let WO = null, WO_SEL = null;
const WO_IC = {gym:'🏋', run:'🏃', swim:'🏊', ruck:'🎒', yoga:'🧘', other:'•'};
async function renderWorkouts(){
  WO = WO || await api('/api/workouts').catch(()=>[]);
  const el = $('#wopick'); if(!el) return;
  if(!WO.length){ el.innerHTML = '<p class="empty">No workouts logged yet.</p>'; return; }
  const list = WO.slice(0, 24);
  if(!WO_SEL) WO_SEL = `${list[0].date}|${list[0].idx}`;
  el.innerHTML = list.map(w => { const k = `${esc(w.date)}|${esc(w.idx)}`, d = new Date(w.date+'T00:00');
    const stat = w.type==='gym' ? `${esc(w.sets)} sets` : w.distance_km ? `${esc(w.distance_km)} km` : w.duration_min ? `${esc(w.duration_min)} min` : '';
    return `<button role="tab" aria-selected="${k===WO_SEL}" data-k="${k}"><span class="wd">${d.toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short'})}</span>
      <span class="wn">${WO_IC[w.type]||'•'} ${esc(w.name)}</span><span class="ws">${stat}${w.garmin?' · <span title="Garmin data">⌚</span>':''}</span></button>`; }).join('');
  el.querySelectorAll('button').forEach(b => b.onclick = () => { WO_SEL = b.dataset.k; renderWorkouts().then(() => { if(MMODE==='session') renderMuscles(); }); });
  const [date, i] = WO_SEL.split('|');
  const D = await api(`/api/workout?date=${date}&i=${i}`).catch(()=>null);
  const box = $('#wodetail'); if(!D){ box.innerHTML = ''; return; }
  const S = D.session, P = D.prev, c = theme();
  const tile = (lab, v, sub='') => `<div class="t"><div class="lab">${lab}</div><div class="v">${v}</div>${sub?`<div class="s">${sub}</div>`:''}</div>`;
  const delta = (cur, prev, unit='', dp=0) => prev==null||cur==null ? '' : `<span class="${cur>prev?'good':cur<prev?'bad':''}">${cur>prev?'▲':cur<prev?'▼':'▬'} ${cur-prev>0?'+':''}${fmt(cur-prev,dp)}${unit}</span> vs ${shortDate(P.date)}`;
  const tiles = [];
  if(S.type==='gym') tiles.push(tile('Sets · volume', `${esc(S.sets)} · ${fmt(S.volume)}<small> kg</small>`, P ? delta(S.volume, P.volume, ' kg') : ''));
  if(D.time || S.distance_km) tiles.push(tile('Distance · time', `${S.distance_km??'–'}<small> km</small> · ${D.time||'–'}`, D.time && S.distance_km ? `${pace(toSecs(D.time)/S.distance_km)} /km${D.cadence?` · cadence ${esc(D.cadence)}`:''}` : ''));
  tiles.push(tile('Duration', S.duration_min!=null?`${esc(S.duration_min)}<small> min</small>`:'–', D.trace?'':(S.garmin?'':'no watch data')));
  tiles.push(tile('Calories', D.kcal&&D.kcal.total?`${fmt(D.kcal.total)}`:'–', D.kcal&&D.kcal.active?`${fmt(D.kcal.active)} active`:''));
  tiles.push(tile('Heart rate', D.hr&&D.hr.avg?`${esc(D.hr.avg)}<small> avg</small> · ${D.hr.max||'–'}<small> max</small>`:'–'));
  if(D.hrr!=null) tiles.push(tile('Recovery HR', `${esc(D.hrr)}<small> bpm drop</small>`, `in 2 min after stopping · ${D.hrr>=40?'excellent':D.hrr>=30?'good':D.hrr>=20?'fair':'low'}${S.type==='gym'?' (noisier after lifting)':''}`));
  if(D.training_load!=null) tiles.push(tile('Training load', `${esc(D.training_load)}`, 'Garmin, this session'));
  const T = D.trace;
  if(T && (T.aerobic_te!=null)) tiles.push(tile('Training effect', `${fmt(T.aerobic_te,1)} <small>/</small> ${fmt(T.anaerobic_te,1)}`,
    `aerobic / anaerobic${T.te_label?' · '+T.te_label.toLowerCase().replace(/_/g,' '):''}`)); if(T && T.body_battery_change!=null) tiles.push(tile('Body battery', `${esc(T.body_battery_change)}`, 'cost of the session'));
  const Z = D.zones_min;
  const zbar = Z ? (() => { const tot = Object.values(Z).reduce((a,b)=>a+b,0)||1, ZC = ['#7a8597','#2a78d6','#1baf7a','#eda100','#eb6834','#C8372D'];
    return `<div class="zbar">${[1,2,3,4,5].map(k => Z['z'+k] ? `<i style="flex:${Z['z'+k]};background:${ZC[k]}" title="Zone ${k}: ${Z['z'+k]} min"><span>Z${k} ${Z['z'+k]}m</span></i>` : '').join('')}</div>`; })() : '';
  let h = `<div class="wo-head"><div><h3>${WO_IC[S.type]||''} ${esc(S.name)}</h3><span class="sub">${fmtDate(S.date)}${S.start?' · '+esc(S.start):''}${/^https:\/\//.test(D.hevy||'')?` · <a href="${esc(D.hevy)}" target="_blank" rel="noopener">Hevy</a>`:''}${D.prs?` · <span class="pr-star">★</span> ${esc(D.prs)} personal best${D.prs>1?'s':''}`:''}</span>
    ${D.note?`<div class="sub">${esc(D.note)}</div>`:''}</div></div>${coachList(D.coach)}<div class="tiles-g wo-tiles">${tiles.join('')}</div>${zbar}`;
  const L = D.laps;
  if(L && L.laps.length){
    const mm = v => `${Math.floor(v/60)}:${String(v%60).padStart(2,'0')}`;
    const ps = L.laps.map(l => l.pace_s).filter(Boolean), lo = Math.min(...ps), hi = Math.max(...ps);
    h += `<div class="notes-h"><h2 class="h3">Laps</h2><span class="sub">${esc(L.source)} · fastest lap starred</span></div>
      <table class="wo-laps"><tr><th>Lap</th><th>Distance</th><th>Time</th><th>Pace</th><th></th><th>Avg HR</th><th>Max HR</th></tr>` +
      L.laps.map((l, k) => `<tr${l.fastest?' class="pr"':''}><td>${k+1}${l.fastest?' <span class="pr-star" aria-label="fastest lap">★</span>':''}</td>
        <td>${fmt(l.km,2)} km</td><td>${mm(l.secs)}</td><td><b>${l.pace_s?mm(l.pace_s):'–'}</b><small> /km</small></td>
        <td class="lapbar"><i style="width:${l.pace_s && hi>lo ? 25 + 75*(hi-l.pace_s)/(hi-lo) : 60}%"></i></td>
        <td>${l.hr_avg??'–'}</td><td>${l.hr_max??'–'}</td></tr>`).join('') + `</table>`;
  }
  const FIT = T && T.effort_fit, CIRC = FIT && FIT.circuits;
  if(T) h += `<div class="notes-h"><h2 class="h3">Heart rate</h2><span class="sub">${T.efforts.length} effort${T.efforts.length!==1?'s':''} picked out from heart-rate peaks${T.effort_gap_min?`, about ${fmt(T.effort_gap_min,1)} min apart`:''}${S.type==='gym'&&S.sets?` (you logged ${esc(S.sets)} sets)`:''}${CIRC?` · ${esc(FIT.matched)} of ${esc(FIT.sets)} sets matched to peaks from your circuit order${FIT.exact?'':' (approximate)'}, hover a dot`:''} · zones are estimates from your highest recorded HR (${esc(D.max_hr)})</span></div><div id="wohr" class="chart" style="height:220px"></div>`;
  else if(S.garmin===false && S.type==='gym') h += `<p class="sub">No watch data for this session, so no heart-rate trace.</p>`;
  else if(S.garmin) h += `<p class="sub">No heart-rate trace saved for this session yet (recent sessions fetch it on the next Garmin sync).</p>`;
  if(D.lifts.length){
    h += `<table class="wo-lifts"><tr><th>Lift</th><th>Sets</th><th>Volume</th><th>vs last time</th><th>Last time</th></tr>` + D.lifts.map(l => {
      const ch = l.vol_change, e1 = l.e1rm_change;
      const chTxt = l.prev ? `${ch!=null?`<span class="${ch>0?'good':ch<0?'bad':''}">${ch>0?'▲ +':ch<0?'▼ ':'▬ '}${fmt(ch)} kg</span>`:''}${e1?` <span class="sub">· best set ${e1>0?'+':''}${fmt(e1,1)} kg e1RM</span>`:''}` : '<span class="sub">first time</span>';
      return `<tr${l.pr?' class="pr"':''}><td>${esc(l.name)}${l.pr?' <span class="pr-star" aria-label="personal best">★</span>':''}${l.note?`<div class="lift-note">💬 ${esc(l.note)}</div>`:''}</td><td class="sets">${(l.sets_raw||[]).map(x=>String(x).replace(/^0x/,'bw×')).join(', ')}</td>
        <td>${l.metres?`${esc(l.metres)} m`:l.volume?fmt(l.volume):`${(l.sets_raw||[]).reduce((a,x)=>a+(+(String(x).split('x')[1])||0),0)} reps`}</td><td>${chTxt}</td><td class="sub">${l.prev?`${shortDate(l.prev.date)}: ${(l.prev.sets_raw||[]).join(', ')}`:'–'}</td></tr>`; }).join('') + `</table>
      <p class="sub">Volume is weight × reps over all logged sets. ${CIRC?'Sets are matched to heart-rate peaks using the circuit order logged with this session.':"Hevy doesn't record when each set happened, so sets aren't matched to the heart-rate trace. Tell your assistant your circuit order (which lifts you loop together) and it will match them."}</p>`;
  }
  box.innerHTML = h;
  if(T){
    const B = D.zone_bounds, ZC = ['#7a8597','#2a78d6','#1baf7a','#eda100','#eb6834'];
    const lo = Math.max(40, Math.min(...T.points.map(p=>p[1])) - 5), hi = Math.max(...T.points.map(p=>p[1])) + 8;
    const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11,fontFamily:'Archivo'},splitLine:{lineStyle:{color:c.rule,opacity:.35}}};
    chart('wohr').setOption({animation:MOTION,grid:{left:44,right:16,top:10,bottom:26},
      xAxis:{type:'value',min:0,max:Math.ceil(T.points[T.points.length-1][0]),...ax,axisLabel:{...ax.axisLabel,formatter:v=>v+' min'}},
      yAxis:{type:'value',min:Math.floor(lo/10)*10,max:Math.ceil(hi/10)*10,...ax},
      tooltip:{trigger:'axis',...tip(c),formatter:ps => { const p = ps.find(x=>x.seriesName==='HR')||ps[0]; const m = p.value[0], z = B.findIndex((b,k)=>p.value[1]>=b && p.value[1]<B[k+1]);
        const EL = T.effort_labels||[]; let ei = -1, best = .5;
        T.efforts.forEach((q,k) => { const dd = Math.abs(q[0]-m); if(dd < best && EL[k]){ best = dd; ei = k; } });
        const L = ei>=0 ? EL[ei] : null;
        return `${fmt(m,1)} min · <b>${p.value[1]}</b> bpm${z>=0?` <span style="color:${c.muted}">zone ${z+1}</span>`:''}${L?`<br><b>${esc(L.name)}</b> · set ${esc(L.set)} of ${esc(L.of)} · ${esc(L.raw.replace(/^0x/,'bw×'))}`:''}`; }},
      series:[{type:'line',name:'HR',data:T.points,showSymbol:false,lineStyle:{color:'#C8372D',width:1.8},
        markArea:{silent:true,label:{show:true,position:'insideRight',color:c.muted,fontSize:10},data:[0,1,2,3,4].map(k=>[{yAxis:B[k],name:'Z'+(k+1),itemStyle:{color:ZC[k],opacity:.08}},{yAxis:B[k+1]}])}},
        {type:'scatter',name:'Efforts',data:T.efforts.map((q,k) => ({value:q, itemStyle:{color:(T.effort_labels||[])[k]||!CIRC?c.ink:c.muted, opacity:(T.effort_labels||[])[k]||!CIRC?1:.45}})),symbolSize:7,tooltip:{show:false}}]});
  }
}
/* ---------- activity calendar: a year of workouts, coloured by calories burnt ---------- */
const CAL_STEPS = [150, 300, 450, 600];   // kcal per day: <150, 150–299, 300–449, 450–599, 600+
function renderCalendar(){
  const el = $('#actcal'); if(!el || !WO) return;
  const iso = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  // Sessions with no watch calories get an estimate from the same kind of session: kcal per minute x minutes
  // when we know how long it lasted, otherwise the median for that type (or for all sessions).
  const med = a => { if(!a.length) return null; const v = [...a].sort((x,y)=>x-y), m = v.length>>1; return v.length%2 ? v[m] : (v[m-1]+v[m])/2; };
  const known = WO.filter(w => w.kcal), allMed = med(known.map(w => w.kcal));
  const estK = w => { const same = known.filter(x => x.type===w.type);
    const rate = med(same.filter(x => x.duration_min).map(x => x.kcal/x.duration_min));
    if(rate && w.duration_min) return Math.round(rate*w.duration_min);
    return Math.round(med(same.map(x => x.kcal)) ?? allMed ?? 0); };
  WO.forEach(w => { w.kcal_est = w.kcal ? null : estK(w); });
  const byDay = {};
  WO.forEach(w => { const b = byDay[w.date] = byDay[w.date] || {kcal:0, est:false, items:[]};
    b.kcal += w.kcal || w.kcal_est || 0; if(!w.kcal) b.est = true; b.items.push(w); });
  const today = new Date(); today.setHours(0,0,0,0);
  const start = new Date(today); start.setDate(start.getDate() - 364);
  start.setDate(start.getDate() - ((start.getDay()+6)%7));          // back to Monday
  const level = k => k <= 0 ? 0 : 1 + CAL_STEPS.filter(s => k >= s).length;
  let cells = '', months = '', lastM = -1, col = 0;
  for(const d = new Date(start); d <= today; d.setDate(d.getDate()+1)){
    const dow = (d.getDay()+6)%7; if(dow===0){ col++; if(d.getMonth()!==lastM && d.getDate()<=7){ lastM = d.getMonth();
      months += `<span style="grid-column:${col+1}">${d.toLocaleDateString('en-GB',{month:'short'})}</span>`; } }
    const k = iso(d), b = byDay[k];
    let cls = 'l0', tip = `${d.toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short',year:'numeric'})}: rest`;
    if(b){
      cls = b.est ? 'lx' : 'l'+level(b.kcal);
      tip = `${d.toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short',year:'numeric'})}: ${b.est?'~':''}${fmt(b.kcal)} kcal${b.est?' (estimated)':''}\n` +
        b.items.map(w => `${WO_IC[w.type]||'•'} ${esc(w.name)} · ${w.kcal?fmt(w.kcal)+' kcal':`~${fmt(w.kcal_est)} kcal estimated, no watch data`}${w.duration_min?` · ${esc(w.duration_min)} min`:''}`).join('\n'); }
    cells += `<i class="${cls}" style="grid-column:${col+1};grid-row:${dow+2}" title="${esc(tip)}"${b?` data-k="${b.items[0].date}|${b.items[0].idx}" tabindex="0" role="button"`:''}></i>`;
  }
  const days = ['Mon','','Wed','','Fri','',''].map((t,i) => `<b style="grid-row:${i+2}">${t}</b>`).join('');
  const key = `<div class="cal-key"><span>Calories burnt</span><i class="l0" title="Rest"></i>${[1,2,3,4,5].map(l => `<i class="l${l}" title="${l===1?'under '+CAL_STEPS[0]:l===5?CAL_STEPS[3]+'+':CAL_STEPS[l-2]+'–'+(CAL_STEPS[l-1]-1)} kcal"></i>`).join('')}
    <span>${CAL_STEPS[3]}+ kcal</span><i class="lx" title="No watch calories: estimated from similar sessions"></i><span>estimated</span></div>`;
  el.innerHTML = `<div class="cal-grid" style="grid-template-columns:28px repeat(${col},minmax(6px,1fr))">${months}${days}${cells}</div>${key}`;
  const first = WO.reduce((m, w) => w.date < m ? w.date : m, WO[0].date);
  const span = Math.round((today - new Date(first+'T00:00')) / 864e5) + 1;
  const allK = WO.reduce((a, w) => a + (w.kcal || w.kcal_est || 0), 0), nEst = WO.filter(w => !w.kcal).length;
  $('#calnote').textContent = `${WO.length} sessions in the last ${fmt(span)} days · ${fmt(allK)} kcal (${fmt(allK/7700,1)} kilos of fat) from workouts`;
  $('#calnote').title = `Using about 7,700 kcal per kilo of body fat.${nEst?` Includes estimates for ${nEst} session${nEst>1?'s':''} with no watch calories.`:''}`;
  el.querySelectorAll('i[data-k]').forEach(c => { const go = () => { WO_SEL = c.dataset.k; renderWorkouts().then(() => { if(MMODE==='session') renderMuscles(); });
      $('#wopick').scrollIntoView({behavior: MOTION?'smooth':'auto', block:'start'}); };
    c.onclick = go; c.onkeydown = e => { if(e.key==='Enter'||e.key===' '){ e.preventDefault(); go(); } }; });
  const wrap = el.parentElement; wrap.scrollLeft = wrap.scrollWidth;
}
/* ---------- muscle map: sets per muscle, hover a muscle for the lifts behind it ---------- */
let MMODE = '7';
document.querySelectorAll('#mrange button').forEach(b => b.onclick = () => {
  document.querySelectorAll('#mrange button').forEach(x => x.setAttribute('aria-pressed', x===b)); MMODE = b.dataset.m; renderMuscles(); });
async function renderMuscles(){
  const box = $('#musclemap'); if(!box || !window.BODYMAP) return;
  let url = `/api/muscles?days=${MMODE}`, what = `the last ${MMODE} days`, over = `over ${what}`;
  if(MMODE === 'session'){
    if(!WO_SEL){ box.innerHTML = '<p class="empty">Pick a workout above.</p>'; return; }
    const [date, i] = WO_SEL.split('|'); url = `/api/muscles?date=${date}&i=${i}`; what = `this workout (${shortDate(date)})`; over = `in ${what}`;
  }
  const M = await api(url).catch(() => null); if(!M){ box.innerHTML = ''; return; }
  const R = M.regions, days = MMODE === 'session' ? 0 : +MMODE;
  // shade by sets: per session 1/2/4/6+, otherwise per week 1/6/10/16+ scaled to the window
  const cut = days ? [1, 6, 10, 16].map(v => v * days / 7) : [1, 2, 4, 6];
  const lvl = v => !v ? 0 : v >= cut[3] ? 4 : v >= cut[2] ? 3 : v >= cut[1] ? 2 : 1;
  const leg = days ? ['0', `1–${Math.round(cut[1]-1)}`, `${Math.round(cut[1])}–${Math.round(cut[2]-1)}`, `${Math.round(cut[2])}–${Math.round(cut[3]-1)}`, `${Math.round(cut[3])}+`]
                   : ['0', '1', '2–3', '4–5', '6+'];
  const fig = (side, title) => `<figure><figcaption>${title}</figcaption><svg viewBox="0 0 100 200" role="img" aria-label="${title} muscles">${
    BODYMAP[side].map(([r, pts]) => r ? `<polygon class="m" data-r="${r}" points="${pts}" fill="var(--m${lvl(R[r].sets)})"><title>${esc(R[r].label)}: ${fmt(R[r].sets,1)} sets</title></polygon>`
                                      : `<polygon points="${pts}" fill="var(--mbody)"/>`).join('')}</svg></figure>`;
  const gaps = M.untrained.map(r => R[r].label.toLowerCase());
  $('#mnote').textContent = `Hard sets per muscle ${over}; warm-ups excluded, a secondary muscle counts half a set, and runs and other cardio count one set per 10 minutes. Hover or tap a muscle to see the lifts and runs behind it.` +
    (gaps.length && MMODE !== 'session' ? ` Not trained: ${gaps.join(', ')}.` : '') + (M.untagged.length ? ` No muscles tagged in exercises.yaml for: ${M.untagged.join(', ')}.` : '');
  const info = r => { const x = R[r];
    if(!x.lifts.length) return `<h4>${esc(x.label)}</h4><p class="sub">Not trained in ${what}.</p>`;
    return `<h4>${esc(x.label)} · ${fmt(x.sets,1)} sets</h4><ul>${x.lifts.map(l => `<li><span>${esc(l.name)}${l.role==='secondary'?' <span class="r">(secondary, counts half)</span>':''}</span>
      <span class="r">${l.minutes!=null?`${esc(l.minutes)} min ≈ ${fmt(l.sets,1)} set${l.sets!==1?'s':''}`:`${esc(l.sets)} set${l.sets!==1?'s':''}`}${days?` · ${[...new Set(l.dates)].map(shortDate).join(', ')}`:''}</span></li>`).join('')}</ul>`; };
  const top = Object.keys(R).filter(r => R[r].sets).sort((a, b) => R[b].sets - R[a].sets)[0];
  box.innerHTML = fig('front', 'Front') + fig('back', 'Back') + `<div class="mside"><div class="mlegend">${leg.map((t, k) => `<span><i style="background:var(--m${k})"></i>${t}${k===0?' sets':''}</span>`).join('')}</div>
    <div class="mtip" id="mtip">${top ? info(top) : `<p class="sub">${MMODE==='session' ? 'Nothing to show for this workout.' : 'No lifts logged in this period.'}</p>`}</div></div>`;
  const show = r => { $('#mtip').innerHTML = info(r); box.querySelectorAll('polygon.m').forEach(p => p.classList.toggle('hl', p.dataset.r === r)); };
  box.querySelectorAll('polygon.m').forEach(p => { p.onmouseenter = () => show(p.dataset.r); p.onclick = () => show(p.dataset.r); });
  if(top) show(top);
}
function renderTrainChart(){
  if(TVIEW === 'energy') renderEnergy(); else renderLift(TVIEW);
}
function renderEnergy(){
  const c = theme(), E = TRAIN.energy;
  let days = E.days; if(TRANGE) days = days.slice(-TRANGE);
  const types = E.types.filter(t => days.some(d => d.sessions.some(s => s.type===t)));
  const x = days.map(d => shortDate(d.date));
  const totals = days.map(d => d.sessions.reduce((a,s)=>a+s.kcal,0));
  const sess = days.flatMap(d => d.sessions.filter(s => s.type!=='walk'));
  const nEst = sess.filter(s=>s.estimated).length, nSteps = days.filter(d=>d.steps).length;
  $('#trainnote').textContent = `Calories burnt, stacked by activity, with daily steps below. ${nEst} of ${sess.length} sessions are estimated from your own measured sessions (hatched); walking burn is estimated from steps, minus steps already inside runs and rucks. Steps recorded on ${nSteps} of ${days.length} days so far — the Garmin pull fills these in daily.`;
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule}}};
  const series = types.map((t, ti) => ({type:'bar', name:TYPE_LABEL[t], stack:'kcal', barMaxWidth:24, barCategoryGap:'30%',
    itemStyle:{color:typeCol(t)},   // series colour drives the legend key; bars below set their own (solid or hatched)
    animationDelay: k => k*10,
    data: days.map((d, di) => {
      const ss = d.sessions.filter(s => s.type===t); if(!ss.length) return null;
      const v = ss.reduce((a,s)=>a+s.kcal,0), est = ss.every(s=>s.estimated);
      // round only the top segment of each stack
      const above = types.slice(ti+1).some(u => d.sessions.some(s => s.type===u));
      return {value:v, itemStyle:{color: est ? hatch(typeCol(t), c.surface) : typeCol(t), opacity: est ? .8 : 1,
        borderColor:c.surface, borderWidth:1, borderRadius: above ? 0 : [4,4,0,0]}};
    })}));
  series.push({type:'line', name:'7-day average', symbol:'none', smooth:.3, lineStyle:{color:c.ink, width:2}, itemStyle:{color:c.ink},
    data: totals.map((_, i) => { const w = totals.slice(Math.max(0,i-6), i+1); return Math.round(w.reduce((a,b)=>a+b,0)/w.length); }),
    endLabel:{show:true,color:c.ink,fontSize:11,fontWeight:600,formatter:p=>`${fmt(p.value)} avg`}});
  const steps = days.map(d => d.steps ?? null), sref = E.steps_ref;
  series.push({type:'bar', name:'Steps', xAxisIndex:1, yAxisIndex:1, barMaxWidth:24, barCategoryGap:'30%',
    data: steps.map(v => v==null ? null : {value:v, itemStyle:{color: v>=sref ? typeCol('walk') : hatch(typeCol('walk'), c.surface), borderRadius:[4,4,0,0]}}),
    markLine:{symbol:'none',silent:true,data:[{yAxis:sref}],lineStyle:{color:c.ink,type:'dashed',opacity:.6},label:{formatter:`${fmt(sref)} (July average)`,color:c.ink,position:'insideEndTop'}}});
  chart('trainchart').setOption({animation:MOTION,animationDuration:550,animationEasing:'cubicOut',textStyle:{fontFamily:'Archivo'},
    title:[{text:'Steps',left:56,top:282,textStyle:{fontSize:12.5,fontWeight:600,color:c.ink,fontFamily:'Archivo'}}],
    legend:{top:0,left:56,itemWidth:12,itemHeight:10,itemGap:16,textStyle:{color:c.muted},data:[...types.map(t=>TYPE_LABEL[t]),'7-day average']},
    grid:[{left:66,right:76,top:40,height:220},{left:66,right:76,top:306,height:96}],
    xAxis:[0,1].map(i => ({type:'category',gridIndex:i,data:x,...ax,axisTick:{show:false},axisLabel:{...ax.axisLabel,show:i===1}})),
    yAxis:[{type:'value',gridIndex:0,...ax,...niceRange(0, Math.max(...totals, 100), 4, true),name:'kcal burnt',nameLocation:'middle',nameGap:42,nameRotate:90,nameTextStyle:{color:c.muted,fontSize:11}},
           {type:'value',gridIndex:1,...ax,...niceRange(0, Math.max(sref, ...steps.filter(v=>v!=null)), 2, true),axisLabel:{...ax.axisLabel,formatter:v=>v>=1000?(v/1000)+'k':v}}],
    axisPointer:{link:[{xAxisIndex:'all'}],lineStyle:{color:c.muted}},
    tooltip:{trigger:'axis',...tip(c),formatter: ps => { const d = days[ps[0].dataIndex];
      const st = `<br>Steps ${d.steps!=null?fmt(d.steps):'not recorded'}`;
      if(!d.sessions.length) return `<b>${fmtDate(d.date)}</b><br>Rest day${st}`;
      return `<b>${fmtDate(d.date)}</b> · ${fmt(totals[ps[0].dataIndex])} kcal${st}<br>` + d.sessions.map(s =>
        `<span class="key" style="background:${typeCol(s.type)}"></span>${TYPE_LABEL[s.type]}${s.effort?' ('+s.effort+')':''}${s.desc?' · '+s.desc:''} · ${fmt(s.kcal)} kcal${s.estimated?' <i>estimated</i>':''}`).join('<br>'); }},
    series});
  // relief table: weekly totals by type (also covers low-contrast colours)
  const weeks = {};
  for(const d of days){ const dt = new Date(d.date+'T00:00'); const mon = new Date(dt); mon.setDate(dt.getDate() - ((dt.getDay()+6)%7));
    const k = `${mon.getFullYear()}-${String(mon.getMonth()+1).padStart(2,'0')}-${String(mon.getDate()).padStart(2,'0')}`;
    weeks[k] = weeks[k] || {stepsSum:0, stepDays:0};
    if(d.steps){ weeks[k].stepsSum += d.steps; weeks[k].stepDays++; }
    for(const s of d.sessions){ weeks[k][s.type] = (weeks[k][s.type]||0) + s.kcal; if(s.type!=='walk') weeks[k].n = (weeks[k].n||0)+1; } }
  $('#traintable').innerHTML = `<table><tr><th>Week of</th>${types.map(t=>`<th><span class="key" style="background:${typeCol(t)}"></span>${TYPE_LABEL[t]}</th>`).join('')}<th>Sessions</th><th>Avg steps</th><th>Total kcal</th></tr>` +
    Object.entries(weeks).reverse().map(([w,v]) => `<tr><td>${shortDate(w)}</td>${types.map(t=>`<td>${v[t]?fmt(v[t]):'–'}</td>`).join('')}<td>${v.n||0}</td><td>${v.stepDays?fmt(v.stepsSum/v.stepDays):'–'}</td><td><b>${fmt(types.reduce((a,t)=>a+(v[t]||0),0))}</b></td></tr>`).join('') + `</table>`;
}
function renderLift(name){
  const c = theme();
  const pts = TRAIN.lifts[name] || [];
  const carry = pts.some(p => p.metres);
  $('#trainnote').textContent = `${name.replace(/-/g,' ')}: ` + (carry ? 'load carried per set.' : 'top set each session, with estimated one-rep max dashed. Gold points are new bests.') + (pts.length < 4 ? ' History before 9 Oct is partial; pasted Hevy workouts fill it in.' : '');
  $('#traintable').innerHTML = '';
  const swapIdx = pts.findIndex(p=>p.epoch==='v2');
  const vals = [...pts.map(p=>p.kg), ...(carry?[]:pts.map(p=>p.e1rm))];
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule}}};
  chart('trainchart').setOption({animation:MOTION,animationDuration:500,textStyle:{fontFamily:'Archivo'},
    legend:{top:0,left:56,textStyle:{color:c.muted},data:carry?[]:['Top set kg','Est. 1RM']},
    grid:{left:66,right:40,top:40,bottom:34},
    tooltip:{trigger:'axis',...tip(c),formatter: ps => { const p = pts[ps[0].dataIndex];
      return `<b>${fmtDate(p.date)}</b><br>${esc(p.kg)} kg${p.reps?' × '+p.reps:''}${p.metres?' for '+p.metres+' m':''}${p.reps?'<br>est. 1RM '+p.e1rm+' kg':''}${p.pr?'<br><b>New best</b>':''}${p.epoch?'<br>'+(p.epoch==='v2'?'new':'old')+' machines':''}`; }},
    xAxis:{type:'category',data:pts.map(p=>shortDate(p.date)),...ax,axisTick:{show:false}},
    yAxis:{type:'value',...ax,...niceRange(Math.min(...vals)-2, Math.max(...vals)+2, 4),name:'kg',nameLocation:'middle',nameGap:42,nameRotate:90,nameTextStyle:{color:c.muted,fontSize:11}},
    series:[
      {type:'line',name:'Top set kg',symbol:'circle',data:pts.map(p=>({value:p.kg,symbolSize:p.pr?13:9,itemStyle:{color:p.pr?c.warn:c.accent,...ring(c)}})),lineStyle:{color:c.accent,width:2},
        areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:c.soft},{offset:1,color:'rgba(0,0,0,0)'}])},
        endLabel:{show:true,color:c.ink,fontWeight:600,fontSize:11,formatter:p=>p.value+' kg'},
        markLine: swapIdx>0 ? {symbol:'none',silent:true,label:{formatter:'new machines',color:c.muted},lineStyle:{color:c.muted,type:'dotted'},data:[{xAxis:swapIdx}]} : undefined},
      ...(carry?[]:[{type:'line',name:'Est. 1RM',data:pts.map(p=>p.e1rm),lineStyle:{color:c.accent,type:'dashed',opacity:.5,width:2},symbol:'none'}])
    ]});
}
async function renderPlan(){
  const p = await api('/api/plan').catch(()=>null); if(!p) return;
  const i = p.info, [vlo, vhi] = i.weekly_sets_guide;
  const banner = i.deload_now
    ? `<div class="focus"><b>Deload week</b> (week ${esc(i.week)} of the block): same weights, 2 sets instead of 3, stop 2–3 reps short of failure.</div>`
    : `<p class="sub">Week ${esc(i.week)} of the block that started ${shortDate(i.block_start)}. Next deload: week of ${shortDate(i.next_deload_week_of)}. Double progression, ${i.rep_range[0]}–${i.rep_range[1]} reps, ${esc(i.working_sets)} working sets.</p>`;
  const rows = p.lifts.map(r => `<tr data-lift="${esc(r.lift)}" tabindex="0"><td>${r.lift.replace(/-/g,' ')}</td><td><span class="sub">${shortDate(r.last_date)}</span> ${esc(r.last)}</td><td><b>${esc(r.target)}</b></td><td class="sub" style="white-space:normal">${esc(r.rule)}</td></tr>`).join('');
  const muscles = [...new Set(p.volume.flatMap(w => Object.keys(w.sets)))].sort();
  const vol = muscles.length ? `<h3 style="font-size:14px;margin:18px 0 6px">Working sets per muscle, per week <span class="sub">(general guide ${vlo}–${vhi} for growth; warm-ups excluded; secondary muscles count half)</span></h3>
    <table><tr><th>Muscle</th>${p.volume.map(w=>`<th>${shortDate(w.week_of)}</th>`).join('')}</tr>` +
    muscles.map(m => `<tr><td>${m}</td>${p.volume.map(w => { const v = w.sets[m]; const cl = v==null?'':v>=vlo&&v<=vhi?'good':v<vlo?'':'bad'; return `<td class="${cl}">${v??'–'}</td>`; }).join('')}</tr>`).join('') + `</table>
    <p class="sub">Volume is low partly because past workouts were only partly logged. Pasted Hevy workouts give full sets from here on.</p>` : '';
  const W = p.week, IC = {gym:'🏋', run:'🏃', rest:'💤'};
  const week = W ? `<h3 style="font-size:14px;margin:4px 0 6px">This week</h3><table class="wk-plan">${W.days.map((d, k) => `<tr${k===0?' class="today"':''}>
      <td><b>${k===0?'Today':new Date(d.date+'T00:00').toLocaleDateString('en-GB',{weekday:'short'})}</b><br><span class="sub">${shortDate(d.date)}</span></td>
      <td>${IC[d.kind]||'•'} <b>${esc(d.name||d.kind)}</b>${d.step?` · <b>${esc(d.step)}</b>`:''}${d.detail?`<div class="sub">${esc(d.detail)}</div>`:''}${d.kind==='gym'&&W.every_gym.length?`<div class="sub">Plus: ${W.every_gym.map(esc).join(' · ')}</div>`:''}</td></tr>`).join('')}</table>
    ${W.run_test&&W.run_test.next?`<p class="sub">Next run test: <b>${shortDate(W.run_test.next)}</b>${W.run_test.baseline?` (baseline ${esc(W.run_test.baseline.time)}, ${esc(W.run_test.baseline.what||'')}, ${shortDate(W.run_test.baseline.date)})`:''}. ${esc(W.run_test.note||'')}</p>`:''}
    ${W.tendon_rule?`<p class="sub">⚠️ ${esc(W.tendon_rule)}</p>`:''}<h3 style="font-size:14px;margin:16px 0 6px">Lifts</h3>` : '';
  $('#plan').innerHTML = week + banner + `<table><tr><th>Lift</th><th>Last time</th><th>Next target</th><th>Why</th></tr>${rows}</table>` + vol;
  document.querySelectorAll('#plan tr[data-lift]').forEach(r => { r.style.cursor = 'pointer'; r.onclick = () => showTrainView(r.dataset.lift); });
}
function renderLiftTable(){
  const names = liftNames();
  const rows = names.map(n => { const ps = TRAIN.lifts[n]; const best = ps.reduce((a,b)=>b.e1rm>a.e1rm?b:a); const last = ps[ps.length-1];
    const s = p => `${esc(p.kg)}${p.reps?' × '+p.reps:''}${p.metres?' kg, '+p.metres+' m':''}`;
    return `<tr data-lift="${n}" aria-selected="${TVIEW===n}" tabindex="0"><td>${n.replace(/-/g,' ')}</td><td>${s(last)}</td><td>${shortDate(last.date)}</td><td>${s(best)}</td><td>${shortDate(best.date)}</td><td>${ps.length}</td></tr>`; });
  $('#lifttable').innerHTML = `<table><tr><th>Lift</th><th>Latest</th><th>When</th><th>Best</th><th>When</th><th>Sessions</th></tr>${rows.join('')}</table>`;
  document.querySelectorAll('#lifttable tr[data-lift]').forEach(r => {
    r.onclick = () => showTrainView(r.dataset.lift);
    r.onkeydown = e => { if(e.key==='Enter'||e.key===' '){ e.preventDefault(); showTrainView(r.dataset.lift); } };
  });
}
function renderRuns(){
  const c = theme();
  const runs = TRAIN.runs, R = TRAIN.reference;
  const rx = runs.map(r=>shortDate(r.date));
  const rax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule}}};
  const RT = (text,top) => ({text,left:56,top,textStyle:{fontSize:12.5,fontWeight:600,color:c.ink,fontFamily:'Archivo'}});
  const paces = runs.map(r=>r.pace), hrs_ = runs.map(r=>r.avg_hr).filter(v=>v!=null);
  chart('runchart').setOption({animation:MOTION,animationDuration:500,textStyle:{fontFamily:'Archivo'},
    title:[RT('Distance, km',0),RT('Pace, min/km (higher is faster)',138),RT('Average heart rate, bpm',310)],
    grid:[{left:56,right:24,top:24,height:90},{left:56,right:24,top:162,height:122},{left:56,right:24,top:334,height:96}],
    xAxis:[0,1,2].map(i=>({type:'category',gridIndex:i,data:rx,...rax,axisLabel:{...rax.axisLabel,show:i===2},axisTick:{show:false}})),
    yAxis:[{type:'value',gridIndex:0,...rax,...niceRange(0, Math.max(...runs.map(r=>r.km||0)), 2, true)},
           {type:'value',gridIndex:1,inverse:true,...rax,...niceRange(Math.min(...paces)-10, Math.max(...paces)+10, 3),axisLabel:{...rax.axisLabel,formatter:v=>pace(v)}},
           {type:'value',gridIndex:2,...rax,...niceRange(Math.min(R.easy_run_avg_hr_max, ...hrs_)-5, Math.max(R.easy_run_avg_hr_max, ...hrs_)+5, 2)}],
    axisPointer:{link:[{xAxisIndex:'all'}],lineStyle:{color:c.muted}},
    tooltip:{trigger:'axis',...tip(c),formatter: ps => { const r = runs[ps[0].dataIndex];
      return `<b>${fmtDate(r.date)}</b><br>${[r.effort,r.mode].filter(Boolean).join(', ')||'run'}<br>${esc(r.km)} km in ${pace(r.secs)} · ${pace(r.pace)}/km${r.avg_hr?`<br>avg HR ${esc(r.avg_hr)}${r.max_hr?' / max '+r.max_hr:''}`:''}${r.hrr!=null?`<br>recovery HR: dropped ${esc(r.hrr)} bpm in 2 min`:''}${r.temp_c?`<br>${esc(r.temp_c)}°C`:''}`; }},
    series:[
      {type:'bar',name:'Distance',xAxisIndex:0,yAxisIndex:0,data:runs.map(r=>r.km),barMaxWidth:22,itemStyle:{color:'#eb6834',borderRadius:[4,4,0,0]},
        label:{show:runs.length<=30,position:'top',color:c.ink,fontSize:10,formatter:p=>p.value!=null?fmt(p.value,1):''}},
      {type:'line',name:'Pace',xAxisIndex:1,yAxisIndex:1,data:paces,symbol:'circle',symbolSize:9,smooth:.25,lineStyle:{color:c.accent,width:2},itemStyle:{color:c.accent,...ring(c)},
        areaStyle:{origin:'end',color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(0,0,0,0)'},{offset:1,color:c.soft}])}},
      {type:'line',name:'Average HR',xAxisIndex:2,yAxisIndex:2,data:runs.map(r=>r.avg_hr),connectNulls:true,symbol:'circle',symbolSize:9,lineStyle:{color:c.ink,width:2},
        itemStyle:{color:c.ink,...ring(c)},
        markLine:{symbol:'none',silent:true,data:[{yAxis:R.easy_run_avg_hr_max}],lineStyle:{color:c.good,type:'dashed'},label:{formatter:`easy runs ≤ ${R.easy_run_avg_hr_max}`,color:c.ink,position:'insideEndTop'}}}]});
}

/* ---------- recovery ---------- */
const hrs = s => { const m = /(\d+)h(\d+)m/.exec(s||''); return m ? +m[1] + m[2]/60 : null; };
const hm = v => v==null ? '–' : `${Math.floor(v)}h${String(Math.round((v%1)*60)).padStart(2,'0')}`;
let REF = null;
let READY = null;
async function renderReadiness(){
  READY = READY || await api('/api/readiness');
  const c = theme(), S = READY.series.filter(s => s.score != null), bt = READY.backtest;
  const names = {rhr:'resting HR up', hrv:'HRV down', sleep_debt_h:'short sleep', load:'training load spike', stress:'stress up', bb:'low body battery', feel:'feeling off'};
  $('#readynote').innerHTML = `Today's state compared with your own last 4 weeks: 100 means nothing is off. Green 70+, amber 50–69, red under 50. ` +
    `<b>It is not a forecast.</b> Tested against your ${esc(bt.of)} recorded off-episodes (shaded), it warned ahead of ${esc(bt.flagged)}; ` +
    `${esc(bt.ordinary_days_below_pct)}% of ordinary days dip into red. Log a daily feel score and new episodes so it can be re-tested.`;
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule}}};
  const x = S.map(s => s.date);
  const areas = READY.episodes.map(e => [{xAxis: x.find(d => d >= e.start) || e.start, itemStyle:{color:'rgba(200,55,45,.10)'}, name: e.what}, {xAxis: [...x].reverse().find(d => d <= e.end) || e.end}]);
  chart('readychart').setOption({animation:MOTION,animationDuration:500,textStyle:{fontFamily:'Archivo'},grid:{left:44,right:20,top:16,bottom:30},
    xAxis:{type:'category',data:x,...ax,axisTick:{show:false},axisLabel:{...ax.axisLabel,formatter:v=>shortDate(v)}},
    yAxis:{type:'value',min:0,max:100,interval:25,...ax},
    tooltip:{trigger:'axis',...tip(c),formatter: ps => { const s = S[ps[0].dataIndex];
      const ep = READY.episodes.find(e => s.date >= e.start && s.date <= e.end);
      return `<b>${fmtDate(s.date)}</b><br>Readiness ${esc(s.score)} (${esc(s.band)})${s.drivers.length?'<br>'+s.drivers.map(k=>names[k]).join(', '):''}${s.sleep_debt_h?`<br>3-night sleep shortfall ${esc(s.sleep_debt_h)} h`:''}${ep?`<br><b>Off episode:</b> ${esc(ep.what)}`:''}`; }},
    series:[{type:'line',name:'Readiness',smooth:.3,symbol:'circle',symbolSize:7,lineStyle:{color:c.ink,width:2},
      data:S.map(s => ({value:s.score,itemStyle:{color:s.band==='green'?c.good:s.band==='amber'?c.warn:c.bad,...ring(c)}})),
      markArea:{silent:true,label:{show:false},data:areas},
      markLine:{symbol:'none',silent:true,lineStyle:{type:'dashed',color:c.muted},label:{color:c.ink,position:'insideEndTop',fontSize:11},
        data:[{yAxis:70,label:{formatter:'70 green'}},{yAxis:50,label:{formatter:'50 red below'}}]}}]});
}
async function renderRecovery(){
  REF = REF || await api('/api/reference');
  renderReadiness();
  api('/api/sleep').then(S => { SLEEP = S; const el = $('#rec-sleep'); if(!S || !S.available || !el) return;
    const L = S.last;
    el.innerHTML = `Last night ${esc(mh(L.asleep))} asleep${L.score?`, score ${esc(L.score)}`:''}${S.tonight?`. Tonight: in bed by <b>${esc(S.tonight.in_bed)}</b>`:''}. <a href="#sleep" id="rec-sleep-go">Sleep in detail →</a>`;
    $('#rec-sleep-go').addEventListener('click', e => { e.preventDefault(); showTab('sleep'); }); }).catch(() => {});
  const c = theme(), days = SUMMARY.filter(d => d.recovery);
  $('#recnote').textContent = days.length < 10 ? `${days.length} nights recorded so far, from past chats. This fills in automatically once the Garmin pull is running.` : '';
  const x = days.map(d=>shortDate(d.date));
  const sleep = days.map(d => hrs(d.recovery.sleep)), hrv = days.map(d => d.recovery.hrv_ms ?? null), rhr = days.map(d => d.recovery.rhr ?? null);
  const nn = a => a.filter(v => v!=null);
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule,opacity:.5}}};
  const T = (text,top) => ({text,left:52,top,textStyle:{fontSize:12.5,fontWeight:600,color:c.ink,fontFamily:'Archivo'}});
  const ref = (v, col, label) => ({symbol:'none',silent:true,data:[{yAxis:v}],lineStyle:{color:col,type:'dashed'},label:{formatter:label,color:col,position:'insideEndTop'}});
  chart('recchart').setOption({animation:MOTION,animationDuration:500,textStyle:{fontFamily:'Archivo'},
    title:[T('Sleep, hours',0),T('Overnight HRV, ms',175),T('Resting heart rate',350)],
    grid:[{left:52,right:20,top:24,height:128},{left:52,right:20,top:199,height:128},{left:52,right:20,top:374,height:108}],
    xAxis:[0,1,2].map(i=>({type:'category',gridIndex:i,data:x,...ax,axisLabel:{...ax.axisLabel,show:i===2}})),
    yAxis:[{type:'value',gridIndex:0,...ax,...niceRange(0, Math.max(9, ...nn(sleep)), 3, true),axisLabel:{...ax.axisLabel,formatter:v=>v+'h'}},
           {type:'value',gridIndex:1,...ax,...niceRange(Math.min(REF.hrv_baseline_ms, ...nn(hrv)) - 3, Math.max(REF.hrv_baseline_ms, ...nn(hrv)) + 3, 3)},
           {type:'value',gridIndex:2,...ax,...niceRange(Math.min(REF.rhr_walk_only, ...nn(rhr)) - 2, Math.max(REF.rhr_walk_only, ...nn(rhr)) + 2, 3)}],
    tooltip:{trigger:'axis',...tip(c),formatter: ps => { const i = ps[0].dataIndex, d = days[i];
      return `<b>${fmtDate(d.date)}</b><br>Sleep ${hm(sleep[i])}${d.recovery.sleep_score?` · score ${esc(d.recovery.sleep_score)}`:''}<br>HRV ${hrv[i]??'–'} ms${d.recovery.hrv_status?' · '+d.recovery.hrv_status:''}<br>Resting HR ${rhr[i]??'–'}${d.recovery.body_battery?`<br>Body battery +${esc(d.recovery.body_battery)}`:''}${d.recovery.note?`<br><span style="color:${c.muted}">${esc(d.recovery.note)}</span>`:''}`; }},
    axisPointer:{link:[{xAxisIndex:'all'}],lineStyle:{color:c.muted}},
    series:[
      {type:'bar',name:'Sleep',xAxisIndex:0,yAxisIndex:0,barMaxWidth:24,
        data:sleep.map(v => v==null?null:{value:+v.toFixed(2),itemStyle:{color:v>=REF.sleep_hours_min?c.good:hatch(c.bad,c.surface),borderRadius:[4,4,0,0]}}),
        markLine:ref(REF.sleep_hours_min, c.good, 'target 7h30')},
      {type:'line',name:'HRV',xAxisIndex:1,yAxisIndex:1,data:hrv,connectNulls:true,smooth:.3,symbol:'circle',symbolSize:7,lineStyle:{color:c.accent,width:2},itemStyle:{color:c.accent,...ring(c)},symbolSize:9,
        areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:c.soft},{offset:1,color:'rgba(0,0,0,0)'}])},
        markLine:ref(REF.hrv_baseline_ms, c.accent, `baseline ${esc(REF.hrv_baseline_ms)} ms`)},
      {type:'line',name:'Resting HR',xAxisIndex:2,yAxisIndex:2,data:rhr,connectNulls:true,smooth:.3,symbol:'circle',symbolSize:7,lineStyle:{color:c.ink,width:2},itemStyle:{color:c.ink,...ring(c)},symbolSize:9,
        markLine:ref(REF.rhr_walk_only, c.bad, `${esc(REF.rhr_walk_only)}+ = walk only`)},
    ]});
}

/* ---------- body ---------- */
let BODY = null;
// 7-day trend: mean of fasted weigh-ins in the 7 days up to each weigh-in.
function rolling7(pts){
  return pts.map(([d]) => { const t = new Date(d); const win = pts.filter(([e]) => { const u = new Date(e); return u <= t && (t-u) < 7*864e5; });
    return [d, +(win.reduce((a,[,v])=>a+v,0)/win.length).toFixed(2)]; });
}
async function renderGlucoseOverview(){
  const O = await api('/api/glucose_overview?days=14').catch(()=>null);
  const c = theme();
  if(!O || !O.days.length){ $('#gnote').textContent = 'No glucose readings yet. They appear here once the FreeStyle Libre has been running for a while.'; $('#gprofile').style.display='none'; return; }
  const ov = O.overall, [lo, hi] = O.range;
  $('#gprofile').style.display = '';
  $('#gnote').innerHTML = `FreeStyle Libre, ${shortDate(O.from)} – ${shortDate(O.to)} (${O.days.length} day${O.days.length!==1?'s':''}).` +
    (ov ? ` Average <b>${fmt(ov.mean,1)}</b> mmol/L · time in range 3.9–7.8 <b>${fmt(ov.tir,0)}%</b> · variability <b>${fmt(ov.cv,0)}%</b> · estimated HbA1c (GMI) <b>${fmt(ov.gmi,1)}%</b>.` : '') +
    ` ${O.days.length < 7 ? 'The 24-hour profile below gets reliable after about a week.' : ''}`;
  $('#gdays').innerHTML = `<table class="g-days"><tr><th>Day</th><th class="num">Readings</th><th class="num">Average</th><th class="num">In range</th><th class="num">Variability</th><th class="num">High / low</th><th class="num">Overnight</th></tr>${[...O.days].reverse().map(d => `<tr>
    <td>${shortDate(d.date)}${d.settling?' <span class="tag">settling in</span>':''}</td><td class="num">${esc(d.n)}</td>
    <td class="num">${d.mean!=null?fmt(d.mean,1):'–'}</td><td class="num ${d.tir==null?'':d.tir>=95?'good':d.tir<85?'bad':''}">${d.tir!=null?fmt(d.tir,0)+'%':'–'}</td>
    <td class="num">${d.cv!=null?fmt(d.cv,0)+'%':'–'}</td><td class="num">${d.max!=null?`${fmt(d.max,1)} / ${fmt(d.min,1)}`:'–'}</td><td class="num">${d.overnight!=null?fmt(d.overnight,1):'–'}</td></tr>`).join('')}</table>`;
  const P = O.profile, x = P.map(p => p.t);
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule,opacity:.5}}};
  const band = (a, b, op) => [{type:'line',data:P.map(p=>p[a]),stack:a+b,lineStyle:{opacity:0},symbol:'none',silent:true,tooltip:{show:false}},
                              {type:'line',data:P.map(p=>+(p[b]-p[a]).toFixed(2)),stack:a+b,lineStyle:{opacity:0},symbol:'none',areaStyle:{color:c.accent,opacity:op},silent:true,tooltip:{show:false}}];
  chart('gprofile').setOption({animation:MOTION,textStyle:{fontFamily:'Archivo'},grid:{left:36,right:16,top:28,bottom:26},
    title:{text:'24-hour profile: median line, middle half and 90% of readings shaded',left:36,top:0,textStyle:{fontSize:12,fontWeight:600,color:c.ink,fontFamily:'Archivo'}},
    xAxis:{type:'category',data:x,boundaryGap:false,...ax,axisTick:{show:false}},
    yAxis:{type:'value',min:2,max:v=>Math.max(10,Math.ceil(v.max+0.5)),interval:2,...ax},
    tooltip:{trigger:'axis',...tip(c),formatter:ps=>{ const p = P[ps[0].dataIndex]; return `<b>${esc(p.t)}</b> · ${esc(p.n)} readings<br>Median <b>${fmt(p.p50,1)}</b><br>Middle half ${fmt(p.p25,1)}–${fmt(p.p75,1)}<br>90% ${fmt(p.p5,1)}–${fmt(p.p95,1)}`; }},
    series:[...band('p5','p95',.12), ...band('p25','p75',.22),
      {type:'line',name:'Median',data:P.map(p=>p.p50),symbol:'none',smooth:.3,lineStyle:{color:c.ink,width:2},
        markArea:{silent:true,label:{show:false},data:[[{yAxis:lo,itemStyle:{color:c.good,opacity:.08}},{yAxis:hi}]]}}]});
  const M = O.meals;
  $('#gmeals').innerHTML = M.length ? `<h3 class="g-h3">Meals ranked by spike (last ${esc(O.window)} days)</h3><table class="g-meals"><tr><th>Meal</th><th class="num">Rise</th><th class="num">Peak</th><th class="num">Peak at</th><th class="num">Back down</th></tr>${M.slice(0,15).map(m => `<tr>
      <td>${shortDate(m.date)} ${esc(m.time)} ${esc(m.meal)}<br><span class="sub">${esc(m.label)}</span></td><td class="num ${m.rise>=3?'bad':m.rise<=1.5?'good':''}"><b>${m.rise>=0?'+':''}${fmt(m.rise,1)}</b></td>
      <td class="num">${fmt(m.peak,1)}</td><td class="num">${esc(m.peak_min)} min</td><td class="num">${m.back_min!=null?m.back_min+' min':'>2½ h'}</td></tr>`).join('')}</table>`
    : `<p class="sub">Meals logged with a time will be ranked here by how much they raise your glucose.</p>`;
}
async function renderBody(){
  renderGlucoseOverview();
  BODY = BODY || await api('/api/body');
  const c = theme(), s = BODY.scale;
  const fasted = s.filter(p=>p.fasted!==false).map(p=>[p.date,p.kg]);
  const today = SUMMARY.length ? SUMMARY[SUMMARY.length-1].date : (s.length ? s[s.length-1].date : null);
  const wt = BODY.weight_targets.map(w=>[w.date,w.kg]); if(today && wt.length) wt.push([today, wt[wt.length-1][1]]);
  const start = s.length ? s[0].date : null;
  const allKg = [...s.map(p=>p.kg), ...wt.map(w=>w[1]), ...BODY.inbody.filter(b=>start && b.date>=start).map(b=>b.weight_kg)];
  const bf = s.filter(p=>p.bf_pct).map(p=>[p.date,p.bf_pct]);
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule,opacity:.5}}};
  const xr = {type:'time',min:start,max:today,...ax};
  chart('bodychart').setOption({animation:MOTION,animationDuration:500,textStyle:{fontFamily:'Archivo'},
    title:[{text:'Weight, kg',left:52,top:0,textStyle:{fontSize:12.5,fontWeight:600,color:c.ink}},{text:'Body fat %, home scale',left:52,top:300,textStyle:{fontSize:12.5,fontWeight:600,color:c.ink}}],
    legend:{top:0,right:20,textStyle:{color:c.muted},data:['7-day trend','Fasted','Not fasted','Target','InBody']},
    grid:[{left:52,right:96,top:30,height:240},{left:52,right:96,top:326,height:70}],
    xAxis:[{...xr,gridIndex:0,axisLabel:{show:false}},{...xr,gridIndex:1}],
    yAxis:[{type:'value',gridIndex:0,...ax,...niceRange(Math.min(...allKg)-0.3, Math.max(...allKg)+0.3, 4)},
           {type:'value',gridIndex:1,...ax,...niceRange(Math.min(...bf.map(b=>b[1]))-0.2, Math.max(...bf.map(b=>b[1]))+0.2, 2)}],
    tooltip:{trigger:'axis',...tip(c)}, axisPointer:{link:[{xAxisIndex:'all'}],lineStyle:{color:c.muted}},
    series:[
      {type:'line',name:'7-day trend',data:rolling7(fasted),smooth:.4,symbol:'none',lineStyle:{color:c.accent,width:3,cap:'round'},z:4,
        areaStyle:{origin:'start',color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:c.soft},{offset:1,color:'rgba(0,0,0,0)'}])}},
      {type:'scatter',name:'Fasted',data:fasted,symbolSize:8,itemStyle:{color:c.accent,opacity:.45},z:5},
      {type:'scatter',name:'Not fasted',data:s.filter(p=>p.fasted===false).map(p=>[p.date,p.kg]),symbolSize:8,itemStyle:{color:c.surface,borderColor:c.accent,borderWidth:2},z:5},
      {type:'line',name:'Target',data:wt,step:'end',symbol:'none',lineStyle:{color:c.good,type:'dashed',width:1.8},z:3,
        endLabel:{show:true,color:c.ink,fontWeight:600,fontFamily:'Archivo',formatter:p=>'target '+p.value[1]}},
      {type:'scatter',name:'InBody',data:BODY.inbody.filter(b=>start && b.date>=start).map(b=>[b.date,b.weight_kg]),symbol:'diamond',symbolSize:15,itemStyle:{color:c.warn,...ring(c)},z:6},
      {type:'line',name:'Body fat %',xAxisIndex:1,yAxisIndex:1,data:bf,smooth:.3,symbol:'circle',symbolSize:8,lineStyle:{color:c.ink,width:2},itemStyle:{color:c.ink,...ring(c)}},
    ]});
  $('#inbodytable').innerHTML = `<table><tr><th>Date</th><th>Weight</th><th>Muscle (SMM)</th><th>Fat mass</th><th>Body fat</th><th>Fat-free</th><th>Visceral</th><th>Phase angle</th><th>Score</th></tr>` +
    BODY.inbody.map(b=>`<tr><td>${shortDate(b.date)} ${b.date.slice(0,4)}</td><td>${esc(b.weight_kg)}${b.clothed?'*':''}</td><td>${b.smm_kg??'–'}</td><td>${b.fat_kg??'–'}</td><td>${b.pbf_pct!=null?b.pbf_pct+'%':'–'}</td><td>${b.ffm_kg??'–'}</td><td>${b.visceral_level??'–'}</td><td>${b.phase_angle??'–'}</td><td>${b.score??'–'}</td></tr>`).join('') +
    `</table><p class="sub">* clothed. InBody reads about 1.7 points higher body fat and 0.8 kg lower fat-free mass than the home scale. Home-scale body fat moves ±0.3% day to day with hydration, so read the trend, not single days.</p>`;
  renderBP(); renderEnergyBalance(); renderComposition();
}

/* ---------- body composition: one small chart per measure the scale (and InBody) gives ---------- */
const BC = [   // key, label, unit, decimals, InBody field measuring the same thing (or null)
  ['fat_kg','Fat mass','kg',1,'fat_kg'], ['muscle_kg','Muscle mass','kg',1,null], ['ffm_kg','Fat-free mass','kg',1,'ffm_kg'],
  ['skeletal_muscle_pct','Skeletal muscle','%',1,null], ['subcutaneous_fat_pct','Subcutaneous fat','%',1,null],
  ['visceral','Visceral fat','level',0,'visceral_level'], ['water_pct','Body water','%',1,null], ['protein_pct','Protein','%',1,null],
  ['bone_kg','Bone mass','kg',2,'bone_mineral_kg'], ['bmr_kcal','BMR','kcal',0,'bmr_kcal'], ['bmi','BMI','',1,'bmi'],
];
function renderComposition(){
  const c = theme(), s = BODY.scale, ib = BODY.inbody || [], bands = BODY.bands || {};
  const shown = BC.filter(([k]) => s.some(p => p[k] != null));
  const start = s.length ? s[0].date : null, end = SUMMARY.length ? SUMMARY[SUMMARY.length-1].date : null;
  $('#bcnote').textContent = 'From the home scale\'s morning readings: the line joins fasted ones, hollow dots are after food (less reliable). ' +
    'Diamonds are InBody scans where InBody measures the same thing (it reads about 1.7 points more body fat and 0.8 kg less fat-free mass than the scale). The change is against the reading nearest 30 days earlier. ' +
    'Bioimpedance swings with hydration, so read the trend, not single days.';
  $('#bcgrid').innerHTML = shown.map(([k,lab]) => `<div class="bc"><div class="bc-h" id="bch-${k}"></div><div id="bc-${k}" class="chart bc-c"></div></div>`).join('');
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:10},splitLine:{lineStyle:{color:c.rule,opacity:.5}}};
  for(const [k,lab,u,dp,ik] of shown){
    const pts = s.filter(p => p[k] != null), f = pts.filter(p => p.fasted !== false), nf = pts.filter(p => p.fasted === false);
    const last = (f.length ? f : pts)[ (f.length ? f : pts).length-1 ];
    const ago = new Date(new Date(last.date+'T00:00') - 30*864e5).toISOString().slice(0,10);
    const base = [...(f.length ? f : pts)].reverse().find(p => p.date <= ago) || null;
    const d = base ? last[k] - base[k] : null;
    const ibs = ik ? ib.filter(b => b[ik] != null && (!start || b.date >= start)).map(b => [b.date, b[ik]]) : [];
    // each chart starts a few days before its own first reading, so the measures the scale added later aren't squashed
    const first = [pts[0].date, ...ibs.map(b => b[0])].sort()[0];
    const x0 = new Date(new Date(first+'T00:00') - 4*864e5).toISOString().slice(0,10);
    const band = bands[k];
    $('#bch-'+k).innerHTML = `<span class="nm">${lab}</span> <b>${fmt(last[k],dp)}</b><small>${u?' '+u:''}</small>` +
      (d!=null ? ` <span class="sub">${d>0?'+':''}${fmt(d,dp)} in 30 d</span>` : ` <span class="sub">${esc(pts.length)} reading${pts.length!==1?'s':''}</span>`);
    const vals = [...pts.map(p => p[k]), ...ibs.map(b => b[1]), ...(band ? band.filter(v => v!=null) : [])];
    const lo = Math.min(...vals), hi = Math.max(...vals), pad = Math.max((hi-lo)*0.1, Math.abs(hi)*0.005, 10**-dp);
    const yr = niceRange(lo-pad, hi+pad, 3), ydp = Math.max(dp, ((String(+(yr.interval||1).toFixed(4)).split('.')[1])||'').length);
    chart('bc-'+k).setOption({animation:MOTION,textStyle:{fontFamily:'Archivo'},grid:{left:44,right:14,top:10,bottom:24},
      xAxis:{type:'time',min:x0,max:end,splitNumber:4,...ax,splitLine:{show:false},axisLabel:{color:c.muted,fontSize:10,hideOverlap:true}},
      yAxis:{type:'value',...ax,...yr,axisLabel:{color:c.muted,fontSize:10,formatter:v=>fmt(v,ydp)}},
      tooltip:{trigger:'item',...tip(c),formatter:p => `${shortDate(String(p.value[0]).slice(0,10))} · <b>${fmt(p.value[1],dp)}${u?' '+u:''}</b> ${esc(p.seriesName)}`},
      series:[
        {type:'line',name:'fasted',data:f.map(p=>[p.date,p[k]]),symbol:'circle',symbolSize:6,showSymbol:f.length<=30,lineStyle:{color:c.accent,width:2},itemStyle:{color:c.accent},
          markLine: band ? {silent:true,symbol:'none',lineStyle:{color:c.good,type:'dashed'},label:{color:c.muted,fontSize:10,position:'insideEndTop',
            formatter:p=>(p.value===band[1]?'under ':'from ')+p.value},data:band.filter(v=>v!=null).map(v=>({yAxis:v}))} : undefined},
        {type:'scatter',name:'after food',data:nf.map(p=>[p.date,p[k]]),symbolSize:7,itemStyle:{color:c.surface,borderColor:c.accent,borderWidth:1.5}},
        {type:'scatter',name:'InBody',data:ibs,symbol:'diamond',symbolSize:12,itemStyle:{color:c.warn,...ring(c)},z:5},
      ]});
  }
}

/* ---------- energy balance: 30 days of burnt minus eaten, and the weight it should have moved ---------- */
async function renderEnergyBalance(){
  const E = await api('/api/energy').catch(()=>null), H = E && E.history;
  if(!H || !H.days.length){ $('#ebnote').textContent = 'Needs a few closed days with Garmin data.'; return; }
  const c = theme(), ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule,opacity:.5}}};
  const kg = v => (v>0?'+':'')+fmt(v,2)+' kg';
  const parts = [];
  if(H.avg_deficit!=null) parts.push(`Average ${H.avg_deficit>=0?'deficit':'surplus'} <b>${fmt(Math.abs(H.avg_deficit))} kcal/day</b> over ${esc(H.counted)} closed days with watch data (burnt per Garmin minus eaten as logged). `);
  if(H.expected_kg!=null) parts.push(`At ${fmt(H.kcal_per_kg)} kcal per kg that should be <b>${kg(H.expected_kg)}</b> in ${H.days.length} days`);
  if(H.actual_kg!=null) parts.push(`; the trend through your ${esc(H.weights.length)} fasted weigh-ins is <b>${kg(H.actual_kg)}</b>.`);
  else parts.push('. Not enough fasted weigh-ins in the window for an actual trend yet.');
  if(H.gap_kcal_day!=null){
    const g = H.gap_kcal_day;
    parts.push(Math.abs(g) < 75 ? ` The two agree to within ${fmt(Math.abs(g))} kcal a day: your logging and Garmin's burn are consistent.`
      : g > 0 ? ` The scale says the real deficit was about <b>${fmt(H.actual_avg_deficit)} kcal/day</b>: ${fmt(g)} kcal a day less than the logs. Either Garmin overestimates your burn, portions are under-logged, or both. Water and glycogen also hide fat loss for a week or two.`
      : ` The scale says you lost more than the logs explain (about ${fmt(-g)} kcal a day more): Garmin may underestimate your burn, or logged portions run high.`);
  }
  $('#ebnote').innerHTML = parts.join('');
  const dates = H.days.map(d => d.date);
  chart('ebchart').setOption({animation:MOTION,animationDuration:500,textStyle:{fontFamily:'Archivo'},
    title:[{text:'Daily balance, kcal: burnt − eaten (up = deficit)',left:52,top:0,textStyle:{fontSize:12.5,fontWeight:600,color:c.ink}},
           {text:'Weight: expected from the balance vs actual',left:52,top:196,textStyle:{fontSize:12.5,fontWeight:600,color:c.ink}}],
    legend:{bottom:0,left:52,textStyle:{color:c.muted},data:['Expected','Actual trend','Fasted']},
    grid:[{left:52,right:40,top:28,height:140},{left:52,right:40,top:222,height:120}],
    xAxis:[{type:'category',data:dates,gridIndex:0,...ax,axisLabel:{show:false}},
           {type:'time',gridIndex:1,min:H.start,max:H.end,...ax}],
    yAxis:[{type:'value',gridIndex:0,...ax},{type:'value',gridIndex:1,scale:true,...ax}],
    tooltip:{trigger:'axis',...tip(c),formatter:ps => ps.map(p => p.seriesName==='Balance'
      ? (() => { const d = H.days[p.dataIndex]; return `<b>${shortDate(d.date)}</b><br>burnt ${d.burnt!=null?fmt(d.burnt):'–'} · eaten ${d.eaten!=null?fmt(d.eaten):'–'}<br>${d.deficit==null?'not counted (day open or no watch data)':d.deficit>=0?`<b>${fmt(d.deficit)}</b> deficit`:`<b>${fmt(-d.deficit)}</b> surplus`}`; })()
      : `${esc(p.seriesName)}: <b>${fmt(p.value[1],2)} kg</b> (${shortDate(String(p.value[0]).slice(0,10))})`).join('<br>')},
    series:[
      {type:'bar',name:'Balance',xAxisIndex:0,yAxisIndex:0,barMaxWidth:14,
        data:H.days.map(d => d.deficit==null ? null : {value:d.deficit, itemStyle:{color:d.deficit>=0?c.good:c.warn, borderRadius:d.deficit>=0?[3,3,0,0]:[0,0,3,3]}}),
        markLine:{silent:true,symbol:'none',lineStyle:{color:c.muted,type:'dashed'},label:{color:c.muted,position:'end',fontSize:11,formatter:'avg'},
          data:H.avg_deficit!=null?[{yAxis:H.avg_deficit}]:[]}},
      {type:'line',name:'Expected',xAxisIndex:1,yAxisIndex:1,data:H.expected_line||[],symbol:'none',lineStyle:{color:c.good,type:'dashed',width:2},itemStyle:{color:c.good}},
      {type:'line',name:'Actual trend',xAxisIndex:1,yAxisIndex:1,data:H.trend||[],symbol:'none',lineStyle:{color:c.accent,width:3},itemStyle:{color:c.accent}},
      {type:'scatter',name:'Fasted',xAxisIndex:1,yAxisIndex:1,data:H.weights,symbolSize:8,itemStyle:{color:c.accent,opacity:.5}},
    ]});
}

/* ---------- food: every food eaten, its macros, how much and how often; the week's biggest sources ---------- */
let FOODS = null, FSORT = {k:'times', dir:-1}, FQ = '', FWIN = 'all';
const PE_CLS = v => v==null ? '' : v >= 15 ? 'good' : v >= 8 ? 'warn' : '';   // grams of protein per 100 kcal
/* ---------- sleep ---------- */
let SLEEP = null;
const mh = m => m==null ? '–' : `${Math.floor(Math.round(m)/60)}h ${String(Math.round(m)%60).padStart(2,'0')}m`;
const clk = m => { if(m==null) return '–'; m = ((Math.round(m) % 1440) + 1440) % 1440; return `${String(Math.floor(m/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`; };
const SLEEP_COL = {deep:'#3d2fb0', light:'#7a6ae0', rem:'#b3a6ff', awake:'#e0a33a'};

async function renderSleep(){
  SLEEP = SLEEP || await api('/api/sleep').catch(()=>null);
  const el = $('#sleep');
  if(!SLEEP){ el.innerHTML = '<p class="empty">Couldn’t load your sleep.</p>'; return; }
  if(!SLEEP.available){ el.innerHTML = '<p class="empty">No nights yet. Connect Garmin on the Connections page and sleep with your watch on.</p>'; return; }
  const S = SLEEP, L = S.last, R = S.recent, G = S.regularity, TN = S.tonight, T = S.target_min;
  const ok = (v, good) => v==null ? '' : good ? 'good' : 'bad';
  el.innerHTML = `
    <p class="sub">Last night is the night you woke up on ${esc(fmtDate(L.date))}. Target ${esc(mh(T))} asleep${R.need?`; Garmin's sleep need lately ${esc(mh(R.need))}`:''}.</p>
    <div class="wk-grid">
      <div class="t"><div class="lab">Last night</div><div class="v ${ok(L.asleep, L.asleep >= T)}">${esc(mh(L.asleep))}</div><div class="s">${clk(L.start)}–${clk(L.end)} · ${esc(L.awake ?? '–')} min awake</div></div>
      <div class="t"><div class="lab">Sleep score</div><div class="v ${ok(L.score, L.score >= 80)}">${esc(L.score ?? '–')}</div><div class="s">HRV ${esc(L.hrv ?? '–')} ms · resting HR ${esc(L.rhr ?? '–')}</div></div>
      <div class="t"><div class="lab">Last ${esc(S.recent_n)} nights</div><div class="v ${ok(R.asleep, R.asleep >= T)}">${esc(mh(R.asleep))}</div><div class="s">${esc(R.on_target)} of ${esc(S.recent_n)} on target</div></div>
      <div class="t"><div class="lab">Sleep debt, 7 nights</div><div class="v ${ok(R.debt7, R.debt7 <= 60)}">${R.debt7 > 0 ? esc(mh(R.debt7)) : 'none'}</div><div class="s">${R.debt7 > 0 ? 'under your target' : 'you’re at or over your target'}</div></div>
      ${TN ? `<div class="t tn"><div class="lab">Tonight</div><div class="v">${esc(TN.in_bed)}</div><div class="s">in bed, for a ${esc(TN.wake)} wake-up${TN.weekend?' (your weekday time: no weekend lie-in)':''}. Wind down from ${esc(TN.wind_down)}.</div></div>` : ''}
    </div>
    <h2>Last night</h2>
    <p class="sub">Your sleep stages through the night.${L.spo2_low?` Oxygen ${esc(L.spo2_avg ?? '–')}% average, ${esc(L.spo2_low)}% lowest; breathing ${esc(L.resp ?? '–')} a minute.`:''}${L.bb!=null?` Body battery ${esc(L.bb)} on waking.`:''}</p>
    <div class="st-legend">${['deep','light','rem','awake'].map(k => `<span><i style="background:${SLEEP_COL[k]}"></i>${({deep:'Deep',light:'Light',rem:'REM',awake:'Awake'})[k]} ${esc(L[k] ?? '–')} min</span>`).join('')}</div>
    <div id="sl-hyp" class="chart" style="height:170px"></div>
    <h2>Every night, last ${esc(S.nights.length)}</h2>
    <p class="sub">Time asleep against your target, with Garmin's sleep need and your sleep debt over the 7 nights to each date.</p>
    <div id="sl-trend" class="chart" style="height:400px"></div>
    ${sleepStagesHtml(S.stages)}
    <h2>When you sleep</h2>
    <p class="sub">Each bar runs from falling asleep to waking. Lately your bedtime is ${esc(G.bed_median ?? '–')} give or take ${esc(G.bed_sd ?? '–')} min, waking ${esc(G.wake_median ?? '–')} give or take ${esc(G.wake_sd ?? '–')} min.${G.social_jetlag_min!=null?` At weekends your sleep runs ${esc(Math.abs(G.social_jetlag_min))} min ${G.social_jetlag_min>=0?'later':'earlier'}.`:''} Weekend mornings in blue.${TN?` Dashed: tonight’s bedtime.`:''}</p>
    <div id="sl-when" class="chart" style="height:360px"></div>
    <h2>What goes with better and worse nights</h2>
    <p class="sub">Each row compares your nights after that kind of day with the rest of your ${esc(S.window_n)} nights. Bars show the difference: green is better, red is worse. Hover a row for the numbers. These show what goes together, not proof of cause.</p>
    <div class="sl-fx">${sleepFactors(S.factors)}</div>
    <h2>What your data says to do</h2>
    ${S.advice.length ? `<div class="sl-adv">${S.advice.map((a, i) => `<div class="fs${i===0?' top':''}"><h3>${esc(a.title)}</h3><p>${esc(a.why)}</p><p class="do">${esc(a.do)}</p></div>`).join('')}</div>` : '<p class="sub">Nothing stands out: your sleep is on target and regular. Keep doing what you are doing.</p>'}
    <h2>Sleep habits that work</h2>
    <p class="sub">The general advice with the best evidence, for everyone. Start with the first two.</p>
    <ol class="sl-gen">${S.general.map(g => `<li><b>${esc(g.title)}.</b> ${esc(g.text)}</li>`).join('')}</ol>`;

  const c = theme();
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule,opacity:.5}}};

  // hypnogram: one lane per stage, awake at the top
  const lane = {awake:3, rem:2, light:1, deep:0};
  if(L.stages && L.stages.length){
    const lo = Math.min(...L.stages.map(s => s.start)), hi = Math.max(...L.stages.map(s => s.end));
    chart('sl-hyp').setOption({animation:false,textStyle:{fontFamily:'Archivo'},grid:{left:52,right:20,top:8,bottom:26},
      xAxis:{type:'value',min:60*Math.floor(lo/60),max:60*Math.ceil(hi/60),...ax,splitLine:{show:true,lineStyle:{color:c.rule,opacity:.35}},axisLabel:{...ax.axisLabel,formatter:clk},interval:60},
      yAxis:{type:'category',data:['Deep','Light','REM','Awake'],...ax,axisLine:{show:false},axisTick:{show:false},splitLine:{show:false}},
      tooltip:{...tip(c),formatter: p => `${esc(({deep:'Deep',light:'Light',rem:'REM',awake:'Awake'})[p.data.stage])}<br>${clk(p.data.value[0])}–${clk(p.data.value[1])} · ${p.data.value[1]-p.data.value[0]} min`},
      series:[{type:'custom',renderItem:(params, api) => { const s = api.value(0), e = api.value(1), y = api.value(2);
          const a = api.coord([s, y]), b = api.coord([e, y]), h = api.size([0, 1])[1] * .72;
          return {type:'rect',shape:{x:a[0],y:a[1]-h/2,width:Math.max(1,b[0]-a[0]),height:h},style:{fill:SLEEP_COL[params.dataIndex!=null?L.stages[params.dataIndex].stage:'light']}}; },
        encode:{x:[0,1],y:2},data:L.stages.map(s => ({value:[s.start, s.end, lane[s.stage]], stage:s.stage}))}]});
  } else $('#sl-hyp').innerHTML = '<p class="empty">No stage data for last night.</p>';

  // trend: asleep bars, need line, target line; 7-night debt below
  const N = S.nights, x = N.map(n => shortDate(n.date));
  const debt7 = N.map((n, i) => { const w = N.slice(Math.max(0, i - 6), i + 1); return w.reduce((a, r) => a + (T - r.asleep), 0) / 60; });
  chart('sl-trend').setOption({animation:MOTION,animationDuration:400,textStyle:{fontFamily:'Archivo'},
    title:[{text:'Asleep, hours',left:52,top:0,textStyle:{fontSize:12.5,fontWeight:600,color:c.ink}},{text:'Sleep debt over 7 nights, hours',left:52,top:238,textStyle:{fontSize:12.5,fontWeight:600,color:c.ink}}],
    grid:[{left:52,right:20,top:24,height:190},{left:52,right:20,top:262,height:86}],
    xAxis:[0,1].map(i => ({type:'category',gridIndex:i,data:x,...ax,axisLabel:{...ax.axisLabel,show:i===1}})),
    yAxis:[{type:'value',gridIndex:0,...ax,...niceRange(0, Math.max(9, ...N.map(n => n.asleep/60)), 3, true),axisLabel:{...ax.axisLabel,formatter:v=>v+'h'}},
           {type:'value',gridIndex:1,...ax,...niceRange(Math.min(0, ...debt7), Math.max(1, ...debt7), 2),axisLabel:{...ax.axisLabel,formatter:v=>v+'h'}}],
    axisPointer:{link:[{xAxisIndex:'all'}],lineStyle:{color:c.muted}},
    tooltip:{trigger:'axis',...tip(c),formatter: ps => { const n = N[ps[0].dataIndex];
      return `<b>${esc(fmtDate(n.date))}</b><br>Asleep ${esc(mh(n.asleep))} (${clk(n.start)}–${clk(n.end)})${n.score?`<br>Score ${esc(n.score)}`:''}${n.need?`<br>Garmin's need ${esc(mh(n.need))}`:''}${n.hrv?`<br>HRV ${esc(n.hrv)} ms`:''}<br>7-night debt ${esc(mh(Math.max(0, debt7[ps[0].dataIndex]*60)))}`; }},
    series:[
      {type:'bar',xAxisIndex:0,yAxisIndex:0,barMaxWidth:16,data:N.map(n => ({value:+(n.asleep/60).toFixed(2),itemStyle:{color:n.asleep>=T?c.good:hatch(c.bad,c.surface),borderRadius:[3,3,0,0]}})),
        markLine:{symbol:'none',silent:true,data:[{yAxis:T/60}],lineStyle:{color:c.good,type:'dashed'},label:{formatter:`target ${mh(T)}`,color:c.good,position:'insideEndTop'}}},
      {type:'line',name:'Need',xAxisIndex:0,yAxisIndex:0,data:N.map(n => n.need ? +(n.need/60).toFixed(2) : null),connectNulls:true,symbol:'none',lineStyle:{color:c.accent,width:1.5,type:'dotted'}},
      {type:'line',name:'Debt',xAxisIndex:1,yAxisIndex:1,data:debt7.map(v => +v.toFixed(1)),symbol:'none',smooth:.3,lineStyle:{color:c.bad,width:2},
        areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(200,55,45,.25)'},{offset:1,color:'rgba(0,0,0,0)'}])},
        markLine:{symbol:'none',silent:true,data:[{yAxis:0}],lineStyle:{color:c.muted,type:'solid',opacity:.6},label:{show:false}}}]});

  if(S.stages && S.stages.available) sleepStageCharts(S, c, ax);
  // when: floating bars from sleep start to wake, minutes from the wake day's midnight (negative = before midnight)
  const base = 60 * Math.floor((Math.min(...N.map(n => n.start), TN ? hmToMin(TN.in_bed) : 0) - 20) / 60);
  const top = 60 * Math.ceil((Math.max(...N.map(n => n.end)) + 20) / 60) - base;
  const bedLine = TN ? {markLine:{symbol:'none',silent:true,data:[{yAxis:hmToMin(TN.in_bed) - base}],lineStyle:{color:c.good,type:'dashed'},label:{formatter:`in bed by ${TN.in_bed}`,color:c.good,position:'insideEndTop'}}} : {};
  chart('sl-when').setOption({animation:MOTION,animationDuration:400,textStyle:{fontFamily:'Archivo'},grid:{left:52,right:20,top:12,bottom:30},
    xAxis:{type:'category',data:x,...ax},
    yAxis:{type:'value',min:0,max:top,interval:60,...ax,axisLabel:{...ax.axisLabel,formatter: v => clk(v + base)}},
    tooltip:{trigger:'axis',...tip(c),formatter: ps => { const n = N[ps[0].dataIndex]; return `<b>${esc(fmtDate(n.date))}</b><br>Asleep ${clk(n.start)} to ${clk(n.end)}<br>${esc(mh(n.asleep))} asleep`; }},
    series:[{type:'bar',stack:'w',silent:true,itemStyle:{color:'transparent'},data:N.map(n => n.start - base)},
      {type:'bar',stack:'w',barMaxWidth:14,data:N.map(n => ({value:n.end - n.start,itemStyle:{color:n.weekend_morning?c.accent:c.muted,opacity:n.weekend_morning?.9:.55,borderRadius:3}})),...bedLine}]});
}
const STG = {deep:'Deep', light:'Light', rem:'REM', awake:'Awake'};
function sleepStagesHtml(G){
  if(!G || !G.available) return '';
  const tile = k => { const [lo, hi] = G.typical[k] || [], v = G.pct[k], cls = lo == null ? '' : v < lo ? 'bad' : v > hi && k !== 'deep' ? 'warn' : 'good';
    return `<div class="t"><div class="lab"><i class="stg-dot" style="background:${SLEEP_COL[k]}"></i>${STG[k]}</div><div class="v ${cls}">${fmt(v, 0)}%</div><div class="s">${esc(G.avg[k])} min a night · typical ${lo}–${hi}%</div></div>`; };
  const cmp = (title, rows) => { const mx = Math.max(...rows.map(r => Math.max(r.deep || 0, r.rem || 0)), 1);
    return `<div class="fs"><h3>${esc(title)}</h3>${rows.map(r => `<div class="stg-c"><span class="nm">${esc(r.label)} <span class="sub">${esc(r.n)} nights</span></span>
      <span class="stg-b"><i style="width:${Math.round((r.deep||0)/mx*100)}%;background:${SLEEP_COL.deep}"></i><b>${esc(r.deep ?? '–')}</b></span>
      <span class="stg-b"><i style="width:${Math.round((r.rem||0)/mx*100)}%;background:${SLEEP_COL.rem}"></i><b>${esc(r.rem ?? '–')}</b></span></div>`).join('')}</div>`; };
  return `<h2>Sleep stages</h2>
    <p class="sub">Your average over ${esc(G.n)} nights, as a share of time asleep, against what healthy adults typically get. Watches estimate stages from movement and heart rate, so read these as trends rather than lab numbers.</p>
    <div class="wk-grid">${['deep','rem','light'].map(tile).join('')}
      <div class="t"><div class="lab"><i class="stg-dot" style="background:${SLEEP_COL.awake}"></i>Wake-ups</div><div class="v">${fmt(G.wake.per_night, 1)}</div><div class="s">a night · ${esc(G.wake.long_nights)} nights with 20+ min awake</div></div></div>
    <div class="sl-pat">${G.patterns.map(p => `<div class="sl-p sl-p-${esc(p.kind)}"><b>${esc(p.title)}</b><span>${esc(p.text)}</span></div>`).join('')}</div>
    <h3 class="sl-h3">Minutes of each stage, every night</h3>
    <div id="sl-stg" class="chart" style="height:260px"></div>
    <h3 class="sl-h3">Deep and REM minutes, by the kind of night</h3>
    <div class="stg-key"><span><i style="background:${SLEEP_COL.deep}"></i>Deep</span><span><i style="background:${SLEEP_COL.rem}"></i>REM</span></div>
    <div class="sw-grid">${cmp('How long you slept', G.by_length)}${cmp('Training the day before', G.by_session)}${cmp('When you fell asleep', G.by_bedtime)}</div>
    <h3 class="sl-h3">When you wake in the night</h3>
    <p class="sub">Spells awake after you first fall asleep, by the hour they start, across ${esc(G.wake.nights)} nights.</p>
    <div id="sl-wake" class="chart" style="height:220px"></div>`;
}
function sleepStageCharts(S, c, ax){
  const N = S.nights, x = N.map(n => shortDate(n.date)), G = S.stages;
  chart('sl-stg').setOption({animation:MOTION,animationDuration:400,textStyle:{fontFamily:'Archivo'},grid:{left:52,right:20,top:28,bottom:28},
    legend:{top:0,right:10,textStyle:{color:c.muted,fontSize:11},itemWidth:10,itemHeight:10},
    xAxis:{type:'category',data:x,...ax},yAxis:{type:'value',...ax,axisLabel:{...ax.axisLabel,formatter:v => v/60 + 'h'},interval:120},
    tooltip:{trigger:'axis',...tip(c),formatter: ps => { const n = N[ps[0].dataIndex]; return `<b>${esc(fmtDate(n.date))}</b><br>` + ['deep','rem','light','awake'].map(k => `${STG[k]} ${n[k] ?? '–'} min`).join('<br>') + `<br>REM ${n.rem && n.asleep ? Math.round(100*n.rem/n.asleep) : '–'}% of sleep`; }},
    series:['deep','rem','light','awake'].map(k => ({type:'bar',name:STG[k],stack:'s',barMaxWidth:14,itemStyle:{color:SLEEP_COL[k]},data:N.map(n => n[k] ?? 0)}))});
  const H = G.wake.by_hour;
  chart('sl-wake').setOption({animation:MOTION,animationDuration:400,textStyle:{fontFamily:'Archivo'},grid:{left:52,right:20,top:12,bottom:28},
    xAxis:{type:'category',data:H.map(h => `${String(h.h).padStart(2,'0')}:00`),...ax},yAxis:{type:'value',...ax,minInterval:1},
    tooltip:{trigger:'axis',...tip(c),formatter: ps => { const h = H[ps[0].dataIndex]; return `<b>${String(h.h).padStart(2,'0')}:00–${String((h.h+1)%24).padStart(2,'0')}:00</b><br>${h.count} wake-ups over ${G.wake.nights} nights<br>about ${h.per10} in every 10 nights`; }},
    series:[{type:'bar',barMaxWidth:28,data:H.map(h => ({value:h.count,itemStyle:{color:SLEEP_COL.awake,borderRadius:[3,3,0,0]}}))}]});
}
// One row per factor: a verdict, then the difference on four measures as small bars around zero.
function sleepFactors(F){
  const verdict = f => {
    if(!f.enough) return ['few', 'Too few nights to tell'];
    const bad = (f.d_score ?? 0) <= -3 || (f.d_asleep ?? 0) <= -15, good = (f.d_score ?? 0) >= 3 || (f.d_asleep ?? 0) >= 15;
    return bad && !good ? ['bad', 'Worse nights'] : good && !bad ? ['good', 'Better nights'] : bad && good ? ['mixed', 'Mixed'] : ['none', 'No real difference'];
  };
  const rank = {bad:0, mixed:1, good:2, none:3, few:4};
  const rows = F.map(f => ({f, v: verdict(f), dbed: f.a.bed != null && f.b.bed != null ? Math.round(f.a.bed - f.b.bed) : null}))
    .sort((x, y) => rank[x.v[0]] - rank[y.v[0]] || Math.abs(y.f.d_score ?? 0) - Math.abs(x.f.d_score ?? 0));
  // each measure: its value, what counts as noise, the scale for a full bar, whether higher is better, and how to say it
  const M = [
    {lab:'Sleep', get:r => r.f.d_asleep, noise:10, full:45, up:true, say:v => `${Math.abs(v)} min ${v>0?'more':'less'}`},
    {lab:'Score', get:r => r.f.d_score, noise:2, full:10, up:true, say:v => `${v>0?'+':'−'}${Math.abs(v)}`},
    {lab:'HRV', get:r => r.f.d_hrv, noise:2, full:8, up:true, say:v => `${v>0?'+':'−'}${Math.abs(v)} ms`},
    {lab:'Asleep', get:r => r.dbed, noise:10, full:60, up:false, say:v => `${Math.abs(v)} min ${v>0?'later':'earlier'}`},
  ];
  const cell = (m, r) => { const v = m.get(r);
    if(v == null) return `<div class="fx-m"><span class="fx-l">${m.lab}</span><span class="sub">–</span></div>`;
    const quiet = Math.abs(v) < m.noise, good = (v > 0) === m.up, w = Math.min(50, Math.abs(v) / m.full * 50);
    const cls = quiet ? 'q' : good ? 'g' : 'b';
    return `<div class="fx-m"><span class="fx-l">${m.lab}</span><span class="fx-bar"><i class="${cls}" style="${v>0?'left:50%':'right:50%'};width:${quiet?Math.max(w,1.5):w}%"></i></span><span class="fx-v ${cls}">${quiet ? 'same' : m.say(v)}</span></div>`; };
  return rows.map(r => { const f = r.f;
    const t = `${f.yes}: ${f.a.n} nights, ${mh(f.a.asleep)} asleep, score ${f.a.score ?? '–'}, HRV ${f.a.hrv ?? '–'} ms, asleep by ${clk(f.a.bed)}\n${f.no}: ${f.b.n} nights, ${mh(f.b.asleep)} asleep, score ${f.b.score ?? '–'}, HRV ${f.b.hrv ?? '–'} ms, asleep by ${clk(f.b.bed)}`;
    return `<div class="fx-row fx-${r.v[0]}" title="${esc(t)}"><div class="fx-name"><b>${esc(f.name)}</b><span class="sub">${esc(f.yes)} · ${esc(f.a.n)} vs ${esc(f.b.n)} nights</span></div>
      <span class="fx-pill">${esc(r.v[1])}</span><div class="fx-ms">${M.map(m => cell(m, r)).join('')}</div></div>`; }).join('');
}
// '22:20' -> minutes from the wake day's midnight, so evening times are negative
const hmToMin = s => { const [h, m] = s.split(':').map(Number); const v = h*60 + m; return v >= 12*60 ? v - 1440 : v; };

function foodExtras(F){
  const P = F.plants, W = F.weekdays, S = F.slots, G = F.glucose, T = (W && W.targets) || {};
  let h = '';
  // plants: this week against the goal, and the last 8 weeks
  if(P){
    const max = Math.max(P.goal, ...P.history.map(x => x.count));
    h += `<h2>Plants this week</h2>
    <p class="sub">Different plants in the last 7 days: fruit, veg, grains, beans, nuts and seeds each count once. Research on gut bacteria found people eating ${esc(P.goal)} or more a week had the most varied gut microbiome.</p>
    <div class="pl-head"><span class="v ${P.this_week >= P.goal ? 'good' : 'bad'}">${fmt(P.this_week)}</span><span class="sub"> of ${esc(P.goal)}</span>
      <span class="pl-hist" aria-label="Plants per week, last ${P.history.length} weeks">${P.history.map(x => `<i title="7 days to ${shortDate(x.end)}: ${x.count}" class="${x.count >= P.goal ? 'ok' : ''}" style="height:${Math.round(x.count / max * 100)}%"></i>`).join('')}<b class="goal" style="bottom:${Math.round(P.goal / max * 100)}%" title="Goal: ${esc(P.goal)}"></b></span></div>
    <div class="staples">${P.plants.map(n => `<span class="chip">${esc(n)}</span>`).join('')}</div>`;
  }
  // swaps for the week's biggest saturated fat sources
  if(F.swaps && F.swaps.length){
    h += `<h2>Swaps for your saturated fat</h2>
    <p class="sub">Your biggest sources this week, and foods you already eat with at least as much protein per calorie and under half the saturated fat. "Saves" is what eating the same calories of the swap instead would have saved this week.</p>
    <div class="sw-grid">${F.swaps.map(s => `<div class="fs"><h3>${esc(s.name)} <span class="sub">${fmt(s.week_sf, 1)} g sat fat in ${fmt(s.week_kcal)} kcal</span></h3>` +
      (s.swaps.length ? s.swaps.map(c => `<div class="sw-row"><span class="nm">${esc(c.name)}</span><span class="good">−${fmt(c.saves_sf, 1)} g</span><span class="sub">${c.protein_change >= 0 ? '+' : '−'}${fmt(Math.abs(c.protein_change))} g protein</span></div>`).join('')
        : '<p class="sub">Nothing you eat beats it on both counts.</p>') + `</div>`).join('')}</div>`;
  }
  // meal slots
  if(S && S.slots && S.slots.length){
    const kmax = Math.max(...S.slots.map(s => s.k));
    h += `<h2>Your meals, on an average day</h2>
    <p class="sub">What each meal supplies per day, averaged over your ${esc(S.days)} complete days in the last 4 weeks. Drinks and anything outside a meal count as snacks.</p>
    <div class="ftab-wrap"><table class="ftab slots"><tr><th>Meal</th><th class="num">kcal</th><th></th><th class="num">Protein</th><th class="num">Sat fat</th><th class="num">Fibre</th><th>Mostly</th></tr>` +
      S.slots.map(s => `<tr><td>${esc(s.slot[0].toUpperCase() + s.slot.slice(1))}</td><td class="num">${fmt(s.k)}</td><td class="bar-cell"><span class="bar"><i class="fs-k" style="width:${Math.round(s.k / kmax * 100)}%"></i></span></td>
        <td class="num">${fmt(s.p)} g</td><td class="num${T.sf && s.sf > T.sf / 3 ? ' hi-sf' : ''}">${fmt(s.sf, 1)} g</td><td class="num">${fmt(s.fib, 1)} g</td><td class="mostly">${s.top.map(n => esc(n.split(/[,(]/)[0].trim())).join(', ')}</td></tr>`).join('') + `</table></div>`;
  }
  // weekday pattern
  if(W && W.days && W.days.some(d => d.n)){
    const cell = (v, k) => { if(v == null) return '<td class="num">–</td>';
      const t = T[k], ok = k === 'sf' ? (t == null || v <= t) : k === 'k' ? true : (t == null || v >= t);
      return `<td class="num ${k === 'k' ? '' : (ok ? 'good' : 'bad')}"><b>${fmt(v, k === 'sf' ? 1 : 0)}</b></td>`; };
    const row = (lab, d, n, cls = '') => d ? `<tr class="${cls}"><td>${esc(lab)} <span class="sub">${esc(n)} d</span></td>${cell(d.k, 'k')}${cell(d.p, 'p')}${cell(d.sf, 'sf')}${cell(d.fib, 'fib')}</tr>` : '';
    const gap = W.weekday && W.weekend ? Math.round(W.weekend.k - W.weekday.k) : null;
    h += `<h2>Weekdays and weekends</h2>
    <p class="sub">Daily averages over complete days in the last 8 weeks, against your targets (protein ${esc(T.p ?? '–')} g or more, saturated fat ${esc(T.sf ?? '–')} g or less, fibre ${esc(T.fib ?? '–')} g or more).${gap != null ? ` Weekends run ${fmt(Math.abs(gap))} kcal ${gap >= 0 ? 'higher' : 'lower'} than weekdays.` : ''}</p>
    <div class="ftab-wrap"><table class="ftab wkd"><tr><th>Day</th><th class="num">kcal</th><th class="num">Protein</th><th class="num">Sat fat</th><th class="num">Fibre</th></tr>
      ${W.days.filter(d => d.n).map(d => row(d.day, d, d.n)).join('')}
      ${row('Weekdays', W.weekday, W.n_weekday, 'tot')}${row('Weekends', W.weekend, W.n_weekend, 'tot')}</table></div>`;
  }
  // glucose by food
  h += `<h2>Glucose by food</h2>`;
  if(G && G.available){
    h += `<p class="sub">Median rise in glucose after meals that included each food (eaten in at least 2 timed meals). A meal's rise belongs to everything in it, so look for foods that sit high across different meals.</p>
    <div class="ftab-wrap"><table class="ftab"><tr><th>Food</th><th class="num">Meals</th><th class="num">Median rise</th><th class="num">Median peak</th><th class="num">Biggest rise</th></tr>` +
      G.foods.slice(0, 25).map(r => `<tr><td>${esc(r.name)}</td><td class="num">${esc(r.meals)}</td><td class="num${r.rise >= 2 ? ' hi-sf' : ''}"><b>${fmt(r.rise, 1)}</b></td><td class="num">${fmt(r.peak, 1)}</td><td class="num">${fmt(r.max_rise, 1)}</td></tr>`).join('') + `</table></div>`;
  } else {
    h += `<p class="sub">Not enough sensor data yet. Wear a CGM (a Libre, synced on the Connections page) and log meals with times, and this ranks your foods by the glucose rise after them.</p>`;
  }
  return h;
}

async function renderFood(){
  FOODS = FOODS || await api('/api/foods').catch(()=>null);
  const el = $('#food'); if(!FOODS){ el.innerHTML = '<p class="empty">Couldn’t load the foods.</p>'; return; }
  const F = FOODS, C = F.counts;
  const amt = (v, r) => v ? (v >= 1000 ? fmt(v/1000, 1) + (r.liquid ? ' L' : ' kg') : fmt(v) + (r.liquid ? ' ml' : ' g')) : '–';
  // counted foods read as "10 × 50 g" (ten eggs); weighed ones as the total; servings with no weight (tea) as "12 cups"
  const qty = (v, n, r) => n && v && Math.abs(v - n * Math.round(v / n)) < 1 ? `${fmt(n)} × ${amt(Math.round(v / n), r)}`
    : (n && !v ? `${fmt(n)} serving${n === 1 ? '' : 's'}` : amt(v, r));
  const src = k => { const S = F.sources[k]; if(!S || !S.top.length) return '';
    const u = k==='k' ? ' kcal' : ' g', dp = k==='sf' ? 1 : 0;
    return `<div class="fs"><h3>${esc(S.label)} <span class="sub">${fmt(S.total, dp)}${u} in ${esc(F.recent_days)} days</span></h3>` +
      S.top.map(x => `<div class="fs-row" title="${esc(x.name)}: ${fmt(x.value, dp)}${u}"><span class="nm">${esc(x.name)}</span><span class="bar"><i class="fs-${k}" style="width:${Math.round(x.share*100)}%"></i></span><span class="pc">${Math.round(x.share*100)}%</span></div>`).join('') + `</div>`; };
  el.innerHTML = `<div class="wk-grid">
      <div class="t"><div class="lab">Foods you've eaten</div><div class="v">${fmt(C.foods)}</div><div class="s">over ${esc(F.logged_days)} logged days</div></div>
      <div class="t"><div class="lab">In the last 7 days</div><div class="v">${fmt(C.week)}</div><div class="s">different foods</div></div>
      <div class="t"><div class="lab">New this month</div><div class="v">${fmt(C.new_this_month)}</div><div class="s">first eaten since the 1st</div></div>
    </div>
    <h2>Where it came from, last 7 days</h2>
    <p class="sub">The foods behind each total, as a share of it. Saturated fat is the one to watch: the top few foods are where a swap pays off most.</p>
    <div class="fs-grid">${['sf','p','k','fib'].map(src).join('')}</div>
    <h2>Your staples</h2>
    <p class="sub">Eaten on the most days. Small changes to these move every day's totals.</p>
    <div class="staples">${F.staples.map(s => `<span class="chip">${esc(s.name)} <b>${Math.round(s.share*100)}%</b></span>`).join('')}</div>
    ${foodExtras(F)}
    <h2>Every food</h2>
    <div class="f-ctl"><input id="fq" type="search" placeholder="Search foods" value="${esc(FQ)}" aria-label="Search foods">
      <span class="seg" role="group" aria-label="Show"><button data-w="all" aria-pressed="${FWIN==='all'}">All time</button><button data-w="week" aria-pressed="${FWIN==='week'}">Last 7 days</button></span></div>
    <div class="ftab-wrap"><table class="ftab" id="ftab"></table></div>
    <p class="sub">Macros per 100 g (or 100 ml for drinks). <b>Protein per 100 kcal</b> shows how efficiently a food delivers protein: green 15 g or more, amber 8–15. "Times" counts logged entries; amounts are what you ate in total. Click a heading to sort.</p>`;
  const table = () => {
    const week = FWIN === 'week';
    const rows = F.foods.filter(r => (!week || r.w_times) && (!FQ || r.name.toLowerCase().includes(FQ) || r.key.includes(FQ)));
    const val = (r, k) => ({name: r.name.toLowerCase(), times: week ? r.w_times : r.times, amount: week ? r.w_amount : r.amount,
      kcal: (week ? r.w_totals : r.totals).k || 0, pe: r.protein_per_100kcal ?? -1, last: r.last,
      k: (r.per100||r.per_unit||{}).k ?? -1, p: (r.per100||r.per_unit||{}).p ?? -1, sf: (r.per100||r.per_unit||{}).sf ?? -1, fib: (r.per100||r.per_unit||{}).fib ?? -1})[k];
    rows.sort((a, b) => { const x = val(a, FSORT.k), y = val(b, FSORT.k); return (x < y ? -1 : x > y ? 1 : 0) * FSORT.dir; });
    const th = (k, lab, cls='') => `<th class="${cls}${FSORT.k===k?' sorted':''}" data-k="${k}" aria-sort="${FSORT.k===k?(FSORT.dir>0?'ascending':'descending'):'none'}">${lab}</th>`;
    const p = r => r.per100 || r.per_unit || {};
    $('#ftab').innerHTML = `<tr>${th('name','Food')}${th('k','kcal','num')}${th('p','Protein','num')}<th class="num">Carbs</th><th class="num">Fat</th>${th('sf','Sat fat','num')}${th('fib','Fibre','num')}${th('pe','Protein / 100 kcal','num')}${th('times', week?'Times (7 d)':'Times','num')}${th('amount', week?'Eaten (7 d)':'Eaten','num')}${th('kcal', week?'kcal (7 d)':'kcal total','num')}<th class="num" title="Times you logged it in the last 7 days, and how much you ate: 10 × 50 g is ten 50 g servings">7 days</th>${th('last','Last eaten','num')}</tr>` +
      (rows.length ? rows.map(r => `<tr><td class="nm">${esc(r.name)}${r.new_this_month?' <span class="tag">new</span>':''}${r.conf==='estimate'?' <span class="sub" title="Macros are an estimate, not from a label">est.</span>':''}${!r.per100&&r.per_unit?' <span class="sub" title="No weight for this one: the macros are per serving, not per 100 g">per serving</span>':''}</td>
        <td class="num">${fmt(p(r).k)}</td><td class="num">${fmt(p(r).p,1)}</td><td class="num">${fmt(p(r).c,1)}</td><td class="num">${fmt(p(r).f,1)}</td>
        <td class="num${(p(r).sf||0)>=5?' hi-sf':''}">${fmt(p(r).sf,1)}</td><td class="num">${fmt(p(r).fib,1)}</td>
        <td class="num pe-${PE_CLS(r.protein_per_100kcal)}">${r.protein_per_100kcal==null?'–':fmt(r.protein_per_100kcal,1)}</td>
        <td class="num">${fmt(week?r.w_times:r.times)}</td><td class="num">${qty(week?r.w_amount:r.amount, week?r.w_count:r.count, r)}</td><td class="num">${fmt((week?r.w_totals:r.totals).k||0)}</td>
        <td class="num">${r.w_times?`${esc(r.w_times)} time${r.w_times===1?'':'s'} · ${qty(r.w_amount, r.w_count, r)}`:'–'}</td><td class="num">${shortDate(r.last)}</td></tr>`).join('')
        : `<tr><td colspan="13" class="empty">No foods match.</td></tr>`);
    $('#ftab').querySelectorAll('th[data-k]').forEach(h => h.addEventListener('click', () => {
      const k = h.dataset.k; FSORT = FSORT.k===k ? {k, dir:-FSORT.dir} : {k, dir: k==='name' ? 1 : -1}; table(); }));
  };
  table();
  $('#fq').addEventListener('input', e => { FQ = e.target.value.trim().toLowerCase(); table(); });
  el.querySelectorAll('.seg button').forEach(b => b.addEventListener('click', () => { FWIN = b.dataset.w;
    el.querySelectorAll('.seg button').forEach(x => x.setAttribute('aria-pressed', x===b)); table(); }));
}

/* ---------- blood pressure ---------- */
const BPCLS = {normal:'normal', elevated:'elevated', 'stage 1':'s1', 'stage 2':'s2', crisis:'crisis'};
const BPLABEL = {normal:'Normal', elevated:'Elevated', 'stage 1':'Stage 1 high', 'stage 2':'Stage 2 high', crisis:'Crisis: seek care'};
// Pulse pressure = systolic - diastolic: how much the pressure swings with each beat. A rough guide, not a diagnosis.
const ppCat = v => v < 30 ? 'narrow' : v <= 50 ? 'healthy' : v <= 60 ? 'upper' : 'wide';
const PP_CLS = {narrow:'elevated', healthy:'normal', upper:'elevated', wide:'s1'};
const PP_LABEL = {narrow:'Narrow', healthy:'Healthy', upper:'Upper normal', wide:'Wide: worth watching'};
const PP_HELP = `<b>Pulse pressure</b> is your top number minus your bottom number: how much the pressure swings with each heartbeat.
  Flexible arteries stretch to absorb each beat and spring back, which keeps the two numbers close. Stiffer arteries let the gap widen.
  <table><tr><td>under 30</td><td>Narrow. Can follow a weak or fast heartbeat; check if it stays there.</td></tr>
  <tr><td><b>30–50</b></td><td><b>Healthy.</b> Around 40 is typical for adults.</td></tr>
  <tr><td>50–60</td><td>Upper normal. Fit people with a slow resting heart rate often read here.</td></tr>
  <tr><td>over 60</td><td>Wide. Worth watching if it stays there, especially with a rising top number.</td></tr></table>
  <br><span>It's a clue about artery stiffness that adds to your blood pressure, not a diagnosis. Judge the average, not one reading.</span>`;
function renderBP(){
  const c = theme(), bp = BODY.bp || [];
  const ax = {axisLine:{lineStyle:{color:c.rule}},axisLabel:{color:c.muted,fontSize:11},splitLine:{lineStyle:{color:c.rule}}};
  if(!bp.length){
    $('#bpnote').innerHTML = 'No readings yet. Log them in chat as <code>bp 07:10 118/76 p52</code>; as many per day as you like. Morning readings (before 9am, seated, before coffee) are the ones that matter for trends.';
    if(charts.bpchart){ charts.bpchart.dispose(); delete charts.bpchart; }
    $('#bpchart').style.display = 'none'; $('#bptable').innerHTML = ''; return;
  }
  $('#bpchart').style.display = '';
  const morning = bp.filter(b => b.context==='morning');
  const basis = morning.length ? morning : bp;   // until readings carry a time, average everything
  const last7 = basis.filter(b => (Date.now() - new Date(b.date)) < 30*864e5);
  const avg = a => a.length ? Math.round(a.reduce((x,y)=>x+y,0)/a.length) : null;
  const ms = avg(last7.map(b=>b.sys)), md = avg(last7.map(b=>b.dia)), mp = avg(last7.map(b=>b.sys-b.dia));
  $('#bpnote').innerHTML = `<div class="tiles">
    <div><div class="lab">${morning.length?"Morning":"Average"}, last 30 days</div><div class="v">${ms!=null?`${ms}/${md}`:'–'}</div>${ms!=null?`<span class="bpcat ${BPCLS[cat(ms,md)]}">${BPLABEL[cat(ms,md)]}</span>`:''}</div>
    <div><div class="lab">Pulse pressure, last 30 days</div><div class="v">${mp!=null?mp:'–'}<small> mmHg</small></div>${mp!=null?`<span class="hs-d" tabindex="0"><span class="bpcat ${PP_CLS[ppCat(mp)]}">${PP_LABEL[ppCat(mp)]}</span> <small>what's this?</small><span class="hs-tip left" role="tooltip">${PP_HELP}</span></span>`:''}</div>
    <div><div class="lab">Readings</div><div class="v">${bp.length}</div></div></div>
    <span class="sub">Categories follow the 2017 ACC/AHA guideline. Single readings vary a lot; judge the morning average.</span>`;
  function cat(s,d){ return s>=180||d>=120?'crisis':s>=140||d>=90?'stage 2':s>=130||d>=80?'stage 1':s>=120?'elevated':'normal'; }
  const pts = k => bp.map(b => ({value:[`${b.date}T${b.time||'08:00'}`, k==='pp' ? b.sys-b.dia : b[k]], symbol: b.context==='morning' ? 'circle' : 'triangle', b}));
  const all = bp.flatMap(b => [b.sys, b.dia, b.sys-b.dia]);
  chart('bpchart').setOption({animation:MOTION,animationDuration:400,textStyle:{fontFamily:'Archivo'},
    legend:{top:0,left:56,textStyle:{color:c.muted},data:['Systolic','Diastolic','Pulse pressure'],
      tooltip:{show:true,...tip(c),formatter: p => p.name==='Pulse pressure' ? `<div style="max-width:300px;white-space:normal">${PP_HELP}</div>` : p.name}},
    grid:{left:66,right:110,top:24,bottom:34},
    xAxis:{type:'time',...ax},
    yAxis:{type:'value',name:'mmHg',nameLocation:'middle',nameGap:42,nameRotate:90,nameTextStyle:{color:c.muted,fontSize:11},...ax,...niceRange(Math.min(60, ...all), Math.max(145, ...all), 4)},
    tooltip:{trigger:'item',...tip(c),formatter: p => { const b = p.data.b;
      const pp = b.sys-b.dia;
      return `<b>${fmtDate(b.date)}</b> ${b.time||''} · ${esc(b.context)}<br>${esc(b.sys)}/${esc(b.dia)}${b.pulse?` · pulse ${esc(b.pulse)}`:''}<br><span class="bpcat ${BPCLS[b.category]}">${BPLABEL[b.category]}</span>
        <br>Pulse pressure <b>${pp}</b> <span class="bpcat ${PP_CLS[ppCat(pp)]}">${PP_LABEL[ppCat(pp)]}</span>${b.note?'<br>'+esc(b.note):''}`; }},
    series:[
      {type:'line',name:'Systolic',data:pts('sys'),symbolSize:9,lineStyle:{color:c.ink,width:2},itemStyle:{color:c.ink,...ring(c)},
        markLine:{symbol:'none',silent:true,lineStyle:{type:'dashed',color:c.muted},label:{color:c.ink,position:'end',fontSize:11},
          data:[{yAxis:120,label:{formatter:'120 elevated'}},{yAxis:130,label:{formatter:'130 stage 1'}},{yAxis:140,label:{formatter:'140 stage 2'}}]}},
      {type:'line',name:'Diastolic',data:pts('dia'),symbolSize:9,lineStyle:{color:c.accent,width:2},itemStyle:{color:c.accent,...ring(c)},
        markLine:{symbol:'none',silent:true,lineStyle:{type:'dashed',color:c.muted},label:{color:c.ink,position:'end',fontSize:11},
          data:[{yAxis:80,label:{formatter:'80 stage 1'}},{yAxis:90,label:{formatter:'90 stage 2'}}]}},
      {type:'line',name:'Pulse pressure',data:pts('pp'),symbolSize:7,lineStyle:{color:'#e87ba4',width:1.6,type:'dotted'},itemStyle:{color:'#e87ba4',...ring(c)},
        markLine:{symbol:'none',silent:true,lineStyle:{type:'dashed',color:'#e87ba4',opacity:.7},label:{color:c.ink,position:'end',fontSize:11},
          data:[{yAxis:60,label:{formatter:'60 wide pulse'}}]}},
    ]});
  $('#bptable').innerHTML = `<table><tr><th>Date</th><th>Time</th><th>When</th><th>Reading</th><th>Pulse</th><th title="Top number minus bottom number">Pulse pressure</th><th>Category</th></tr>` +
    [...bp].reverse().map(b => `<tr><td>${shortDate(b.date)}</td><td>${b.time||'–'}</td><td>${esc(b.context)}</td><td><b>${esc(b.sys)}/${esc(b.dia)}</b></td><td>${b.pulse??'–'}</td><td>${b.sys-b.dia}</td><td><span class="bpcat ${BPCLS[b.category]}">${BPLABEL[b.category]}</span></td></tr>`).join('') + `</table>
    <p class="sub">Circles are morning readings, triangles are other or unknown times. Pulse pressure is the top number minus the bottom one (dotted pink line).</p>`;
}

/* ---------- garmin sync status ---------- */
function ago(iso){ if(!iso) return null; const m = Math.round((Date.now() - new Date(iso)) / 60000);
  return m < 1 ? 'just now' : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m/60)} h ago` : `${Math.round(m/1440)} d ago`; }
let syncWasRunning = false, syncTimer = null;
async function pollSync(){
  let s; try { s = await api('/api/garmin'); } catch(e){ return; }
  const dot = $('#syncdot'), msg = $('#syncmsg'), btn = $('#syncbtn');
  dot.className = 'dot'; btn.hidden = !s.ready; btn.disabled = !!s.running;
  if(s.blocked){ msg.textContent = 'Garmin: sync off'; $('#sync').title = s.blocked; }
  else if(!s.installed || !s.logged_in){ msg.innerHTML = '<a href="/connections.html">Garmin: connect</a>'; $('#sync').title = 'Log in to Garmin on the Connections page.'; }
  else if(s.running){ dot.classList.add('run'); msg.textContent = 'Syncing Garmin…'; }
  else if(s.last_error && (!s.last_success || s.last_error_at > s.last_success)){ dot.classList.add('err'); msg.textContent = 'Garmin sync failed'; $('#sync').title = s.last_error; }
  else if(s.last_success){ dot.classList.add('ok'); msg.textContent = `Garmin pulled ${ago(s.last_success)}${s.watch_upto?` · watch data to ${s.watch_upto.slice(0,10)===new Date(Date.now()+8*3600e3).toISOString().slice(0,10)?s.watch_upto.slice(11,16):fmtDate(s.watch_upto.slice(0,10))}`:''}`;
    $('#sync').title = (s.last_changes||[]).join('\n') || 'No changes in the last sync' + (s.last_push_ok===false ? '\nGitHub push failed — will retry' : ''); }
  else msg.textContent = 'Garmin: not synced yet';
  if(!s.running) garminToasts(s);
  if(syncWasRunning && !s.running){ await reloadData(); }
  syncWasRunning = !!s.running;
  clearTimeout(syncTimer); syncTimer = setTimeout(pollSync, s.running ? 3000 : 60000);
}
$('#syncbtn').onclick = async () => {
  $('#syncbtn').disabled = true;
  await post('/api/garmin/sync').catch(()=>{});
  pollSync();
};
// Toasts for problems with the scheduled Garmin pull. Each problem has a key; dismissing hides that key only.
const dismissed = (()=>{ try{ return JSON.parse(localStorage.getItem('ft-dismissed')||'{}'); }catch(e){ return {}; } })();
function dismiss(key){ dismissed[key] = 1; try{ localStorage.setItem('ft-dismissed', JSON.stringify(dismissed)); }catch(e){} }
function toast(key, kind, title, why, actions=[]){
  if(dismissed[key] || document.querySelector(`.toast[data-key="${CSS.escape(key)}"]`)) return;
  const el = document.createElement('div');
  el.className = 'toast ' + kind; el.dataset.key = key; el.setAttribute('role', kind==='err' ? 'alert' : 'status');
  el.innerHTML = `<span class="ic" aria-hidden="true">${kind==='err' ? '⛔' : '⚠️'}</span><b></b><span class="why"></span><div class="acts"></div>`;
  el.querySelector('b').textContent = title; el.querySelector('.why').textContent = why;
  const acts = el.querySelector('.acts');
  for(const [label, fn, primary] of [...actions, ['Dismiss', null]]){
    const b = document.createElement('button'); b.textContent = label; if(primary) b.className = 'primary';
    b.onclick = async () => { if(fn) await fn(); else dismiss(key); el.remove(); };
    acts.appendChild(b);
  }
  $('#toasts').appendChild(el);
}
function clearToasts(prefix){ document.querySelectorAll('.toast').forEach(t => { if(t.dataset.key.startsWith(prefix)) t.remove(); }); }
const syncAgain = ['Sync again', async () => { await post('/api/garmin/sync').catch(()=>{}); pollSync(); }, true];
function garminToasts(s){
  if(!s.ready) return;   // setup not finished: the header already says what to do
  const failed = s.last_error && (!s.last_success || s.last_error_at > s.last_success);
  if(failed) toast('err:'+s.last_error_at, 'err', 'Garmin sync failed', s.last_error, [syncAgain]);
  else clearToasts('err:');
  const lastOk = s.last_success ? new Date(s.last_success) : null;
  if(!failed && lastOk && (Date.now() - lastOk) > 26*3600e3)
    toast('stale:'+s.last_success, 'warn', 'Garmin hasn’t synced for a while', `Last successful sync ${ago(s.last_success)}. Is the dashboard service running and the Mac awake?`, [syncAgain]);
  if(s.last_push_ok === false)
    toast('push:'+(s.last_push_error_at||s.last_success), 'warn', 'GitHub backup failed', 'Your data is saved and committed on this Mac, but the push to GitHub failed. It retries on the next sync.');
  if(s.last_watch_date){
    const days = Math.floor((Date.now() - new Date(s.last_watch_date+'T23:59')) / 864e5);
    if(days >= 2) toast('nowatch:'+s.last_watch_date, 'warn', `No watch data since ${shortDate(s.last_watch_date)}`,
      `Syncs are working, but Garmin has nothing new for ${days} days. Is the watch charged, worn and synced to the Garmin app?`, [syncAgain]);
  }
  for(const w of (s.last_warnings||[]))
    toast(`part:${esc(w.date)}:${esc(w.part)}:${esc(s.last_success)}`, 'warn', `Garmin ${esc(w.part)} missing for ${shortDate(w.date)}`, w.error, [syncAgain]);
}

async function alertToasts(){
  const al = await api('/api/alerts').catch(()=>[]);
  for(const a of al) if(!a.id.startsWith('lab-')) toast(`alert:${esc(a.id)}:${esc(a.since)}`, 'warn', a.title, `${esc(a.text)} ${esc(a.todo)}`);
}
async function reloadData(){
  SUMMARY = await api('/api/summary'); HS = null; TRAIN = null; FOODS = null; SLEEP = null;  WO = null; BODY = null; REF = null; READY = null; renderAll();
}

/* ---------- boot ---------- */
function renderTab(t){
  if(t==='day') renderDay(currentDate);
  if(t==='longevity') renderLongevity();
  if(t==='advice') renderAdvice();
  if(t==='food') renderFood();
  if(t==='sleep') renderSleep();
  if(t==='wellbeing') renderWellbeing();
  if(t==='week') renderWeek(WEEK);
  if(t==='trends') renderTrends();
  if(t==='training') renderTraining();
  if(t==='recovery') renderRecovery();
  if(t==='body') renderBody();
  if(t==='timeline') renderTimeline();
}
function renderAll(){ renderTab((location.hash||'#day').slice(1)); }
/* ---------- profile: first-run setup (name, start date, timezone -> settings.yaml) ---------- */
let PROFILE = null;
function showWho(){   // a small profile icon, not the name: the name made the header wrap and pushed the sync status down
  const b = $('#who'); if(!b || !PROFILE) return;
  b.hidden = !PROFILE.name;
  const label = PROFILE.name ? `${esc(PROFILE.name)}: profile, start date and timezone` : 'Profile';
  b.title = label; b.setAttribute('aria-label', label);
  b.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="12" cy="8" r="4" fill="none" stroke="currentColor" stroke-width="2"/><path d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
}
function openSetup(first){
  const d = $('#setup'), f = $('#setupform'); if(!d || !PROFILE) return;
  $('#setup-h').textContent = first ? 'Welcome to Body Kaizen' : 'Your profile';
  const browserTz = (()=>{ try{ return Intl.DateTimeFormat().resolvedOptions().timeZone; }catch(e){ return ''; } })();
  f.name.value = PROFILE.name || '';
  f.start_date.value = PROFILE.start_date || PROFILE.suggested.start_date || '';
  f.timezone.value = PROFILE.timezone || browserTz || PROFILE.suggested.timezone || '';
  try { const tzs = Intl.supportedValuesOf ? Intl.supportedValuesOf('timeZone') : [];
        $('#tzlist').innerHTML = tzs.map(z => `<option value="${esc(z)}">`).join(''); } catch(e) {}
  $('#setuperr').textContent = ''; d.showModal(); f.name.focus();
}
async function saveSetup(ev){
  ev.preventDefault(); const f = $('#setupform');
  const body = {name: f.name.value, start_date: f.start_date.value, timezone: f.timezone.value.trim()};
  const r = await post('/api/setup', body).catch(()=>null);
  const j = r ? await r.json().catch(()=>({})) : {error:'The server did not answer.'};
  if(!r || !r.ok){ $('#setuperr').textContent = j.error || 'Could not save.'; return; }
  PROFILE = j; showWho(); $('#setup').close(); reloadData();
}
async function loadProfile(){
  PROFILE = await api('/api/profile').catch(()=>null); if(!PROFILE) return;
  showWho(); $('#who') && ($('#who').onclick = () => openSetup(false));
  $('#setupsave') && ($('#setupsave').onclick = saveSetup);
  if(PROFILE.needs_setup) openSetup(!PROFILE.name);
}
api('/api/summary').then(s => { SUMMARY = s; showTab((location.hash||'#day').slice(1)); pollSync(); alertToasts(); loadProfile(); })
  .catch(e => { $('main').innerHTML = `<p class="empty">Couldn't load data from the server (${esc(e.message)}). Check the terminal running app/server.py.</p>`; });
