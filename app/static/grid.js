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

  function Grid(opts) {
    this.table = opts.table;
    this.cols = opts.cols;
    this.rows = opts.rows;
    this.onChange = opts.onChange || function () {};
    this.render = opts.render || {};
    this.rowClass = opts.rowClass || function () { return ''; };
    this.sort = null;                     // {c, dir}
    this.filters = {};                    // colKey -> string
    this.view = [];
    this.cur = {r: 0, c: this.firstEditable()};
    this.anchor = {r: 0, c: this.cur.c};
    this.typeBuf = '';
    this.typeAt = 0;
    this.editing = null;
    this.menu = null;
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
        var want = (self.filters[k] || '').trim().toLowerCase();
        if (!want) continue;
        var got = String(self.rows[i][k] == null ? '' : self.rows[i][k]).toLowerCase();
        // A list filter is an exact value; a text filter is "contains", which
        // is what people expect from a box they type into.
        var col = self.colByKey(k);
        // The blank option asks for rows nobody has answered yet, which is the
        // filter the supervisor actually wants before chasing a company.
        if (want === '∅') { if (got !== '') return false; }
        else if (col && col.list) { if (got !== want) return false; }
        else if (got.indexOf(want) < 0) return false;
      }
      return true;
    });

    if (this.sort) {
      var key = this.cols[this.sort.c].key, dir = this.sort.dir;
      idx.sort(function (a, b) {
        var x = String(self.rows[a][key] == null ? '' : self.rows[a][key]);
        var y = String(self.rows[b][key] == null ? '' : self.rows[b][key]);
        // Blanks sort last whichever way the column is pointing: an empty cell
        // is not a small value, it is a missing one.
        if (!x && !y) return a - b;
        if (!x) return 1;
        if (!y) return -1;
        var n = x.localeCompare(y, undefined, {numeric: true, sensitivity: 'base'});
        return dir === 'desc' ? -n : n;
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
      var arrow = (self.sort && self.sort.c === ci)
        ? (self.sort.dir === 'desc' ? ' ▼' : ' ▲') : '';
      return '<th data-c="' + ci + '"' + (c.width ? ' style="width:' + c.width + '"' : '')
        + ' class="hd' + (c.sortable === false ? '' : ' sortable') + '">'
        + '<span class="hl">' + esc(c.label) + arrow + '</span>'
        + (c.hint ? '<span class="hh">' + esc(c.hint) + '</span>' : '')
        + '</th>';
    }).join('') + '</tr>';

    var filt = '<tr class="filt">' + this.cols.map(function (c, ci) {
      if (c.filter === false) return '<td></td>';
      var v = self.filters[c.key] || '';
      if (c.list) {
        return '<td><select data-fc="' + ci + '"><option value="">(all)</option>'
          + c.list.map(function (o) {
              return '<option value="' + esc(o) + '"' + (v === o ? ' selected' : '') + '>'
                + esc(o) + '</option>'; }).join('')
          + '<option value="∅"' + (v === '∅' ? ' selected' : '') + '>(blank)</option>'
          + '</select></td>';
      }
      return '<td><input data-fc="' + ci + '" placeholder="filter" value="' + esc(v) + '"></td>';
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

    this.table.innerHTML = '<thead>' + head + filt + '</thead><tbody>' + body + '</tbody>';
    this.paint();
    this.wireHead();
  };

  Grid.prototype.wireHead = function () {
    var self = this;
    Array.prototype.forEach.call(this.table.querySelectorAll('th.sortable'), function (th) {
      th.onclick = function () {
        var c = +th.dataset.c;
        // asc, then desc, then back to the order the rows arrived in.
        if (!self.sort || self.sort.c !== c) self.sort = {c: c, dir: 'asc'};
        else if (self.sort.dir === 'asc') self.sort = {c: c, dir: 'desc'};
        else self.sort = null;
        self.applyView();
        self.draw();
        self.say(self.sort ? ('sorted by ' + self.cols[c].label + ' ' + self.sort.dir)
                           : 'sort cleared');
      };
    });
    Array.prototype.forEach.call(this.table.querySelectorAll('[data-fc]'), function (el) {
      var apply = function () {
        var c = +el.dataset.fc;
        self.filters[self.cols[c].key] = el.value;
        self.applyView();
        self.draw();
        var n = self.view.length;
        self.say(self.filtered()
          ? (n + ' of ' + self.rows.length + ' row' + (n === 1 ? '' : 's') + ' shown')
          : 'filter cleared');
        var again = self.table.querySelector('[data-fc="' + c + '"]');
        if (again && again.focus) { again.focus(); if (again.setSelectionRange && again.value)
          again.setSelectionRange(again.value.length, again.value.length); }
      };
      el.onchange = apply;
      if (el.tagName === 'INPUT') {
        var t = null;
        el.oninput = function () { clearTimeout(t); t = setTimeout(apply, 250); };
      }
      el.onkeydown = function (e) { e.stopPropagation(); };
    });
  };

  Grid.prototype.filtered = function () {
    for (var k in this.filters) if ((this.filters[k] || '').trim()) return true;
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
    if (!col || col.ro) return false;
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
    if (!col || !col.list || col.ro) return;
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
    if (!col || col.ro) return;
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
        case 'Escape':     self.closeMenu(); return;
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
