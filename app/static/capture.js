/* A table as a picture (22/09/2026).
 *
 * The subcontractor's declaration is sent on in Zalo and WhatsApp as often as
 * it is read on the page, and a photo of a screen is what people were sending.
 * This draws the table itself onto a canvas - white paper, black ink, the
 * company and the day in the title, who captured it and when at the foot - and
 * hands the PNG over as a download, and to the clipboard where the browser
 * allows it, so it can be pasted straight into a chat.
 *
 *   TableCapture.png({title, subtitle, cols: [{label, align?}], rows: [[..]],
 *                     footer, filename})
 *
 * Nothing here depends on the page's own styling: what is captured is the
 * data, laid out the same way whichever page asked.
 */
(function (global) {
  'use strict';

  var FONT = '13px -apple-system, "Segoe UI", Roboto, Arial, sans-serif';
  var BOLD = 'bold 13px -apple-system, "Segoe UI", Roboto, Arial, sans-serif';
  var TITLE = 'bold 18px -apple-system, "Segoe UI", Roboto, Arial, sans-serif';
  var SMALL = '11px -apple-system, "Segoe UI", Roboto, Arial, sans-serif';
  var PAD = 10, ROW = 26, HEAD = 30, MARGIN = 24, MAXCOL = 320;

  function text(v) { return v == null ? '' : String(v); }

  /* Column widths from the content, measured with the real font - never
     guessed - and capped so one long remark cannot make a picture a metre
     wide. Pure, so it can be tested without a canvas: `measure` is any
     function from a string to a width. */
  function layout(cols, rows, measure) {
    var widths = cols.map(function (c) { return measure(text(c.label), true) + PAD * 2; });
    rows.forEach(function (r) {
      cols.forEach(function (c, j) {
        var w = measure(text(r[j]), false) + PAD * 2;
        if (w > widths[j]) widths[j] = w;
      });
    });
    widths = widths.map(function (w) { return Math.min(Math.ceil(w), MAXCOL); });
    var total = widths.reduce(function (a, b) { return a + b; }, 0);
    return { widths: widths, width: total + MARGIN * 2,
             height: MARGIN + 28 + 18 + 8 + HEAD + rows.length * ROW + 8 + 16 + MARGIN };
  }

  /* Cut a value to fit its column, with an ellipsis, so a capped column
     still reads as "cut", not as a different, shorter value. */
  function fit(ctx, s, w) {
    s = text(s);
    if (ctx.measureText(s).width <= w) return s;
    while (s.length > 1 && ctx.measureText(s + '…').width > w) s = s.slice(0, -1);
    return s + '…';
  }

  function draw(opts) {
    var cols = opts.cols || [], rows = opts.rows || [];
    var probe = document.createElement('canvas').getContext('2d');
    var lay = layout(cols, rows, function (s, bold) {
      probe.font = bold ? BOLD : FONT;
      return probe.measureText(s).width;
    });
    var scale = Math.min(3, Math.max(2, global.devicePixelRatio || 1));
    var cv = document.createElement('canvas');
    cv.width = lay.width * scale;
    cv.height = lay.height * scale;
    var ctx = cv.getContext('2d');
    ctx.scale(scale, scale);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, lay.width, lay.height);
    ctx.textBaseline = 'middle';

    var y = MARGIN;
    ctx.fillStyle = '#111827';
    ctx.font = TITLE;
    ctx.fillText(text(opts.title), MARGIN, y + 12);
    y += 28;
    ctx.font = SMALL;
    ctx.fillStyle = '#4b5563';
    ctx.fillText(text(opts.subtitle), MARGIN, y + 6);
    y += 18 + 8;

    // header band
    ctx.fillStyle = '#f3f4f6';
    ctx.fillRect(MARGIN, y, lay.width - MARGIN * 2, HEAD);
    ctx.font = BOLD;
    ctx.fillStyle = '#111827';
    var x = MARGIN;
    cols.forEach(function (c, j) {
      ctx.textAlign = c.align === 'right' ? 'right' : 'left';
      ctx.fillText(fit(ctx, c.label, lay.widths[j] - PAD * 2),
                   c.align === 'right' ? x + lay.widths[j] - PAD : x + PAD, y + HEAD / 2);
      x += lay.widths[j];
    });
    y += HEAD;

    ctx.font = FONT;
    rows.forEach(function (r, i) {
      if (i % 2 === 1) {
        ctx.fillStyle = '#fafafa';
        ctx.fillRect(MARGIN, y, lay.width - MARGIN * 2, ROW);
      }
      ctx.strokeStyle = '#e5e7eb';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(MARGIN, y + ROW - 0.5); ctx.lineTo(lay.width - MARGIN, y + ROW - 0.5); ctx.stroke();
      x = MARGIN;
      cols.forEach(function (c, j) {
        var v = text(r[j]);
        ctx.fillStyle = v ? '#111827' : '#9ca3af';
        ctx.textAlign = c.align === 'right' ? 'right' : 'left';
        ctx.fillText(v ? fit(ctx, v, lay.widths[j] - PAD * 2) : '—',
                     c.align === 'right' ? x + lay.widths[j] - PAD : x + PAD, y + ROW / 2);
        x += lay.widths[j];
      });
      y += ROW;
    });

    // frame
    ctx.strokeStyle = '#d1d5db';
    ctx.strokeRect(MARGIN + 0.5, MARGIN + 28 + 18 + 8 + 0.5,
                   lay.width - MARGIN * 2 - 1, HEAD + rows.length * ROW - 1);

    y += 8;
    ctx.font = SMALL;
    ctx.fillStyle = '#6b7280';
    ctx.textAlign = 'left';
    ctx.fillText(text(opts.footer), MARGIN, y + 8);
    return cv;
  }

  function stamp() {
    var d = new Date(), p = function (n) { return (n < 10 ? '0' : '') + n; };
    return p(d.getDate()) + '/' + p(d.getMonth() + 1) + '/' + d.getFullYear()
      + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function safeName(s) {
    return text(s).replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^_+|_+$/g, '') || 'table';
  }

  /* Draw, download, and offer to the clipboard. Resolves to {downloaded,
     copied} so the page can say which happened - the clipboard is refused
     by some browsers and on plain http, and silence there would read as
     "nothing happened". */
  function png(opts) {
    var cv = draw(opts);
    var name = safeName(opts.filename || opts.title) + '.png';
    return new Promise(function (resolve) {
      cv.toBlob(function (blob) {
        var out = { downloaded: false, copied: false, name: name };
        try {
          var a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = name;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
          out.downloaded = true;
        } catch (e) { /* the download is the fallback; nothing to fall back to */ }
        var clip = global.navigator && global.navigator.clipboard;
        if (clip && clip.write && global.ClipboardItem) {
          clip.write([new global.ClipboardItem({ 'image/png': blob })])
            .then(function () { out.copied = true; resolve(out); },
                  function () { resolve(out); });
        } else {
          resolve(out);
        }
      }, 'image/png');
    });
  }

  global.TableCapture = { png: png, draw: draw, layout: layout, stamp: stamp,
                          safeName: safeName };
})(typeof window !== 'undefined' ? window : this);
