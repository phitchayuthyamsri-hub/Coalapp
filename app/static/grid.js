/* A small spreadsheet, for people who already know how to use one.
 *
 * The declaration page had a drop-down in every cell: fifty-eight trucks times
 * three lists is a hundred and seventy-four clicks to say something most days
 * amounts to "same as yesterday". So the grid behaves the way the tool these
 * people actually use behaves - arrows move, typing sets, Ctrl+D fills down, a
 * block copied out of Excel pastes straight in, and the headers sort and filter.
 *
 * The one idea worth knowing: `view` is the list of row indexes currently on
 * screen, in the order they appear. Everything the user touches is addressed by
 * position in the view; everything written goes to the underlying row. Sorting
 * or filtering therefore cannot move somebody's edit onto a different truck.
 */
(function (global) {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }

  // Times arrive as 6, 600, 6:00, 6.00, 0600 - all meaning the same thing.
  function normTime(v) {
    var s = String(v == null ? '' : v).trim();
    if (!s) return '';
    var m = s.match(/^(\d{1,2})[:.h]?(\d{2})$/) || s.match(/^(\d{1,2})$/);
    if (!m) return null;
    var h = parseInt(m[1], 10), mi = m[2] ? parseInt(m[2], 10) : 0;
    if (h > 23 || mi > 59) return null;
    return (h < 10 ? '0' + h : '' + h) + ':' + (mi < 10 ? '0' + mi : '' + mi);
  }

  // Dates first, then numbers, then text; blanks always last. Copied in spirit
  // from the Logistics grid so both tables sort a column the same way.
  function cmpVal(a, b) {
    var sa = String(a == null ? '' : a).trim(), sb = String(b == null ? '' : b).trim();
    if (sa === '' && sb === '') return 0;
    if (sa === '') return 1;
    if (sb === '') return -1;
    var da = Date.parse(sa), db = Date.parse(sb);
    var looksDate = /^\d{4}-\d{2}-\d{2}/;
    if (looksDate.test(sa) && looksDate.test(sb) && !isNaN(da) && !isNaN(db)) return da - db;
    var na = Number(sa), nb = Number(sb);
    if (sa !== '' && sb !== '' && !isNaN(na) && !isNaN(nb)) return na - nb;
    return sa.localeCompare(sb, undefined, {numeric: true, sensitivity: 'base'});
  }

  function Grid(opts) {
    this.table = opts.table;
    this.cols = opts.cols;
    this.rows = opts.rows;
    this.onChange = opts.onChange || function () {};
    this.render = opts.render || {};
    this.rowClass = opts.rowClass || function () { return ''; };
    // A sequence, not one column: "sort by company, then by time" is the
    // question people actually ask of a truck list.
    this.sortSeq = [];                    // [{c, asc}]
    this.filters = {};                    // colKey -> Set of allowed values
    this.view = [];
    this.cur = {r: 0, c: this.firstEditable()};
    this.anchor = {r: 0, c: this.cur.c};
    this.typeBuf = '';
    this.typeAt = 0;
    this.editing = null;
    this.menu = null;
    // Looking is not changing: a read-only grid still sorts, filters, selects
    // and copies. It just cannot write.
    this.readOnly = !!opts.readOnly;
    this.applyView();
    this.wire();
  }

  Grid.prototype.firstEditable = function () {
    for (var i = 0; i < this.cols.length; i++) if (!this.cols[i].ro) return i;
    return 0;
  };

  // ── which rows are on screen, and in what order ──────────────────────────
  Grid.prototype.applyView = function () {
    var self = this;
    var idx = this.rows.map(function (_r, i) { return i; });

    idx = idx.filter(function (i) {
      for (var k in self.filters) {
        var allow = self.filters[k];
        if (!allow) continue;
        var got = String(self.rows[i][k] == null ? '' : self.rows[i][k]);
        if (!allow.has(got)) return false;
      }
      return true;
    });

    if (this.sortSeq.length) {
      var seq = this.sortSeq.map(function (lv) {
        return {key: self.cols[lv.c].key, asc: lv.asc};
      });
      idx.sort(function (a, b) {
        for (var i = 0; i < seq.length; i++) {
          var va = self.rows[a][seq[i].key], vb = self.rows[b][seq[i].key];
          var ea = String(va == null ? '' : va).trim() === '';
          var eb = String(vb == null ? '' : vb).trim() === '';
          // Blanks last whichever way the column points. An empty cell is not a
          // small value, it is a missing one, and burying the rows nobody has
          // answered at the top of a descending sort is the opposite of useful.
          if (ea !== eb) return ea ? 1 : -1;
          if (ea && eb) continue;
          var n = cmpVal(va, vb);
          if (n) return seq[i].asc ? n : -n;
        }
        return a - b;                     // stable: original order breaks ties
      });
    }
    this.view = idx;
    if (this.cur.r >= this.view.length) this.cur.r = Math.max(0, this.view.length - 1);
    if (this.anchor.r >= this.view.length) this.anchor.r = this.cur.r;
  };

  Grid.prototype.colByKey = function (k) {
    for (var i = 0; i < this.cols.length; i++) if (this.cols[i].key === k) return this.cols[i];
    return null;
  };
  Grid.prototype.rowAt = function (vr) { return this.rows[this.view[vr]]; };

  // ── drawing ──────────────────────────────────────────────────────────────
  Grid.prototype.draw = function () {
    var self = this;
    var head = '<tr>' + this.cols.map(function (c, ci) {
      var lv = self.sortLevel(ci);
      var badge = lv < 0 ? ''
        : '<span class="hsort">' + (self.sortSeq[lv].asc ? '▲' : '▼')
          + (self.sortSeq.length > 1 ? (lv + 1) : '') + '</span>';
      var on = self.filters[c.key] ? ' filt-on' : '';
      return '<th data-c="' + ci + '"' + (c.width ? ' style="width:' + c.width + '"' : '')
        + ' class="hd' + on + '">'
        + '<span class="hl">' + esc(c.label) + badge + '</span>'
        + (c.hint ? '<span class="hh">' + esc(c.hint) + '</span>' : '')
        + '<span class="harrow">▾</span>'
        + '</th>';
    }).join('') + '</tr>';

    var body = this.view.map(function (ri, vr) {
      var row = self.rows[ri];
      var tds = self.cols.map(function (c, ci) {
        var val = row[c.key];
        var shown = self.render[c.key] ? self.render[c.key](row, val) : esc(val || '');
        return '<td data-r="' + vr + '" data-c="' + ci + '"'
          + (c.ro ? ' class="ro"' : '') + '>' + shown + '</td>';
      }).join('');
      return '<tr class="' + self.rowClass(row) + '">' + tds + '</tr>';
    }).join('');

    this.table.innerHTML = '<thead>' + head + '</thead><tbody>' + body + '</tbody>';
    this.paint();
    this.wireHead();
  };

  Grid.prototype.sortLevel = function (ci) {
    for (var i = 0; i < this.sortSeq.length; i++) if (this.sortSeq[i].c === ci) return i;
    return -1;
  };

  Grid.prototype.wireHead = function () {
    var self = this;
    Array.prototype.forEach.call(this.table.querySelectorAll('th'), function (th) {
      th.onclick = function (e) { self.openColMenu(e, +th.dataset.c); };
    });
  };

  // ── the column menu ──────────────────────────────────────────────────────
  // Sort, then sort again by something else, then tick the values you want.
  // The same shape as the Logistics grid, because these are the same people.
  Grid.prototype.openColMenu = function (ev, ci) {
    ev.stopPropagation();
    var self = this, col = this.cols[ci];
    if (this.cmenu && this.cmKey === ci) { this.closeColMenu(); return; }
    this.closeColMenu();
    this.closeMenu();
    this.cmKey = ci;

    var m = document.createElement('div');
    m.className = 'col-menu';
    m.innerHTML =
      '<div class="cm-sort"><button data-s="az">\u25B2 Sort A\u2192Z</button>'
      + '<button data-s="za">\u25BC Sort Z\u2192A</button></div>'
      + '<div class="cm-sort cm-sort2"><button data-s="+az">+ then A\u2192Z</button>'
      + '<button data-s="+za">+ then Z\u2192A</button></div>'
      + '<div class="cm-seq"></div>'
      + '<input class="cm-search" placeholder="Search values\u2026">'
      + '<div class="cm-list"></div>'
      + '<div class="cm-actions"><button data-a="all">All</button>'
      + '<button data-a="none">None</button>'
      + '<button class="cm-apply" data-a="apply">Apply</button></div>';
    document.body.appendChild(m);
    this.cmenu = m;

    var seqEl = m.querySelector('.cm-seq');
    if (this.sortSeq.length) {
      seqEl.innerHTML = '<div class="cm-seq-in"><b>Sorted by</b> '
        + this.sortSeq.map(function (lv, i) {
            return '<span class="cm-seq-tag">' + (i + 1) + '. '
              + esc(self.cols[lv.c].label) + ' ' + (lv.asc ? '\u25B2' : '\u25BC')
              + '</span>'; }).join(' ')
        + '<button data-a="clearsort">Clear sorting</button></div>';
    }

    // Every distinct value in the column, counted, taken from ALL rows so the
    // list does not shrink as you filter yourself into a corner.
    var counts = {};
    this.rows.forEach(function (r) {
      var v = String(r[col.key] == null ? '' : r[col.key]);
      counts[v] = (counts[v] || 0) + 1;
    });
    var vals = Object.keys(counts).sort(cmpVal);
    var allow = this.filters[col.key];
    m.querySelector('.cm-list').innerHTML = vals.map(function (v) {
      var on = (!allow || allow.has(v)) ? ' checked' : '';
      return '<label class="cm-item"><input type="checkbox" value="' + esc(v) + '"' + on + '>'
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
        self.sortSeq = [{c: ci, asc: sc === 'az'}];
        self.closeColMenu(); self.applyView(); self.draw();
        self.say('sorted by ' + col.label);
      } else if (sc === '+az' || sc === '+za') {
        var at = self.sortLevel(ci);
        if (at >= 0) self.sortSeq[at].asc = (sc === '+az');
        else self.sortSeq.push({c: ci, asc: sc === '+az'});
        self.closeColMenu(); self.applyView(); self.draw();
        self.say('then by ' + col.label);
      } else if (a === 'clearsort') {
        self.sortSeq = [];
        self.closeColMenu(); self.applyView(); self.draw();
        self.say('sorting cleared');
      } else if (a === 'all' || a === 'none') {
        Array.prototype.forEach.call(m.querySelectorAll('.cm-item'), function (li) {
          if (li.style.display !== 'none') li.querySelector('input').checked = (a === 'all');
        });
      } else if (a === 'apply') {
        var boxes = Array.prototype.slice.call(m.querySelectorAll('.cm-item input'));
        var on = boxes.filter(function (x) { return x.checked; })
                      .map(function (x) { return x.value; });
        // Everything ticked is not a filter, it is the absence of one.
        if (on.length === boxes.length) delete self.filters[col.key];
        else self.filters[col.key] = new Set(on);
        self.closeColMenu(); self.applyView(); self.draw();
        var n = self.view.length;
        self.say(self.filtered() ? (n + ' of ' + self.rows.length + ' shown')
                                 : 'filter cleared');
      }
    });

    var r = ev.target.closest('th').getBoundingClientRect();
    m.style.left = Math.max(4, Math.min(r.left + window.scrollX,
                            window.innerWidth - m.offsetWidth - 8)) + 'px';
    var want = Math.min(m.offsetHeight || 320, window.innerHeight * 0.7);
    var below = window.innerHeight - r.bottom;
    m.style.top = ((below < want + 8 && r.top > want + 8)
      ? Math.max(4, r.top + window.scrollY - want - 2)
      : r.bottom + window.scrollY + 2) + 'px';
    var sf = m.querySelector('.cm-search');
    if (sf) sf.focus();
  };

  Grid.prototype.closeColMenu = function () {
    if (this.cmenu && this.cmenu.parentNode) this.cmenu.parentNode.removeChild(this.cmenu);
    this.cmenu = null;
    this.cmKey = null;
  };

  Grid.prototype.filtered = function () {
    for (var k in this.filters) if (this.filters[k]) return true;
    return false;
  };

  Grid.prototype.cell = function (r, c) {
    return this.table.querySelector('td[data-r="' + r + '"][data-c="' + c + '"]');
  };

  Grid.prototype.box = function () {
    return {
      r1: Math.min(this.cur.r, this.anchor.r), r2: Math.max(this.cur.r, this.anchor.r),
      c1: Math.min(this.cur.c, this.anchor.c), c2: Math.max(this.cur.c, this.anchor.c)
    };
  };

  Grid.prototype.paint = function () {
    var b = this.box();
    var cells = this.table.querySelectorAll('tbody td');
    for (var i = 0; i < cells.length; i++) {
      var td = cells[i];
      var r = +td.dataset.r, c = +td.dataset.c;
      var inBox = r >= b.r1 && r <= b.r2 && c >= b.c1 && c <= b.c2;
      td.classList.toggle('sel', inBox && !(r === this.cur.r && c === this.cur.c));
      td.classList.toggle('cur', r === this.cur.r && c === this.cur.c);
    }
    var cur = this.cell(this.cur.r, this.cur.c);
    if (cur && cur.scrollIntoView) cur.scrollIntoView({block: 'nearest', inline: 'nearest'});
  };

  Grid.prototype.refreshRow = function (vr) {
    var self = this;
    var tr = this.table.querySelectorAll('tbody tr')[vr];
    if (!tr) return;
    var row = this.rowAt(vr);
    tr.className = this.rowClass(row);
    this.cols.forEach(function (c, ci) {
      var td = self.cell(vr, ci);
      if (!td) return;
      td.innerHTML = self.render[c.key] ? self.render[c.key](row, row[c.key])
                                        : esc(row[c.key] || '');
    });
    this.paint();
  };

  // ── moving ───────────────────────────────────────────────────────────────
  Grid.prototype.go = function (r, c, keepAnchor) {
    this.commit();
    this.closeMenu();
    r = Math.max(0, Math.min(this.view.length - 1, r));
    c = Math.max(0, Math.min(this.cols.length - 1, c));
    this.cur = {r: r, c: c};
    if (!keepAnchor) this.anchor = {r: r, c: c};
    this.paint();
  };

  // ── setting a value ──────────────────────────────────────────────────────
  Grid.prototype.set = function (vr, c, val) {
    var col = this.cols[c];
    if (this.readOnly || !col || col.ro) return false;
    var row = this.rowAt(vr);
    if (!row) return false;
    if (col.kind === 'time' && val) {
      var t = normTime(val);
      if (t === null) return false;
      val = t;
    }
    if (col.list && val) {
      var hit = null;
      for (var i = 0; i < col.list.length; i++) {
        if (col.list[i].toLowerCase() === String(val).toLowerCase()) { hit = col.list[i]; break; }
      }
      if (hit === null) return false;
      val = hit;
    }
    row[col.key] = val;
    this.onChange(row, col.key, val, vr);
    return true;
  };

  // ── the type-ahead that replaces the drop-down ───────────────────────────
  Grid.prototype.typeAhead = function (ch) {
    var col = this.cols[this.cur.c];
    if (!col || !col.list) return false;
    var now = Date.now();
    if (now - this.typeAt > 900) this.typeBuf = '';
    this.typeAt = now;

    var buf = this.typeBuf + ch;
    var matches = col.list.filter(function (v) {
      return v.toLowerCase().indexOf(buf.toLowerCase()) === 0;
    });
    if (matches.length) {
      this.typeBuf = buf;
    } else {
      this.typeBuf = ch;
      matches = col.list.filter(function (v) {
        return v.toLowerCase().indexOf(ch.toLowerCase()) === 0;
      });
      if (!matches.length) return false;
    }
    var cur = this.rowAt(this.cur.r)[col.key];
    var i = matches.indexOf(cur);
    var next = (this.typeBuf.length === 1 && i >= 0) ? matches[(i + 1) % matches.length]
                                                     : matches[0];
    this.set(this.cur.r, this.cur.c, next);
    this.refreshRow(this.cur.r);
    return true;
  };

  // ── the drop-down, for anyone who does not know the letters ──────────────
  Grid.prototype.openMenu = function () {
    var col = this.cols[this.cur.c];
    if (this.readOnly || !col || !col.list || col.ro) return;
    this.closeMenu();
    var td = this.cell(this.cur.r, this.cur.c);
    if (!td) return;
    var self = this;
    var cur = this.rowAt(this.cur.r)[col.key];
    var box = document.createElement('div');
    box.className = 'gmenu';
    box.innerHTML = col.list.map(function (v) {
      return '<div class="gopt' + (v === cur ? ' on' : '') + '" data-v="' + esc(v) + '">'
        + esc(v) + '</div>';
    }).join('') + '<div class="gopt clear" data-v="">(clear)</div>';
    document.body.appendChild(box);
    var r = td.getBoundingClientRect();
    box.style.left = (r.left + window.scrollX) + 'px';
    box.style.top = (r.bottom + window.scrollY) + 'px';
    box.style.minWidth = r.width + 'px';
    // Flip above the cell when there is no room below it.
    if (r.bottom + box.offsetHeight > window.innerHeight && r.top > box.offsetHeight) {
      box.style.top = (r.top + window.scrollY - box.offsetHeight) + 'px';
    }
    box.addEventListener('mousedown', function (e) {
      var opt = e.target.closest('.gopt');
      if (!opt) return;
      e.preventDefault();
      e.stopPropagation();
      self.set(self.cur.r, self.cur.c, opt.dataset.v);
      self.refreshRow(self.cur.r);
      self.closeMenu();
      self.table.focus();
    });
    this.menu = box;
  };

  Grid.prototype.closeMenu = function () {
    if (this.menu && this.menu.parentNode) this.menu.parentNode.removeChild(this.menu);
    this.menu = null;
  };

  // ── inline editing ───────────────────────────────────────────────────────
  Grid.prototype.edit = function (seed) {
    var col = this.cols[this.cur.c];
    if (this.readOnly || !col || col.ro) return;
    if (col.list) return this.openMenu();
    var td = this.cell(this.cur.r, this.cur.c);
    if (!td) return;
    var val = seed != null ? seed : (this.rowAt(this.cur.r)[col.key] || '');
    var type = col.kind === 'date' ? 'date' : 'text';
    td.innerHTML = '<input class="ed" type="' + type + '" value="' + esc(val) + '"'
      + (col.kind === 'time' ? ' placeholder="HH:MM" maxlength="5"' : '') + '>';
    var inp = td.querySelector('.ed');
    inp.focus();
    if (type === 'text') inp.setSelectionRange(inp.value.length, inp.value.length);
    this.editing = {r: this.cur.r, c: this.cur.c, input: inp};
    var self = this;
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); self.commit(); self.go(self.cur.r + 1, self.cur.c); self.table.focus(); }
      else if (e.key === 'Escape') { e.preventDefault(); self.editing = null; self.refreshRow(self.cur.r); self.table.focus(); }
      else if (e.key === 'Tab') { e.preventDefault(); self.commit(); self.go(self.cur.r, self.cur.c + 1); self.table.focus(); }
      e.stopPropagation();
    });
    inp.addEventListener('blur', function () { self.commit(); });
  };

  Grid.prototype.commit = function () {
    if (!this.editing) return;
    var e = this.editing;
    this.editing = null;
    var col = this.cols[e.c];
    var raw = e.input.value.trim();
    var ok = this.set(e.r, e.c, raw);
    if (!ok && raw && col.kind === 'time') {
      this.say('"' + raw + '" is not a time - use HH:MM, like 06:00 or 14:30');
    }
    this.refreshRow(e.r);
  };

  // ── block operations ─────────────────────────────────────────────────────
  // All of these work on what is on screen. With a filter on, that is the
  // point: "these fifteen are all coming back" should touch fifteen rows.
  Grid.prototype.fillDown = function () {
    var b = this.box(), n = 0, c, r;
    for (c = b.c1; c <= b.c2; c++) {
      var src = this.rowAt(b.r1)[this.cols[c].key];
      for (r = b.r1 + 1; r <= b.r2; r++) if (this.set(r, c, src)) n++;
    }
    if (b.r1 === b.r2) {
      for (c = b.c1; c <= b.c2; c++) {
        var v = this.rowAt(b.r1)[this.cols[c].key];
        for (r = b.r1 + 1; r < this.view.length; r++) if (this.set(r, c, v)) n++;
      }
    }
    this.draw();
    return n;
  };

  Grid.prototype.clear = function () {
    if (this.readOnly) return 0;
    var b = this.box(), n = 0;
    for (var r = b.r1; r <= b.r2; r++)
      for (var c = b.c1; c <= b.c2; c++)
        if (!this.cols[c].ro) { this.rowAt(r)[this.cols[c].key] = ''; n++; }
    this.draw();
    return n;
  };

  Grid.prototype.copyText = function () {
    var b = this.box(), out = [];
    for (var r = b.r1; r <= b.r2; r++) {
      var line = [];
      for (var c = b.c1; c <= b.c2; c++) line.push(this.rowAt(r)[this.cols[c].key] || '');
      out.push(line.join('\t'));
    }
    return out.join('\n');
  };

  Grid.prototype.paste = function (text) {
    var lines = String(text).replace(/\r/g, '').split('\n');
    if (lines.length && lines[lines.length - 1] === '') lines.pop();
    var ok = 0, bad = 0;
    for (var i = 0; i < lines.length; i++) {
      var cells = lines[i].split('\t');
      for (var j = 0; j < cells.length; j++) {
        var r = this.cur.r + i, c = this.cur.c + j;
        if (r >= this.view.length || c >= this.cols.length) continue;
        if (this.cols[c].ro) continue;
        if (this.set(r, c, cells[j].trim())) ok++; else bad++;
      }
    }
    this.draw();
    return {ok: ok, bad: bad};
  };

  // ── input ────────────────────────────────────────────────────────────────
  Grid.prototype.wire = function () {
    var self = this;
    var t = this.table;
    t.setAttribute('tabindex', '0');

    t.addEventListener('mousedown', function (e) {
      var td = e.target.closest && e.target.closest('td');
      if (!td || td.dataset.r === undefined) return;
      self.commit();
      var r = +td.dataset.r, c = +td.dataset.c;
      if (e.shiftKey) { self.cur = {r: r, c: c}; }
      else { self.cur = {r: r, c: c}; self.anchor = {r: r, c: c}; }
      self.paint();
      t.focus();
      // A single click on a list cell opens the list. The letters are faster
      // once you know them, and nobody knows them on the first day.
      if (!e.shiftKey && self.cols[c].list && !self.cols[c].ro) {
        self.openMenu();          // click or double-click, the list opens
      } else {
        self.closeMenu();
        self.dragging = true;
      }
    });
    t.addEventListener('mouseover', function (e) {
      // e.buttons is the truth about whether a button is still held. The flag
      // alone could survive a mouseup that happened outside this document -
      // in an iframe, that is most of them - and then a plain mouse move
      // dragged a selection across the page.
      if (!self.dragging || !(e.buttons & 1)) { self.dragging = false; return; }
      var td = e.target.closest && e.target.closest('td');
      if (!td || td.dataset.r === undefined) return;
      self.cur = {r: +td.dataset.r, c: +td.dataset.c};
      self.paint();
    });
    document.addEventListener('mouseup', function () { self.dragging = false; });
    document.addEventListener('mousedown', function (e) {
      if (self.cmenu && !self.cmenu.contains(e.target)) self.closeColMenu();
      if (!self.menu) return;
      if (self.menu.contains(e.target)) return;
      if (t.contains(e.target)) return;
      self.closeMenu();
    });

    t.addEventListener('dblclick', function (e) {
      var td = e.target.closest && e.target.closest('td');
      if (!td || td.dataset.r === undefined) return;
      self.cur = {r: +td.dataset.r, c: +td.dataset.c};
      self.anchor = {r: self.cur.r, c: self.cur.c};
      self.edit();
    });

    t.addEventListener('keydown', function (e) {
      if (self.editing) return;
      var k = e.key;
      var shift = e.shiftKey, mod = e.ctrlKey || e.metaKey;

      if (self.menu && (k === 'Escape' || k === 'Enter')) {
        e.preventDefault(); self.closeMenu(); return;
      }
      if ((e.altKey && k === 'ArrowDown') || (!mod && !e.altKey && k === 'F4')) {
        e.preventDefault(); self.openMenu(); return;
      }
      if (mod && (k === 'd' || k === 'D')) {
        e.preventDefault();
        var n = self.fillDown();
        self.say(n + ' cell' + (n === 1 ? '' : 's') + ' filled down'
          + (self.filtered() ? ' (visible rows only)' : ''));
        return;
      }
      if (mod && (k === 'c' || k === 'C')) {
        e.preventDefault();
        var txt = self.copyText();
        if (navigator.clipboard) navigator.clipboard.writeText(txt);
        self.say('copied');
        return;
      }
      if (mod && (k === 'a' || k === 'A')) {
        e.preventDefault();
        self.anchor = {r: 0, c: 0};
        self.cur = {r: self.view.length - 1, c: self.cols.length - 1};
        self.paint();
        return;
      }
      switch (k) {
        case 'ArrowUp':    e.preventDefault(); self.go(self.cur.r - 1, self.cur.c, shift); return;
        case 'ArrowDown':  e.preventDefault(); self.go(self.cur.r + 1, self.cur.c, shift); return;
        case 'ArrowLeft':  e.preventDefault(); self.go(self.cur.r, self.cur.c - 1, shift); return;
        case 'ArrowRight': e.preventDefault(); self.go(self.cur.r, self.cur.c + 1, shift); return;
        case 'Tab':        e.preventDefault(); self.go(self.cur.r, self.cur.c + (shift ? -1 : 1)); return;
        case 'Enter':      e.preventDefault();
                           if (self.cols[self.cur.c].list) self.go(self.cur.r + 1, self.cur.c);
                           else self.edit();
                           return;
        case 'F2':         e.preventDefault(); self.edit(); return;
        case 'Home':       e.preventDefault(); self.go(self.cur.r, 0, shift); return;
        case 'End':        e.preventDefault(); self.go(self.cur.r, self.cols.length - 1, shift); return;
        case 'PageUp':     e.preventDefault(); self.go(self.cur.r - 12, self.cur.c, shift); return;
        case 'PageDown':   e.preventDefault(); self.go(self.cur.r + 12, self.cur.c, shift); return;
        case 'Delete':
        case 'Backspace':  e.preventDefault(); self.clear(); self.say('cleared'); return;
        case 'Escape':     self.closeMenu(); self.closeColMenu(); return;
      }
      if (mod || e.altKey) return;
      if (k.length !== 1) return;
      var col = self.cols[self.cur.c];
      if (!col || col.ro) return;
      e.preventDefault();
      if (col.list) { self.closeMenu(); self.typeAhead(k); }
      else { self.edit(k); }
    });

    t.addEventListener('paste', function (e) {
      if (self.editing) return;
      e.preventDefault();
      var txt = (e.clipboardData || global.clipboardData).getData('text');
      var res = self.paste(txt);
      self.say(res.ok + ' cell' + (res.ok === 1 ? '' : 's') + ' pasted'
        + (res.bad ? ', ' + res.bad + ' rejected (not an allowed value)' : ''));
    });
  };

  // Swap the data without rewiring anything.
  Grid.prototype.setRows = function (rows) {
    this.commit();
    this.closeMenu();
    this.closeColMenu();
    this.rows = rows;
    this.applyView();
    if (this.cur.r >= this.view.length) this.cur.r = 0;
    if (this.anchor.r >= this.view.length) this.anchor.r = this.cur.r;
    this.draw();
  };

  Grid.prototype.say = function (msg) { if (this.onSay) this.onSay(msg); };

  Grid.normTime = normTime;
  global.Grid = Grid;
})(window);
