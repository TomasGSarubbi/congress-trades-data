/* Progressive enhancement only: the tables are complete without this file. */
(function () {
  var table = document.querySelector('[data-filterable]');
  if (!table || !table.tBodies.length) return;
  var rows = Array.prototype.slice.call(table.tBodies[0].rows);
  var q = document.getElementById('q');
  var chamber = document.getElementById('f-chamber');
  var dirn = document.getElementById('f-direction');
  var count = document.getElementById('result-count');

  function apply() {
    var term = ((q && q.value) || '').toLowerCase().trim();
    var c = (chamber && chamber.value) || '';
    var d = (dirn && dirn.value) || '';
    var shown = 0;
    rows.forEach(function (r) {
      var ok = (!c || r.dataset.chamber === c) &&
               (!d || r.dataset.direction === d) &&
               (!term || (r.dataset.search || '').indexOf(term) !== -1);
      r.hidden = !ok;
      if (ok) shown++;
    });
    if (count) {
      count.textContent = shown === rows.length
        ? rows.length + ' trades'
        : shown + ' of ' + rows.length + ' trades';
    }
  }

  [q, chamber, dirn].forEach(function (el) {
    if (el) el.addEventListener('input', apply);
  });

  Array.prototype.forEach.call(table.querySelectorAll('th[data-sort]'), function (th) {
    th.addEventListener('click', function () {
      var key = th.dataset.sort;
      var asc = th.dataset.dir !== 'asc';
      Array.prototype.forEach.call(table.querySelectorAll('th[data-sort]'), function (o) {
        if (o !== th) o.removeAttribute('data-dir');
      });
      th.dataset.dir = asc ? 'asc' : 'desc';
      rows.sort(function (a, b) {
        var x = a.dataset[key], y = b.dataset[key];
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
