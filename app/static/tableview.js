/* Sort and filter for a table the page draws itself.
 *
 * The grid on the declaration page owns its cells. This one does not: the
 * supervisor's table is full of live inputs the page renders and reads back by
 * row index, so the ordering has to change without the indices moving.
 *
 * So this keeps a `view` - the row indexes to draw, in the order to draw them -
 * and hands it back. The page keeps emitting data-i as the ORIGINAL index, and
 * everything that collects the form still works whatever order it is looking at.
 * The same idea as the grid, and for the same reason: sorting a page must never
 * move somebody's edit onto a different truck.
 */
(function (global) {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }

  function cmpVal(a, b) {
    var sa = String(a == null ? '' : a).trim(), sb = String(b == null ? '' : b).trim();
    if (sa === '' && sb === '') return 0;
    if (sa === '') return 1;
    if (sb === '') return -1;
    var looksDate = /^\d{4}-\d{2}-\d{2}/;
    if (looksDate.test(sa) && looksDate.test(sb)) return Date.parse(sa) - Date.parse(sb);
    var na = Number(sa), nb = Number(sb);
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return sa.localeCompare(sb, undefined, {numeric: true, sensitivity: 'base'});
  }

  /* cols: [{key, label, get(row)}] - get() so a column can read something the
   * row does not literally hold, like a badge's text. */
  function TableView(opts) {
    this.cols = opts.cols;
    this.rows = [];
    this.sortSeq = [];
    this.filters = {};
    this.onChange = opts.onChange || function () {};
    this.menu = null;
    this.menuKey = null;
    var self = this;
    document.addEventListener('mousedown', function (e) {
      if (self.menu && !self.menu.contains(e.target)) self.close();
    });
  }

  TableView.prototype.val = function (row, col) {
    return col.get ? col.get(row) : row[col.key];
  };

  /* What the FILTER offers, which is not always what the sort compares.
   *
   * A column of arrival times sorts by the time and by nothing else. But a
   * filter list of times is one line per truck - fifty-eight choices, none of
   * them a question anybody asks. What is asked of that column is "show me the
   * late ones", so a column may name a second, coarser value for the menu while
   * the ordering still runs on the real clock. */
  TableView.prototype.fval = function (row, col) {
    return col.fget ? col.fget(row) : this.val(row, col);
  };

  TableView.prototype.view = function (rows) {
    var self = this;
    if (rows) this.rows = rows;
    var idx = this.rows.map(function (_r, i) { return i; });

    idx = idx.filter(function (i) {
      for (var k in self.filters) {
        var allow = self.filters[k];
        if (!allow) continue;
        var col = self.byKey(k);
        if (!col) continue;
        var fv = self.fval(self.rows[i], col);
        if (!allow.has(String(fv == null ? '' : fv))) return false;
      }
      return true;
    });

    if (this.sortSeq.length) {
      idx.sort(function (a, b) {
        for (var i = 0; i < self.sortSeq.length; i++) {
          var lv = self.sortSeq[i], col = self.byKey(lv.key);
          if (!col) continue;
          var va = self.val(self.rows[a], col), vb = self.val(self.rows[b], col);
          var ea = String(va == null ? '' : va).trim() === '';
          var eb = String(vb == null ? '' : vb).trim() === '';
          if (ea !== eb) return ea ? 1 : -1;      // blanks last, both directions
          if (ea && eb) continue;
          var n = cmpVal(va, vb);
          if (n) return lv.asc ? n : -n;
        }
        return a - b;
      });
    }
    return idx;
  };

  TableView.prototype.byKey = function (k) {
    for (var i = 0; i < this.cols.length; i++) if (this.cols[i].key === k) return this.cols[i];
    return null;
  };

  TableView.prototype.level = function (k) {
    for (var i = 0; i < this.sortSeq.length; i++) if (this.sortSeq[i].key === k) return i;
    return -1;
  };

  TableView.prototype.active = function (k) { return !!this.filters[k]; };

  /* Header cell contents: the label, a sort badge and the arrow. */
  TableView.prototype.head = function (col) {
    var lv = this.level(col.key);
    var badge = lv < 0 ? ''
      : '<span class="hsort">' + (this.sortSeq[lv].asc ? '▲' : '▼')
        + (this.sortSeq.length > 1 ? (lv + 1) : '') + '</span>';
    return '<th data-col="' + esc(col.key) + '"'
      + (col.rowspan ? ' rowspan="' + col.rowspan + '"' : '')
      + ' class="hd' + (col.cls ? ' ' + col.cls : '')
      + (this.active(col.key) ? ' filt-on' : '') + '">'
      + '<span class="hl">' + esc(col.label) + badge + '</span>'
      + (col.hint ? '<span class="hh">' + esc(col.hint) + '</span>' : '')
      + '<span class="harrow">▾</span></th>';
  };

  TableView.prototype.wire = function (table) {
    var self = this;
    Array.prototype.forEach.call(table.querySelectorAll('th[data-col]'), function (th) {
      th.onclick = function (e) { self.open(e, th.dataset.col); };
    });
  };

  TableView.prototype.close = function () {
    if (this.menu && this.menu.parentNode) this.menu.parentNode.removeChild(this.menu);
    this.menu = null;
    this.menuKey = null;
  };

  TableView.prototype.open = function (ev, key) {
    ev.stopPropagation();
    var self = this, col = this.byKey(key);
    if (!col) return;
    if (this.menu && this.menuKey === key) { this.close(); return; }
    this.close();
    this.menuKey = key;

    var m = document.createElement('div');
    m.className = 'col-menu';
    m.innerHTML =
      '<div class="cm-sort"><button data-s="az">▲ Sort A→Z</button>'
      + '<button data-s="za">▼ Sort Z→A</button></div>'
      + '<div class="cm-sort cm-sort2"><button data-s="+az">+ then A→Z</button>'
      + '<button data-s="+za">+ then Z→A</button></div>'
      + '<div class="cm-seq"></div>'
      + '<input class="cm-search" placeholder="Search values…">'
      + '<div class="cm-list"></div>'
      + '<div class="cm-actions"><button data-a="all">All</button>'
      + '<button data-a="none">None</button>'
      + '<button class="cm-apply" data-a="apply">Apply</button></div>';
    document.body.appendChild(m);
    this.menu = m;

    if (this.sortSeq.length) {
      m.querySelector('.cm-seq').innerHTML = '<div class="cm-seq-in"><b>Sorted by</b> '
        + this.sortSeq.map(function (lv, i) {
            var c = self.byKey(lv.key);
            return '<span class="cm-seq-tag">' + (i + 1) + '. '
              + esc(c ? (c.tag || c.label) : lv.key) + ' ' + (lv.asc ? '▲' : '▼')
              + '</span>'; }).join(' ')
        + '<button data-a="clearsort">Clear sorting</button></div>';
    }

    var counts = {};
    this.rows.forEach(function (r) {
      var v = String(self.fval(r, col) == null ? '' : self.fval(r, col));
      counts[v] = (counts[v] || 0) + 1;
    });
    var allow = this.filters[key];
    m.querySelector('.cm-list').innerHTML = Object.keys(counts).sort(cmpVal).map(function (v) {
      return '<label class="cm-item"><input type="checkbox" value="' + esc(v) + '"'
        + ((!allow || allow.has(v)) ? ' checked' : '') + '>'
        + '<span>' + (v === '' ? '(blank)' : esc(v)) + '</span>'
        + '<i>' + counts[v] + '</i></label>';
    }).join('');

    m.addEventListener('click', function (e) { e.stopPropagation(); });
    m.querySelector('.cm-search').addEventListener('input', function () {
      var q = this.value.toLowerCase();
      Array.prototype.forEach.call(m.querySelectorAll('.cm-item'), function (li) {
        li.style.display = li.textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
      });
    });
    m.addEventListener('mousedown', function (e) {
      var b = e.target.closest('button');
      if (!b) return;
      e.preventDefault();
      var sc = b.dataset.s, a = b.dataset.a;
      if (sc === 'az' || sc === 'za') {
        self.sortSeq = [{key: key, asc: sc === 'az'}];
      } else if (sc === '+az' || sc === '+za') {
        var at = self.level(key);
        if (at >= 0) self.sortSeq[at].asc = (sc === '+az');
        else self.sortSeq.push({key: key, asc: sc === '+az'});
      } else if (a === 'clearsort') {
        self.sortSeq = [];
      } else if (a === 'all' || a === 'none') {
        Array.prototype.forEach.call(m.querySelectorAll('.cm-item'), function (li) {
          if (li.style.display !== 'none') li.querySelector('input').checked = (a === 'all');
        });
        return;                                  // stay open while ticking
      } else if (a === 'apply') {
        var boxes = Array.prototype.slice.call(m.querySelectorAll('.cm-item input'));
        var on = boxes.filter(function (x) { return x.checked; })
                      .map(function (x) { return x.value; });
        if (on.length === boxes.length) delete self.filters[key];
        else self.filters[key] = new Set(on);
      } else {
        return;
      }
      self.close();
      self.onChange();
    });

    var r = ev.target.closest('th').getBoundingClientRect();
    m.style.left = Math.max(4, Math.min(r.left + window.scrollX,
                            window.innerWidth - m.offsetWidth - 8)) + 'px';
    var want = Math.min(m.offsetHeight || 320, window.innerHeight * 0.7);
    m.style.top = ((window.innerHeight - r.bottom < want + 8 && r.top > want + 8)
      ? Math.max(4, r.top + window.scrollY - want - 2)
      : r.bottom + window.scrollY + 2) + 'px';
    var sf = m.querySelector('.cm-search');
    if (sf) sf.focus();
  };

  TableView.prototype.filtered = function () {
    for (var k in this.filters) if (this.filters[k]) return true;
    return false;
  };

  global.TableView = TableView;
})(window);
