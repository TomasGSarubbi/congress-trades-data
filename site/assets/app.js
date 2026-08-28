/* Progressive enhancement only: every table is complete without this file.
   Any table marked [data-filterable] is filtered by the controls carrying
   [data-filter] (matched against the row's matching data- attribute) plus a
   free-text box (#q, matched against data-search), and sorted by any
   th[data-sort]. */
(function () {
  var table = document.querySelector('[data-filterable]');
  if (!table || !table.tBodies.length) return;

  var rows = Array.prototype.slice.call(table.tBodies[0].rows);
  var controls = Array.prototype.slice.call(document.querySelectorAll('[data-filter]'));
  var search = document.getElementById('q');
  var count = document.getElementById('result-count');
  var noun = table.getAttribute('data-filterable') || 'rows';

  function matches(row) {
    for (var i = 0; i < controls.length; i++) {
      var c = controls[i];
      var want = c.type === 'checkbox' ? (c.checked ? '1' : '') : c.value;
      if (!want) continue;
      if ((row.getAttribute('data-' + c.getAttribute('data-filter')) || '') !== want) {
        return false;
      }
    }
    var term = ((search && search.value) || '').toLowerCase().trim();
    if (term && (row.getAttribute('data-search') || '').indexOf(term) === -1) {
      return false;
    }
    return true;
  }

  function apply() {
    var shown = 0;
    rows.forEach(function (r) {
      var ok = matches(r);
      r.hidden = !ok;
      if (ok) shown++;
    });
    if (count) {
      count.textContent = shown === rows.length
        ? rows.length + ' ' + noun
        : shown + ' of ' + rows.length + ' ' + noun;
    }
  }

  controls.concat([search]).forEach(function (el) {
    if (el) el.addEventListener(el.type === 'checkbox' ? 'change' : 'input', apply);
  });

  Array.prototype.forEach.call(table.querySelectorAll('th[data-sort]'), function (th) {
    th.addEventListener('click', function () {
      var key = th.getAttribute('data-sort');
      var asc = th.getAttribute('data-dir') !== 'asc';
      Array.prototype.forEach.call(table.querySelectorAll('th[data-sort]'), function (o) {
        if (o !== th) o.removeAttribute('data-dir');
      });
      th.setAttribute('data-dir', asc ? 'asc' : 'desc');
      rows.sort(function (a, b) {
        var x = a.getAttribute('data-' + key), y = b.getAttribute('data-' + key);
        var nx = parseFloat(x), ny = parseFloat(y);
        if (!isNaN(nx) && !isNaN(ny)) return asc ? nx - ny : ny - nx;
        return asc ? String(x).localeCompare(y) : String(y).localeCompare(x);
      });
      var body = table.tBodies[0];
      rows.forEach(function (r) { body.appendChild(r); });
    });
  });

  apply();
})();
