/* When the session is gone, go to the login page - do not sit on stale data.
 *
 * Sessions are signed cookies. Rotating the server's key, or a session
 * timing out, makes every open tab's cookie unreadable - but nothing told the
 * tab. Pages that poll got 401 after 401 and kept showing whatever they last
 * had; pages that do not poll looked fine until a click. "Log everyone out"
 * therefore meant "log everyone out and hope they refresh". This script is
 * the hope, made mechanical:
 *
 *   - any same-origin fetch that comes back 401 sends the tab to /login,
 *     keeping the page it was on so login brings it straight back;
 *   - a heartbeat asks /api/me once a minute for the pages that never fetch,
 *     so a rotated key reaches them within the minute;
 *   - a framed page moves the TOP window, not the frame, so the login page is
 *     never drawn inside an iframe of the page it is replacing.
 *
 * Nothing here logs anyone out. It only notices that they already are.
 */
(function (w) {
  'use strict';
  if (!w || w.__sessionGuard) return;
  w.__sessionGuard = true;

  var top_ = (function () { try { return w.top && w.top.location.origin === w.location.origin ? w.top : w; } catch (e) { return w; } })();

  function onLogin() {
    return /^\/login(\/|$|\?)/.test(top_.location.pathname);
  }

  function goLogin() {
    if (onLogin()) return;
    var back = top_.location.pathname + top_.location.search + top_.location.hash;
    top_.location.href = '/login?next=' + encodeURIComponent(back);
  }

  // Every fetch this page makes: a 401 means the session is gone.
  if (typeof w.fetch === 'function') {
    var realFetch = w.fetch;
    w.fetch = function (input, init) {
      return realFetch.call(w, input, init).then(function (r) {
        try {
          var u = typeof input === 'string' ? input : (input && input.url) || '';
          var sameOrigin = u.charAt(0) === '/' || u.indexOf(w.location.origin) === 0;
          if (r && r.status === 401 && sameOrigin) goLogin();
        } catch (e) {}
        return r;
      });
    };
  }

  // XMLHttpRequest too - the tool's bridge still uses it.
  if (w.XMLHttpRequest && w.XMLHttpRequest.prototype) {
    var proto = w.XMLHttpRequest.prototype, realOpen = proto.open;
    proto.open = function (method, url) {
      try {
        var u = String(url || '');
        if (u.charAt(0) === '/' || u.indexOf(w.location.origin) === 0) {
          this.addEventListener('load', function () { if (this.status === 401) goLogin(); });
        }
      } catch (e) {}
      return realOpen.apply(this, arguments);
    };
  }

  // The heartbeat, for pages that never ask the server anything.
  function beat() {
    if (onLogin() || document.hidden) return;
    try {
      (w.__origFetch || w.fetch)('/api/me', { credentials: 'same-origin', cache: 'no-store' })
        .then(function (r) { if (r.status === 401) goLogin(); })
        .catch(function () {});
    } catch (e) {}
  }
  w.setInterval(beat, 60000);
  w.setTimeout(beat, 1500);
})(typeof window !== 'undefined' ? window : null);
