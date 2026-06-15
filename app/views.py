import os
from flask import Blueprint, render_template, redirect, url_for, Response
from flask_login import login_required, current_user

bp = Blueprint("views", __name__)

# Bridge injected into the full tool: mirror its localStorage to the shared
# server store. Pull all keys on load (sync, before the app runs), then push
# every write/remove to the server so the whole team shares one dataset.
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
    if(this===window.localStorage){
      try{ fetch(BASE+'/'+encodeURIComponent(k),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:String(v)})}); }catch(e){}
    }
  };
  Storage.prototype.removeItem=function(k){
    _rem.call(this,k);
    if(this===window.localStorage){ try{ fetch(BASE+'/'+encodeURIComponent(k),{method:'DELETE'}); }catch(e){} }
  };
})();
</script>"""

_TOOL_HTML = None


def _tool_html():
    global _TOOL_HTML
    if _TOOL_HTML is None:
        path = os.path.join(os.path.dirname(__file__), "tool", "index.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        _TOOL_HTML = html.replace("<head>", "<head>" + _BRIDGE, 1)
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


# Rebuilt app (kept available; uses its own SQLite tables, separate from /tool)
@bp.route("/performance")
@login_required
def performance():
    return render_template("performance.html")


@bp.route("/daily")
@login_required
def daily():
    return render_template("daily.html")


@bp.route("/pva")
@login_required
def pva():
    return render_template("pva.html")


@bp.route("/subfleet")
@login_required
def subfleet():
    return render_template("subfleet.html")


@bp.route("/parameter")
@login_required
def parameter():
    return render_template("parameter.html")


@bp.route("/data")
@login_required
def data():
    return render_template("data.html")


@bp.route("/gps")
@login_required
def gps():
    return render_template("gps.html")


@bp.route("/plan")
@login_required
def plan():
    return render_template("plan.html")


@bp.route("/truckstatus")
@login_required
def truckstatus():
    return render_template("truckstatus.html")


@bp.route("/weigh")
@login_required
def weigh():
    return render_template("weigh.html")


@bp.route("/fleet")
@login_required
def fleet():
    return render_template("fleet.html")


@bp.route("/guide")
@login_required
def guide():
    return render_template("guide.html")


@bp.route("/dashboard")
@login_required
def dashboard():
    return redirect(url_for("views.tool"))
