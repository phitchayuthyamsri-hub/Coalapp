/* The row-number column, defined once for every table that lists trucks.
 *
 * Fifty-odd plates and no way to say where you are in them. The number counts
 * the rows AS SHOWN, so a sort or a filter starts again at 1 and "I am on 17"
 * means the same thing to whoever is told it.
 *
 * It is a place, not an id. It is never saved, never sent back, and never the
 * thing a row is addressed by - the tables keep their own row indexes for that,
 * which is what stops an edit landing on a different truck after a sort.
 *
 * Tried on the sandbox first, live everywhere since 18/09/2026.
 */
(function (g) {
  'use strict';

  /* The header cell. No data-col / data-c attribute on purpose: the column
   * menus are wired by those attributes, and a number has nothing to sort or
   * filter by. */
  g.noHead = function () {
    return '<th class="c-no" title="Row number, as shown">No#</th>';
  };

  /* The row's cell. Takes the position in the VIEW, zero-based. */
  g.rowNo = function (n) {
    return '<td class="c-no">' + (n + 1) + '</td>';
  };

  /* For a header that spans two rows, so the number sits beside the other
   * identifying columns rather than above a sub-heading of its own. */
  g.noHead2 = function () {
    return '<th class="c-no" rowspan="2" title="Row number, as shown">No#</th>';
  };
})(typeof window !== 'undefined' ? window : this);
