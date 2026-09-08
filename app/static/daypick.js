/* The day picker, shared by the three pages that pick a day.
 *
 * It replaces a free date field with the days that exist. A calendar invites
 * the one mistake nobody catches: typing a day nothing was filed under and
 * reading the empty page as "they sent nothing" - which is exactly what
 * happened when the declaration page and the board disagreed by one day.
 *
 * The element keeps the id `day` and its .value stays a YYYY-MM-DD string, so
 * every page that already reads $('#day').value goes on working.
 */
(function (global) {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }

  // 09-09-26, the way the sheets are written.
  function dmy(iso) {
    var p = String(iso || '').split('-');
    if (p.length !== 3) return iso || '';
    return p[2] + '-' + p[1] + '-' + p[0].slice(2);
  }

  function weekday(iso) {
    try {
      return new Date(iso + 'T00:00').toLocaleDateString('en-GB', {weekday: 'short'});
    } catch (e) { return ''; }
  }

  /* opts.detail: false for the company - their own days need no commentary.
   *              true for a supervisor or a manager, who are choosing between
   *              days that several companies have contributed to and need to
   *              be told which one is live. */
  function DayPick(opts) {
    this.sel = opts.select;
    this.detail = !!opts.detail;
    this.source = opts.source || 'sheet';
    this.onPick = opts.onPick || function () {};
    this.rows = [];
    this.today = null;
    this.latest = null;
    var self = this;
    this.sel.addEventListener('change', function () { self.onPick(self.sel.value); });
  }

  DayPick.prototype.label = function (r) {
    var head = dmy(r.date) + '  ' + weekday(r.date);
    if (!this.detail) {
      // The company: say what state their own sheet is in, nothing else.
      if (!r.lists) return head + (r.today ? '  ·  new sheet' : '');
      var st = r.states.join('/');
      return head + '  ·  ' + r.trucks + ' trucks  ·  ' + st;
    }
    if (this.source === 'run'){
      var run = [];
      if (r.latest) run.push('NOW');
      if (r.today && !r.latest) run.push('today');
      run.push(r.trucks ? (r.trucks + ' due at the mine') : 'nothing due');
      if (r.trucks) run.push(r.issued ? 'plan issued' : 'not issued yet');
      return head + '  ·  ' + run.join('  ·  ');
    }
    var bits = [];
    if (r.latest) bits.push('LATEST');
    if (r.today && !r.latest) bits.push('today');
    if (!r.lists) bits.push(r.today ? 'nothing sent yet' : 'empty');
    else {
      bits.push(r.companies.length + (r.companies.length === 1 ? ' company' : ' companies'));
      bits.push(r.trucks + ' trucks');
      if (r.waiting) bits.push(r.waiting + ' waiting');
      if (r.amend) bits.push(r.amend + ' amend request');
      bits.push(r.states.join('/'));
    }
    return head + '  ·  ' + bits.join('  ·  ');
  };

  DayPick.prototype.render = function (want) {
    var self = this;
    this.sel.innerHTML = this.rows.map(function (r) {
      return '<option value="' + esc(r.date) + '">' + esc(self.label(r)) + '</option>';
    }).join('');
    // Prefer what was asked for, then the day with something on it, then today.
    var pick = null;
    if (want && this.rows.some(function (r) { return r.date === want; })) pick = want;
    if (!pick) pick = this.latest || this.today;
    if (pick) this.sel.value = pick;
    return this.sel.value;
  };

  /* Two kinds of day, and they are not interchangeable.
   *   'sheet' - the day a sheet was SENT. What the declaration, the supervisor
   *             and the manager work on, because they work on sheets.
   *   'run'   - the day trucks reach the mine. What the planner and the monitor
   *             watch, because that is when anything happens.
   * Feeding one a list of the other is the fault this whole picker exists to
   * stop, so the source is named rather than assumed. */
  DayPick.prototype.load = function (want) {
    var self = this;
    if (this.source === 'run') return this.loadRun(want);
    return fetch('/api/shift/dates').then(function (r) { return r.json(); })
      .then(function (j) {
        self.rows = j.dates || [];
        self.today = j.today;
        self.latest = j.latest;
        return self.render(want);
      }).catch(function () {
        // Never leave the page without a day: a picker with nothing in it is
        // worse than a calendar.
        var t = new Date(Date.now() + 7 * 3600 * 1000).toISOString().slice(0, 10);
        self.rows = [{date: t, lists: 0, trucks: 0, companies: [], states: [],
                      waiting: 0, amend: 0, today: true, latest: false}];
        self.today = t;
        return self.render(t);
      });
  };

  DayPick.prototype.loadRun = function (want) {
    var self = this;
    return fetch('/api/shift/plan-day').then(function (r) { return r.json(); })
      .then(function (j) {
        var days = j.days || [];
        self.today = j.today;
        // The day being worked: the one the planner's own answer points at.
        self.latest = j.date || null;
        self.rows = days.map(function (d) {
          return {date: d.date, lists: d.trucks ? 1 : 0, trucks: d.trucks,
                  companies: [], states: d.issued ? ['issued'] : ['not issued yet'],
                  waiting: 0, amend: 0, today: d.date === j.today,
                  latest: d.date === j.date, issued: !!d.issued};
        });
        if (!self.rows.some(function (r2) { return r2.date === j.today; })) {
          self.rows.push({date: j.today, lists: 0, trucks: 0, companies: [],
                          states: [], waiting: 0, amend: 0, today: true,
                          latest: false, issued: false});
          self.rows.sort(function (x, y) { return x.date < y.date ? 1 : -1; });
        }
        return self.render(want);
      }).catch(function () {
        var t = new Date(Date.now() + 7 * 3600 * 1000).toISOString().slice(0, 10);
        self.rows = [{date: t, lists: 0, trucks: 0, companies: [], states: [],
                      waiting: 0, amend: 0, today: true, latest: false}];
        self.today = t;
        return self.render(t);
      });
  };

  global.DayPick = DayPick;
  global.DayPick.dmy = dmy;
})(window);
