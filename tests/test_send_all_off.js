// Send Plan: "Send all" (every planned driver in a row) is switched off (user 20/11/2026).
// Run: node tests/test_send_all_off.js
const fs = require('fs'), path = require('path'), vm = require('vm');
const html = fs.readFileSync(path.join(__dirname, '..', 'app', 'tool', 'index.html'), 'utf8');
let FAIL = 0;
const check = (l, g, w) => { const ok = g === w; if (!ok) FAIL++; console.log((ok ? '  PASS  ' : '  FAIL  ') + l.padEnd(52) + (ok ? '' : 'got ' + g + ' want ' + w)); };
check('switch is off', /const SEND_ALL_ENABLED=false;/.test(html), true);
check('button only drawn when the switch is on', html.includes("(SEND_ALL_ENABLED ? '<button class=\"send-all-btn\" id=\"sendAllBtn\""), true);
check('no other Send all button in the page', (html.match(/id="sendAllBtn"/g) || []).length, 1);
const i = html.indexOf('function _sendAllStart(list){'), j = html.indexOf('\n}', i) + 2;
const ctx = { SEND_ALL_ENABLED: false, started: 0, _ensureStepDom() { ctx.started++; }, _waRender() { ctx.started++; }, document: { getElementById: () => ({ classList: { add() { ctx.started++; } } }) } };
vm.createContext(ctx); vm.runInContext(html.slice(i, j) + '\n_sendAllStart([{plate:"20H01370"},{plate:"20H01381"}]);', ctx);
check('starting Send all does nothing', ctx.started, 0);
check('per-driver WhatsApp button still there', html.includes("el.querySelectorAll('.wa-send')"), true);
console.log(FAIL ? '\n' + FAIL + ' FAILED' : '\nall passed'); process.exit(FAIL ? 1 : 0);
