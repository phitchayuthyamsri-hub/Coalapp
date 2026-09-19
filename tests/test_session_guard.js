// A tab whose login is gone goes to the login page; one that is fine is left alone.
//
// "Log everyone out" used to mean rotating the key and hoping people refreshed.
// Pages that poll got 401 after 401 and kept showing stale data. This is the
// guard that makes the hope mechanical.
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync('app/static/session_guard.js', 'utf8');

let fail = 0;
function is(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want); if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(58)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}

// A stub window: same-origin fetch answering with a chosen status.
function mkWindow({status, path, framed}){
  const timers = [];
  const loc = {origin: 'http://box', pathname: path || '/monitor', search: '', hash: '#x', href: ''};
  const w = {
    location: loc,
    document: {hidden: false},
    setInterval: (fn, ms) => { timers.push({fn, ms, kind: 'interval'}); return 1; },
    setTimeout: (fn, ms) => { timers.push({fn, ms, kind: 'timeout'}); return 2; },
    fetch: () => Promise.resolve({status}),
    XMLHttpRequest: function(){},
    __timers: timers,
  };
  w.XMLHttpRequest.prototype = {open(){ this._opened = true; }, addEventListener(){}};
  w.top = framed ? {location: {origin: 'http://box', pathname: '/tool', search: '', hash: '#ops', href: ''}} : w;
  vm.runInNewContext(src, {window: w, document: w.document, XMLHttpRequest: w.XMLHttpRequest});
  return w;
}

(async () => {
  console.log('a fetch that comes back 401');
  let w = mkWindow({status: 401});
  await w.fetch('/api/shift/track');
  is('sends the tab to the login page', w.location.href.startsWith('/login?next='), true);
  is('...remembering where it was', decodeURIComponent(w.location.href.split('next=')[1]), '/monitor#x');

  console.log('\na fetch that is fine');
  w = mkWindow({status: 200});
  await w.fetch('/api/shift/track');
  is('leaves the tab alone', w.location.href, '');

  console.log('\nan off-site fetch that is 401');
  w = mkWindow({status: 401});
  await w.fetch('https://mt1.google.com/vt/x');
  is('is none of our business', w.location.href, '');

  console.log('\nalready on the login page');
  w = mkWindow({status: 401, path: '/login'});
  await w.fetch('/api/me');
  is('never redirects to itself', w.location.href, '');

  console.log('\ninside an iframe of the tool');
  w = mkWindow({status: 401, framed: true});
  await w.fetch('/api/shift/list');
  is('the TOP window moves, not the frame', w.top.location.href.startsWith('/login?next='), true);
  is('...back to the page the frame was in', decodeURIComponent(w.top.location.href.split('next=')[1]), '/tool#ops');
  is('...and the frame itself is untouched', w.location.href, '');

  console.log('\nthe heartbeat');
  w = mkWindow({status: 401});
  const beat = w.__timers.find(t => t.kind === 'interval');
  is('asks once a minute', beat && beat.ms, 60000);
  const first = w.__timers.find(t => t.kind === 'timeout');
  is('...and once soon after load', first && first.ms, 1500);
  w.fetch = () => Promise.resolve({status: 401});
  beat.fn(); await new Promise(r => setTimeout(r, 5));
  is('a 401 heartbeat sends the tab to login', w.location.href.startsWith('/login?next='), true);
  w = mkWindow({status: 401}); w.document.hidden = true;
  w.__timers.find(t => t.kind === 'interval').fn(); await new Promise(r => setTimeout(r, 5));
  is('a hidden tab does not beat', w.location.href, '');

  console.log('\nloading twice');
  w = mkWindow({status: 401});
  const before = w.fetch;
  vm.runInNewContext(src, {window: w, document: w.document, XMLHttpRequest: w.XMLHttpRequest});
  is('does not wrap fetch a second time', w.fetch === before, true);

  console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
  process.exit(fail ? 1 : 0);
})();
