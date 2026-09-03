// Which page the tool opens on, and whether a refresh comes back to it.
//
//   node tests/test_tool_landing.js            (extracts the guard itself)
//   node tests/test_tool_landing.js guard.js   (or point it at one)
//
// This exists because the bug it covers survived two fixes. Both times the
// code was in the served page and looked right; neither time did it run in the
// order the browser actually uses. Checking that a string is present proves
// nothing - so this executes the guard against a fake DOM in the real order:
// <head> runs, body is parsed with the markup default already active,
// DOMContentLoaded fires, and only then does /api/me resolve.
//
// The failure it locks down: the recorder fired on DOMContentLoaded, saw the
// markup's default still active, and rewrote the address bar before the
// restore - which waits on /api/me - had read it. #ops became #perf.
const fs = require('fs'), vm = require('vm');

function scenario({hash, default_page, tabs, guardJs}){
  const buttons = [];
  const mk = (page, subtab, active) => {
    const attrs = {'data-page': page};
    if (subtab) attrs['data-subtab'] = subtab;
    const b = {
      _cls: new Set(active ? ['active'] : []),
      style: {display: ''},
      getAttribute: k => (k in attrs ? attrs[k] : null),
      dataset: {page, subtab},
      classList: {
        contains: c => b._cls.has(c),
        toggle: (c, on) => { on ? b._cls.add(c) : b._cls.delete(c); }
      },
      closest: sel => (sel.indexOf('button[data-page]') >= 0 ? b : null),
      click(){ buttons.forEach(x => x.classList.toggle('active', x === b));
               nav._clicks.forEach(fn => fn({target: b})); },
      key: subtab ? page + ':' + subtab : page
    };
    buttons.push(b); return b;
  };
  // markup order from app/tool/index.html: ops first, perf carries .active
  mk('ops', null, false);
  mk('perf', null, true);
  mk('daily', null, false);
  mk('data', 'timeline', false);

  const nav = {
    _clicks: [],
    addEventListener: (ev, fn) => { if (ev === 'click') nav._clicks.push(fn); },
    querySelector: sel => sel === 'button[data-page].active'
      ? (buttons.find(b => b.classList.contains('active')) || null) : null,
    querySelectorAll: () => buttons
  };
  const domReady = [];
  const doc = {
    addEventListener: (ev, fn) => { if (ev === 'DOMContentLoaded') domReady.push(fn); },
    getElementById: id => (id === 'pageNav' ? nav : null),
    querySelector: () => null, querySelectorAll: () => []
  };

  let href = 'http://x/tool' + (hash ? '#' + hash : '');
  const win = {
    location: { get hash(){ const i = href.indexOf('#'); return i < 0 ? '' : href.slice(i); },
                get href(){ return href; }, set href(v){ href = v; } },
    history: { replaceState: (a, b2, url) => { href = 'http://x/tool' + url; } },
    localStorage: { getItem: () => null, setItem: () => {} },
    addEventListener: () => {}, removeEventListener: () => {}
  };
  const me = {username: 'tester', default_page, tabs, is_admin: true};
  const timers = [];
  const sandbox = {
    window: win, document: doc, history: win.history, location: win.location,
    setTimeout, clearTimeout, console,
    setInterval: (fn, ms) => { const id = setInterval(fn, ms); timers.push(id); return id; },
    fetch: () => Promise.resolve({json: () => Promise.resolve(me), ok: true}),
    XMLHttpRequest: function(){ this.open = () => {}; this.send = () => {};
                                this.setRequestHeader = () => {}; },
    Array, Object, JSON, Date, Math, decodeURIComponent, encodeURIComponent
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(guardJs, sandbox, {filename: 'guard.js'});   // <head>
  domReady.forEach(f => f());                                   // DOM ready
  // 200ms: the recorder deliberately waits 60ms after a click before writing.
  return new Promise(res => setTimeout(() => {
    timers.forEach(clearInterval);
    const active = buttons.find(b => b.classList.contains('active'));
    res({active: active ? active.key : null, hash: win.location.hash});
  }, 200));
}

(async () => {
  let src = process.argv[2];
  if (!src){
    const py = fs.readFileSync(require('path').join(__dirname, '..', 'app', 'views.py'), 'utf8');
    const m = py.match(/_GUARD = """([\s\S]*?)"""/);
    if (!m){ console.error('could not find _GUARD in app/views.py'); process.exit(2); }
    var guardJs = m[1].replace('<script>', '').replace('</script>', '');
  } else {
    var guardJs = fs.readFileSync(src, 'utf8');
  }
  const cases = [
    ['refresh on #ops (the reported bug)', {hash: 'ops',  default_page: 'perf'}, 'ops'],
    ['refresh on #data:timeline',          {hash: 'data:timeline', default_page: 'perf'}, 'data:timeline'],
    ['fresh login, no hash, default ops',  {hash: '',     default_page: 'ops'},  'ops'],
    ['fresh login, no hash, default perf', {hash: '',     default_page: 'perf'}, 'perf'],
    ['hash wins over default',             {hash: 'daily', default_page: 'ops'}, 'daily'],
    ['unknown hash falls back to default', {hash: 'nope', default_page: 'ops'},  'ops'],
  ];
  let bad = 0;
  for (const [name, opts, want] of cases){
    const r = await scenario({...opts, guardJs});
    const ok = r.active === want && r.hash === '#' + want;
    if (!ok) bad++;
    console.log((ok ? '  PASS  ' : '  FAIL  ') + name.padEnd(36)
      + ' active=' + String(r.active).padEnd(14) + ' url=' + r.hash
      + (ok ? '' : '   expected ' + want));
  }
  console.log(bad ? '\n  ' + bad + ' FAILING' : '\n  all pass');
  process.exit(bad ? 1 : 0);
})();
