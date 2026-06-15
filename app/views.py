import os
from flask import Blueprint, render_template, redirect, url_for, Response, abort
from flask_login import login_required, current_user

bp = Blueprint("views", __name__)

# Mirror the tool's localStorage to the shared server store. Pull on load,
# push on write (unless the user is view-only).
_BRIDGE = """<script>
(function(){
  var BASE='/api/kv';
  try{
    var x=new XMLHttpRequest(); x.open('GET',BASE,false); x.send();
    if(x.status===200){
      var d=JSON.parse(x.responseText||'{}');
      Object.keys(d).forEach(function(k){ try{ window.localStorage.setItem(k,d[k]); }catch(e){} });
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
          if(!allow[b.getAttribute('data-page')]) b.style.display='none';
        });
        var sub=['anchors','data','gps','plan','truckstatus','weigh','fleet'];
        if(!sub.some(function(k){return allow[k];})){ var di=document.getElementById('navDataInput'); if(di) di.style.display='none'; }
      }

      // default landing page, then fall back to first visible
      if(nav){
        var ok=function(k){ return !me.tabs || me.tabs.indexOf(k)>=0; };
        var target=null;
        if(me.default_page && ok(me.default_page)) target=nav.querySelector('button[data-page="'+me.default_page+'"]');
        var active=nav.querySelector('button[data-page].active');
        if(!target && active && active.style.display==='none'){
          target=Array.prototype.find.call(nav.querySelectorAll('button[data-page]'), function(b){ return b.style.display!=='none'; });
        }
        if(target) target.click();
      }
    }).catch(function(){});
  });
})();
</script>"""

_TOOL_HTML = None


def _tool_html():
    global _TOOL_HTML
    if _TOOL_HTML is None:
        path = os.path.join(os.path.dirname(__file__), "tool", "index.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        _TOOL_HTML = html.replace("<head>", "<head>" + _BRIDGE + _GUARD, 1)
    return _TOOL_HTML


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("views.tool"))
    return redirect(url_for("auth.login"))


@bp.route("/tool")
@login_required
def tool():
    return Response(_tool_html(), mimetype="text/html")


@bp.route("/admin")
@login_required
def admin():
    if not getattr(current_user, "is_admin", False):
        abort(403)
    return render_template("admin.html")


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
