/* A small spreadsheet, for people who already know how to use one.
 *
 * The declaration page had a drop-down in every cell: fifty-eight trucks times
 * three lists is a hundred and seventy-four clicks to say something most days
 * amounts to "same as yesterday". So the grid behaves the way the tool these
 * people actually use behaves - arrows move, typing sets, Ctrl+D fills down,
 * and a block copied out of Excel pastes straight in.
 *
 * Deliberately not a library: it is one table with one active cell and a
 * selection rectangle, and every behaviour here is one a spreadsheet already
 * taught the reader.
 */
(function (global) {
  'use strict';

  function Grid(opts) {
    this.table = opts.table;             // <table> with a <tbody>
    this.cols = opts.cols;               // [{key, label, kind, list, width, ro}]
    this.rows = opts.rows;               // array of row objects
    this.onChange = opts.onChange || function () {};
    this.render = opts.render || {};     // per-column display overrides
    this.rowClass = opts.rowClass || function () { return ''; };
    this.cur = {r: 0, c: this.firstEditable()};
    this.anchor = {r: 0, c: this.cur.c};
    this.typeBuf = '';
    this.typeAt = 0;
    this.editing = null;
    this.wire();
  }

  Grid.prototype.firstEditable = function () {
    for (var i = 0; i < this.cols.length; i++) if (!this.cols[i].ro) return i;
    return 0;
  };

  Grid.prototype.esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  };

  // ── drawing ──────────────────────────────────────────────────────────────
  Grid.prototype.draw = function () {
    var self = this;
    var head = '<tr>' + this.cols.map(function (c) {
      return '<th' + (c.width ? ' style="width:' + c.width + '"' : '') + '>'
        + self.esc(c.label) + '</th>';
    }).join('') + '</tr>';
    var body = this.rows.map(function (row, ri) {
      var tds = self.cols.map(function (c, ci) {
        var val = row[c.key];
        var shown = self.render[c.key] ? self.render[c.key](row, val) : self.esc(val || '');
        return '<td data-r="' + ri + '" data-c="' + ci + '"'
          + (c.ro ? ' class="ro"' : '') + '>' + shown + '</td>';
      }).join('');
      return '<tr class="' + self.rowClass(row) + '">' + tds + '</tr>';
    }).join('');
    this.table.innerHTML = '<thead>' + head + '</thead><tbody>' + body + '</tbody>';
    this.paint();
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
    var cells = this.table.querySelectorAll('td');
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

  Grid.prototype.refreshRow = function (ri) {
    var self = this;
    var tr = this.table.querySelectorAll('tbody tr')[ri];
    if (!tr) return;
    tr.className = this.rowClass(this.rows[ri]);
    this.cols.forEach(function (c, ci) {
      var td = self.cell(ri, ci);
      if (!td) return;
      var val = self.rows[ri][c.key];
      td.innerHTML = self.render[c.key] ? self.render[c.key](self.rows[ri], val)
                                        : self.esc(val || '');
    });
    this.paint();
  };

  // ── moving ───────────────────────────────────────────────────────────────
  Grid.prototype.go = function (r, c, keepAnchor) {
    this.commit();
    r = Math.max(0, Math.min(this.rows.length - 1, r));
    c = Math.max(0, Math.min(this.cols.length - 1, c));
    this.cur = {r: r, c: c};
    if (!keepAnchor) this.anchor = {r: r, c: c};
    this.paint();
  };

  // ── setting a value ──────────────────────────────────────────────────────
  Grid.prototype.set = function (r, c, val) {
    var col = this.cols[c];
    if (!col || col.ro) return false;
    if (col.list && val) {
      var hit = null;
      for (var i = 0; i < col.list.length; i++) {
        if (col.list[i].toLowerCase() === String(val).toLowerCase()) { hit = col.list[i]; break; }
      }
      if (hit === null) return false;         // not one of the allowed values
      val = hit;
    }
    this.rows[r][col.key] = val;
    this.onChange(this.rows[r], col.key, val, r);
    return true;
  };

  // ── the type-ahead that replaces the drop-down ───────────────────────────
  // A letter picks the first value starting with it; the same letter again
  // steps to the next one. Exactly what a list box in Excel does.
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
      // Nothing matches the buffer, so treat this keystroke as a fresh start -
      // which is what makes pressing "b" twice step BH -> Breakdown.
      this.typeBuf = ch;
      matches = col.list.filter(function (v) {
        return v.toLowerCase().indexOf(ch.toLowerCase()) === 0;
      });
      if (!matches.length) return false;
    }
    var cur = this.rows[this.cur.r][col.key];
    var i = matches.indexOf(cur);
    var next = (this.typeBuf.length === 1 && i >= 0) ? matches[(i + 1) % matches.length]
                                                     : matches[0];
    this.set(this.cur.r, this.cur.c, next);
    this.refreshRow(this.cur.r);
    return true;
  };

  // ── inline editing, for the free-text and date columns ───────────────────
  Grid.prototype.edit = function (seed) {
    var col = this.cols[this.cur.c];
    if (!col || col.ro) return;
    var td = this.cell(this.cur.r, this.cur.c);
    if (!td) return;
    var val = seed != null ? seed : (this.rows[this.cur.r][col.key] || '');
    var type = col.kind === 'date' ? 'date' : 'text';
    td.innerHTML = '<input class="ed" type="' + type + '" value="' + this.esc(val) + '">';
    var inp = td.querySelector('.ed');
    inp.focus();
    if (type === 'text') inp.setSelectionRange(inp.value.length, inp.value.length);
    this.editing = {r: this.cur.r, c: this.cur.c, input: inp};
    var self = this;
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); self.commit(); self.go(self.cur.r + 1, self.cur.c); }
      else if (e.key === 'Escape') { e.preventDefault(); self.editing = null; self.refreshRow(self.cur.r); }
      else if (e.key === 'Tab') { e.preventDefault(); self.commit(); self.go(self.cur.r, self.cur.c + 1); }
      e.stopPropagation();
    });
    inp.addEventListener('blur', function () { self.commit(); });
  };

  Grid.prototype.commit = function () {
    if (!this.editing) return;
    var e = this.editing;
    this.editing = null;
    this.set(e.r, e.c, e.input.value.trim());
    this.refreshRow(e.r);
  };

  // ── block operations ─────────────────────────────────────────────────────
  Grid.prototype.fillDown = function () {
    var b = this.box();
    var n = 0;
    for (var c = b.c1; c <= b.c2; c++) {
      var src = this.rows[b.r1][this.cols[c].key];
      for (var r = b.r1 + 1; r <= b.r2; r++) if (this.set(r, c, src)) n++;
    }
    // One row selected means "fill this value to the bottom", which is the
    // thing people actually want after typing the first row.
    if (b.r1 === b.r2) {
      for (var c2 = b.c1; c2 <= b.c2; c2++) {
        var v = this.rows[b.r1][this.cols[c2].key];
        for (var r2 = b.r1 + 1; r2 < this.rows.length; r2++) if (this.set(r2, c2, v)) n++;
      }
    }
    this.draw();
    return n;
  };

  Grid.prototype.clear = function () {
    var b = this.box(), n = 0;
    for (var r = b.r1; r <= b.r2; r++)
      for (var c = b.c1; c <= b.c2; c++)
        if (!this.cols[c].ro) { this.rows[r][this.cols[c].key] = ''; n++; }
    this.draw();
    return n;
  };

  Grid.prototype.copyText = function () {
    var b = this.box(), out = [];
    for (var r = b.r1; r <= b.r2; r++) {
      var line = [];
      for (var c = b.c1; c <= b.c2; c++) line.push(this.rows[r][this.cols[c].key] || '');
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
        if (r >= this.rows.length || c >= this.cols.length) continue;
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
      self.dragging = true;
    });
    t.addEventListener('mouseover', function (e) {
      if (!self.dragging) return;
      var td = e.target.closest && e.target.closest('td');
      if (!td || td.dataset.r === undefined) return;
      self.cur = {r: +td.dataset.r, c: +td.dataset.c};
      self.paint();
    });
    document.addEventListener('mouseup', function () { self.dragging = false; });

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

      if (mod && (k === 'd' || k === 'D')) {
        e.preventDefault();
        var n = self.fillDown();
        self.say(n + ' cell' + (n === 1 ? '' : 's') + ' filled down');
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
        self.cur = {r: self.rows.length - 1, c: self.cols.length - 1};
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
        case 'Escape':     return;
      }
      if (mod || e.altKey) return;
      if (k.length !== 1) return;
      var col = self.cols[self.cur.c];
      if (!col || col.ro) return;
      e.preventDefault();
      if (col.list) { self.typeAhead(k); }
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

  Grid.prototype.say = function (msg) {
    if (this.onSay) this.onSay(msg);
  };

  global.Grid = Grid;
})(window);
