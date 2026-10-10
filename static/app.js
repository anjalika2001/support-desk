/* Support Desk - small, dependency-free UI enhancements.
   Every page still works without this file. */
(function () {
  "use strict";
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  // ---------- Toasts: close button and auto-dismiss ----------
  $$(".toasts .flash").forEach(function (t) {
    var close = document.createElement("button"), timer = document.createElement("span");
    close.type = "button"; close.className = "close"; close.setAttribute("aria-label", "Dismiss"); close.innerHTML = "&times;";
    timer.className = "timer";
    if (t.classList.contains("error")) timer.style.animationDuration = "8s";
    t.appendChild(close); t.appendChild(timer);
    var dismiss = function () { t.classList.add("out"); setTimeout(function () { t.remove(); }, 350); };
    close.addEventListener("click", dismiss);
    timer.addEventListener("animationend", dismiss); // pauses on hover via CSS
  });

  // ---------- Textareas grow with their content ----------
  $$("textarea[data-autogrow]").forEach(function (ta) {
    ta.addEventListener("input", function () { ta.style.height = "auto"; ta.style.height = ta.scrollHeight + 2 + "px"; });
  });

  // ---------- Collapsible "new ticket" form (remembers its state) ----------
  var toggle = $("#toggle-form"), body = $("#new-ticket-body");
  if (toggle && body) {
    var setOpen = function (open) {
      body.classList.toggle("closed", !open);
      toggle.setAttribute("aria-expanded", open);
      toggle.classList.toggle("collapsed", !open);
      $(".toggle-text", toggle).textContent = open ? "Hide" : "Show";
      try { localStorage.setItem("sd-form-open", open ? "1" : "0"); } catch (e) {}
    };
    try { if (localStorage.getItem("sd-form-open") === "0") setOpen(false); } catch (e) {}
    toggle.addEventListener("click", function () { setOpen(body.classList.contains("closed")); });
  }

  // ---------- Active queue: search, priority chips, status tiles, sorting ----------
  var table = $("#queue");
  if (table) {
    var tbody = $("tbody", table), rows = $$("tr", tbody), search = $("#queue-search");
    var state = { q: "", prio: "", status: "" };
    var rank = { High: 1, Medium: 2, Low: 3, Open: 1, "In progress": 2, Escalated: 3 };

    var apply = function () {
      var q = state.q.toLowerCase(), shown = 0;
      rows.forEach(function (r) {
        var ok = (!q || r.textContent.toLowerCase().indexOf(q) !== -1) &&
                 (!state.prio || r.getAttribute("data-prio") === state.prio) &&
                 (!state.status || r.getAttribute("data-status") === state.status);
        r.classList.toggle("hide", !ok);
        if (ok) shown++;
      });
      $("#result-count").textContent = shown === rows.length ? rows.length + " ticket" + (rows.length === 1 ? "" : "s")
                                                             : shown + " of " + rows.length + " shown";
      $("#no-match").hidden = shown !== 0;
      table.style.display = shown ? "" : "none";
      $$(".stat[data-status]").forEach(function (s) { s.classList.toggle("selected", s.getAttribute("data-status") === state.status); });
      $$(".chip[data-prio]").forEach(function (c) { c.classList.toggle("on", c.getAttribute("data-prio") === state.prio); });
    };

    rows.forEach(function (r) {
      r.addEventListener("click", function (e) { if (!e.target.closest("a")) window.location = r.getAttribute("data-href"); });
    });
    search.addEventListener("input", function () { state.q = search.value.trim(); apply(); });
    $$(".chip[data-prio]").forEach(function (c) {
      c.addEventListener("click", function () { state.prio = c.getAttribute("data-prio"); apply(); });
    });
    $("#clear-filters").addEventListener("click", function (e) {
      e.preventDefault();
      state = { q: "", prio: "", status: "" };
      search.value = "";
      apply();
    });
    // Clicking a status tile filters the queue (click again to clear); Resolved links to the knowledge base
    $$(".stat[data-status]").forEach(function (s) {
      s.addEventListener("click", function () {
        var st = s.getAttribute("data-status");
        if (st === "Resolved") { window.location = s.getAttribute("data-href"); return; }
        state.status = state.status === st ? "" : st;
        apply();
      });
    });

    $$("th.sortable", table).forEach(function (th) {
      th.setAttribute("tabindex", "0");
      var sort = function () {
        var key = th.getAttribute("data-key"), dir = th.getAttribute("aria-sort") === "ascending" ? -1 : 1;
        $$("th.sortable", table).forEach(function (x) { x.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
        var val = function (r) {
          var v = r.getAttribute("data-" + key);
          return key === "id" ? +v : key === "prio" || key === "status" ? rank[v] || 9 : v.toLowerCase();
        };
        rows.sort(function (a, b) { var x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * dir; });
        rows.forEach(function (r) { tbody.appendChild(r); });
      };
      th.addEventListener("click", sort);
      th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
    });

    apply();
  }

  // ---------- Ticket page: action tabs ----------
  var tabs = $(".tabs");
  if (tabs) {
    var ink = $(".ink", tabs), buttons = $$("button[data-tab]", tabs);
    var moveInk = function (b) {
      ink.style.left = b.offsetLeft + "px";
      ink.style.width = b.offsetWidth + "px";
      ink.style.setProperty("--tab-c", b.style.getPropertyValue("--tab-c"));
    };
    var select = function (b) {
      buttons.forEach(function (x) { x.classList.toggle("on", x === b); x.setAttribute("aria-selected", x === b); });
      $$(".actions form").forEach(function (f) { f.classList.toggle("on", f.getAttribute("data-panel") === b.getAttribute("data-tab")); });
      moveInk(b);
    };
    buttons.forEach(function (b) {
      b.setAttribute("role", "tab");
      b.addEventListener("click", function () { select(b); $(".actions form.on textarea").focus(); });
    });
    select(buttons[0]);
    window.addEventListener("resize", function () { moveInk($("button.on", tabs)); });
  }
})();
