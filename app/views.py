import os
import json
from flask import Blueprint, render_template, redirect, url_for, Response, abort
from flask_login import login_required, current_user

bp = Blueprint("views", __name__)

# Mirror the tool's localStorage to the shared server store. Pull on load,
# push on write (unless the user is view-only).
_BRIDGE = """<script>
(function(){
  var BASE='/api/kv';
  try{
    var x=new XMLHttpRequest(); x.open('GET',BASE+'?_='+Date.now(),false); try{x.setRequestHeader('Cache-Control','no-store');}catch(e){} x.send();
    if(x.status===200){
      var d=JSON.parse(x.responseText||'{}');
      Object.keys(d).forEach(function(k){ if(k.indexOf('coalRpt')===0) return; try{ window.localStorage.setItem(k,d[k]); }catch(e){} });
    }
  }catch(e){ console.warn('shared-store pull failed', e); }
  var _set=Storage.prototype.setItem, _rem=Storage.prototype.removeItem;
  Storage.prototype.setItem=function(k,v){
    _set.call(this,k,v);
    if(this===window.localStorage && !window.__READONLY__){
      try{ fetch(BASE+'/'+encodeURIComponent(k),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:String(v)})}); }catch(e){}
    }
  };
  Storage.prototype.removeItem=function(k){
    _rem.call(this,k);
    if(this===window.localStorage && !window.__READONLY__){ try{ fetch(BASE+'/'+encodeURIComponent(k),{method:'DELETE'}); }catch(e){} }
  };
})();
</script>"""

# Apply per-user settings to the tool: username top-right, default language,
# allowed tabs, default landing page, and read-only (no uploads / no saving).
_GUARD = """<script>
(function(){
  var IDLE_MS=30*60*1000, timer;
  function reset(){ clearTimeout(timer); timer=setTimeout(function(){ try{location.href='/logout';}catch(e){} }, IDLE_MS); }
  ['mousemove','mousedown','keydown','scroll','touchstart','click'].forEach(function(ev){ document.addEventListener(ev, reset, {passive:true}); });
  reset();

  document.addEventListener('DOMContentLoaded', function(){
    fetch('/api/me').then(function(r){return r.json();}).then(function(me){
      if(!me) return;

      // username + links, top-right
      try{
        var btn=document.getElementById('exportHtmlBtn');
        if(btn && !document.getElementById('__whoami')){
          var html='<span id="__whoami" style="color:#fff;font-size:12px;opacity:.9">&#128100; '+(me.username||'')+'</span>';
          html+=' <a href="/" style="color:#9cd0ff;font-size:12px;text-decoration:none">Home</a>';
          if(me.is_admin) html+=' <a href="/admin" style="color:#9cd0ff;font-size:12px;text-decoration:none">Admin</a>';
          if(me.can_edit===false) html+=' <span style="background:#5a4a1a;color:#ffd479;font-size:11px;border-radius:999px;padding:1px 7px">view-only</span>';
          html+=' <a href="/logout" style="color:#9cd0ff;font-size:12px;text-decoration:none">Log out</a>';
          btn.insertAdjacentHTML('beforebegin', html);
        }
      }catch(e){}

      // default language
      try{
        var want=(me.lang==='vi')?'vi':'en';
        var lb=document.querySelector('#langToggle button[data-lang="'+want+'"]');
        if(lb && !lb.classList.contains('active')) lb.click();
      }catch(e){}

      // read-only: block uploads + saving/sharing
      if(me.can_edit===false){
        window.__READONLY__=true;
        try{
          document.querySelectorAll('input[type=file]').forEach(function(i){ i.disabled=true; });
          var css=document.createElement('style');
          css.textContent='[id$="Dz"],.dz,.dropzone{pointer-events:none!important;opacity:.5!important}';
          document.head.appendChild(css);
        }catch(e){}
      }

      // allowed tabs (hide the rest)
      var nav=document.getElementById('pageNav');
      if(nav && me.tabs){
        var allow={}; me.tabs.forEach(function(k){ allow[k]=1; });
        nav.querySelectorAll('button[data-page]').forEach(function(b){
          var k=b.getAttribute('data-perm')||b.getAttribute('data-page');
          if(!allow[k]) b.style.display='none';
        });
        var sub=['anchors','data','gps','plan','truckstatus','weigh','fleet'];
        if(!sub.some(function(k){return allow[k];})){ var di=document.getElementById('navDataInput'); if(di) di.style.display='none'; }
      }

      // default landing page, then fall back to first visible
      if(nav){
        var ok=function(k){ return !me.tabs || me.tabs.indexOf(k)>=0; };
        var target=null;
        if(me.default_page && ok(me.default_page)) target=Array.prototype.find.call(nav.querySelectorAll('button[data-page]'), function(b){ return (b.getAttribute('data-perm')||b.getAttribute('data-page'))===me.default_page; });
        var active=nav.querySelector('button[data-page].active');
        if(!target && active && active.style.display==='none'){
          target=Array.prototype.find.call(nav.querySelectorAll('button[data-page]'), function(b){ return b.style.display!=='none'; });
        }
        if(target) target.click();
      }
    }).catch(function(){});
  });
})();

(function(){
  var area=null, since=Date.now();
  function cur(){ var nav=document.getElementById('pageNav'); if(!nav) return null;
    var b=nav.querySelector('button[data-page].active'); if(!b) return null;
    var a=b.getAttribute('data-page'), sub=b.getAttribute('data-subtab'); return sub? a+':'+sub : a; }
  function send(a,sec){ if(!a||sec<1) return; try{ fetch('/api/track',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({page:a,seconds:sec}),keepalive:true}); }catch(e){} }
  function flush(){ var now=Date.now(), sec=Math.round((now-since)/1000); if(area) send(area,sec); since=now; }
  function setArea(){ flush(); area=cur(); }
  setTimeout(function(){ area=cur(); since=Date.now(); }, 1200);
  var nav=document.getElementById('pageNav');
  if(nav) nav.addEventListener('click', function(e){ if(e.target.closest('button[data-page]')) setTimeout(setArea,60); });
  setInterval(flush, 60000);
  document.addEventListener('visibilitychange', function(){ if(document.hidden) flush(); });
  window.addEventListener('beforeunload', flush);
})();
</script>"""

_TOOL_HTML = None


# Capture discrete user actions (tab opens, sorts, uploads, Calculate, exports,
# manual-time edits, language switches) via global event delegation — no tool
# internals are touched. Events are batched and flushed to /api/event.
_EVENTS = """<script>
(function(){
  var Q=[], lastK='', lastT=0;
  function push(action, detail){
    var k=action+'|'+detail, now=Date.now();
    if(k===lastK && (now-lastT)<1500) return;   // de-dupe rapid repeats
    lastK=k; lastT=now;
    Q.push({action:action, detail:String(detail||'').slice(0,300)});
    if(Q.length>=25) flush();
  }
  function flush(){
    if(!Q.length) return;
    var batch=Q.splice(0,Q.length);
    try{ fetch('/api/event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({events:batch}),keepalive:true}); }catch(e){}
  }
  function curTab(){
    var nav=document.getElementById('pageNav'); if(!nav) return '';
    var b=nav.querySelector('button[data-page].active'); return b? (b.textContent||'').trim() : '';
  }
  function txt(el){ return (el.textContent||'').replace(/[\\u25B2\\u25BC\\u2191\\u2193]/g,'').trim().slice(0,60); }

  document.addEventListener('click', function(e){
    var t=e.target;
    var nb=t.closest && t.closest('#pageNav button[data-page]');
    if(nb){ setTimeout(function(){ push('open_tab', curTab()); }, 80); return; }
    var th=t.closest && t.closest('th[data-dsort],th[data-sort]');
    if(th){ push('sort', txt(th) || th.getAttribute('data-dsort') || th.getAttribute('data-sort')); return; }
    var lb=t.closest && t.closest('#langToggle button[data-lang]');
    if(lb){ push('language', lb.getAttribute('data-lang')); return; }
    var cx=t.closest && t.closest('#dinCtxPop button');
    if(cx){ push('manual_time', txt(cx) || 'set'); return; }
    var btn=t.closest && t.closest('button,a.btn,[role=button]');
    if(btn){
      var s=txt(btn);
      if(/calculat/i.test(s)) push('calculate', s);
      else if(/export|download|baked|\\.xlsx|excel|\\bpng\\b|image|screenshot|\\bsave\\b/i.test(s)) push('export', s);
    }
  }, true);

  document.addEventListener('change', function(e){
    var i=e.target;
    if(i && i.tagName==='INPUT' && i.type==='file' && i.files && i.files.length){
      var names=[]; for(var j=0;j<i.files.length;j++) names.push(i.files[j].name);
      var ctx=curTab(); push('upload', (ctx?ctx+': ':'')+names.join(', '));
    }
  }, true);

  setInterval(flush, 4000);
  document.addEventListener('visibilitychange', function(){ if(document.hidden) flush(); });
  window.addEventListener('pagehide', flush);
  window.addEventListener('beforeunload', flush);
})();
</script>"""


def _tool_html():
    global _TOOL_HTML
    if _TOOL_HTML is None:
        path = os.path.join(os.path.dirname(__file__), "tool", "index.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        _TOOL_HTML = html.replace("<head>", "<head>" + _BRIDGE + _GUARD + _EVENTS, 1)
    return _TOOL_HTML



APPS = [("tms", "TMS : Coal project", "/tool"),
        ("report", "Daily/Weekly performance report", "/report")]


def _app_allowed(key):
    raw = getattr(current_user, "allowed_apps", None)
    if not raw:
        return True   # NULL = all apps
    try:
        return key in json.loads(raw)
    except Exception:
        return True


@bp.route("/")
@login_required
def index():
    apps = [{"key": k, "label": lbl, "url": url} for (k, lbl, url) in APPS if _app_allowed(k)]
    return render_template("hub.html", apps=apps,
                           username=current_user.username,
                           is_admin=getattr(current_user, "is_admin", False))


@bp.route("/tool")
@login_required
def tool():
    if not _app_allowed("tms"):
        return redirect(url_for("views.index"))
    return Response(_tool_html(), mimetype="text/html")


@bp.route("/report")
@login_required
def report():
    if not _app_allowed("report"):
        return redirect(url_for("views.index"))
    return render_template("report.html",
                           username=current_user.username,
                           is_admin=getattr(current_user, "is_admin", False))


@bp.route("/admin")
@login_required
def admin():
    if not getattr(current_user, "is_admin", False):
        abort(403)
    return render_template("admin.html")


@bp.route("/admin/activity")
@login_required
def admin_activity_page():
    if not getattr(current_user, "is_admin", False):
        abort(403)
    return render_template("activity.html")


# Rebuilt app pages (kept; separate SQLite-backed store from /tool)
def _page(name):
    @login_required
    def view():
        return render_template(name + ".html")
    view.__name__ = name
    return view


for _n in ["performance", "daily", "pva", "subfleet", "parameter", "data",
           "gps", "plan", "truckstatus", "weigh", "fleet", "guide"]:
    bp.add_url_rule("/" + _n, _n, _page(_n))


@bp.route("/dashboard")
@login_required
def dashboard():
    return redirect(url_for("views.tool"))
