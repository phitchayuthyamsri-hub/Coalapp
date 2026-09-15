/* Dates are shown DD/MM/YYYY across the whole program.
 *
 * They are stored, compared, sorted and sent as YYYY-MM-DD - that form sorts as
 * text and every date function understands it - so this changes only what a
 * person reads. Two parts:
 *
 *   DateFmt.dmy(iso) / DateFmt.dt(date)   for code that builds date text itself;
 *   a watcher that rewrites any YYYY-MM-DD left in the page's visible text, so a
 *   date nobody remembered to format still reads day first.
 *
 * Form fields, scripts, code blocks and anything inside [data-raw-date] are
 * never touched, so nothing typed, saved or sent is altered - only the words on
 * the screen.
 */
(function (global) {
  'use strict';

  var SEP = '/';                      // the one place the separator is chosen

  function p2(n) { return (n < 10 ? '0' : '') + n; }

  // '2026-09-16' (or '2026-09-16T05:00') -> '16/09/2026'
  function dmy(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso == null ? '' : iso));
    return m ? m[3] + SEP + m[2] + SEP + m[1] : (iso == null ? '' : String(iso));
  }

  // a Date, or anything Date understands -> '16/09/2026 05:00'
  function dt(d) {
    if (!(d instanceof Date)) d = new Date(d);
    if (isNaN(d.getTime())) return '';
    return p2(d.getDate()) + SEP + p2(d.getMonth() + 1) + SEP + d.getFullYear()
      + ' ' + p2(d.getHours()) + ':' + p2(d.getMinutes());
  }

  // A real calendar date, optionally with a time, not glued to other digits or
  // dashes - so '20260916' in a file name or '2026-13-01' are left alone.
  var RE = /(^|[^\d\-\/])(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?:[T ]([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d(?:\.\d+)?)?)?(?![\d\-])/g;

  function text(s) {
    return String(s).replace(RE, function (all, pre, y, mo, d, hh, mi) {
      return pre + d + SEP + mo + SEP + y + (hh ? ' ' + hh + ':' + mi : '');
    });
  }

  var SKIP = {SCRIPT: 1, STYLE: 1, TEXTAREA: 1, INPUT: 1, NOSCRIPT: 1, CODE: 1, PRE: 1};

  function skipped(node) {
    for (var el = node.parentNode; el && el.nodeType === 1; el = el.parentNode) {
      if (SKIP[el.nodeName] || el.isContentEditable
          || (el.hasAttribute && el.hasAttribute('data-raw-date'))) return true;
    }
    return false;
  }

  function fix(node) {
    var v = node.nodeValue;
    if (!v || v.length < 10 || v.indexOf('-') < 0) return;
    RE.lastIndex = 0;
    if (!RE.test(v)) return;
    if (skipped(node)) return;
    var nv = text(v);
    if (nv !== v) node.nodeValue = nv;
  }

  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { fix(root); return; }
    if (root.nodeType !== 1 || SKIP[root.nodeName]) return;
    var w = document.createTreeWalker(root, 4 /* NodeFilter.SHOW_TEXT */, null);
    var n;
    while ((n = w.nextNode())) fix(n);
  }

  var pending = [], queued = false;

  function flush() {
    queued = false;
    var list = pending;
    pending = [];
    for (var i = 0; i < list.length; i++) walk(list[i]);
  }

  function queue(node) {
    pending.push(node);
    if (queued) return;
    queued = true;
    // Before the browser paints, so a raw date is never seen flickering.
    if (global.queueMicrotask) global.queueMicrotask(flush);
    else setTimeout(flush, 0);
  }

  function start() {
    walk(document.body);
    if (!global.MutationObserver) return;
    new global.MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var m = muts[i];
        if (m.type === 'characterData') queue(m.target);
        else for (var j = 0; j < m.addedNodes.length; j++) queue(m.addedNodes[j]);
      }
    }).observe(document.documentElement, {childList: true, subtree: true, characterData: true});
  }

  global.DateFmt = {dmy: dmy, dt: dt, text: text, SEP: SEP};

  if (typeof document !== 'undefined' && document.documentElement) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
  }
})(window);
