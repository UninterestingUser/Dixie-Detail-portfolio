// Register the service worker, which makes the control app installable.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
}

// A rule's condition rows show the inputs their fact takes: a list of
// values, or the two ends of a range (the catalog's rule screen).
function showConditionInputs(select) {
  const row = select.closest(".condition");
  const option = select.options[select.selectedIndex];
  if (row) row.dataset.kind = option ? option.dataset.kind || "" : "";
}
document.addEventListener("change", (event) => {
  if (event.target.matches(".condition-fact")) showConditionInputs(event.target);
});
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".condition-fact").forEach(showConditionInputs);
});

// The review queue's "pick every model year on this page".
document.addEventListener("change", (event) => {
  if (!event.target.matches(".pick-all")) return;
  event.target.form.querySelectorAll('input[name="selected"]').forEach((box) => { box.checked = event.target.checked; });
});

// Popups: a button with data-opens="id" opens that dialog; data-closes
// closes the one it is in, changing nothing (the Cancel job popup).
document.addEventListener("click", (event) => {
  const opener = event.target.closest("[data-opens]");
  if (opener) {
    const dialog = document.getElementById(opener.dataset.opens);
    if (dialog && dialog.showModal) {
      event.preventDefault();
      dialog.showModal();
    }
    return;
  }
  const closer = event.target.closest("[data-closes]");
  if (closer) {
    event.preventDefault();
    closer.closest("dialog").close();
  }
});

// The home screen's Cancel link for a job Time Off covers opens the job's Cancel popup.
document.addEventListener("DOMContentLoaded", () => {
  if (window.location.hash !== "#cancel") return;
  const dialog = document.getElementById("cancel-dialog");
  if (dialog && dialog.showModal) dialog.showModal();
});

// Swiping left or right on the schedule moves to the next or previous days.
(() => {
  let startX = null, startY = null;
  document.addEventListener("touchstart", (event) => {
    if (!event.target.closest("[data-swipe-area]") || event.touches.length !== 1) { startX = null; return; }
    startX = event.touches[0].clientX;
    startY = event.touches[0].clientY;
  }, { passive: true });
  document.addEventListener("touchend", (event) => {
    if (startX === null) return;
    const dx = event.changedTouches[0].clientX - startX;
    const dy = event.changedTouches[0].clientY - startY;
    startX = null;
    if (Math.abs(dx) < 70 || Math.abs(dx) < 2 * Math.abs(dy)) return;
    const link = document.querySelector(`[data-swipe="${dx < 0 ? "next" : "previous"}"]`);
    if (link) window.location.href = link.href;
  });
})();

// Earlier days load above the Schedule list; keep the days in view where they were.
document.addEventListener("htmx:beforeSwap", (event) => {
  if (event.detail.target.matches("[data-earlier]")) {
    window.earlierSwap = { height: document.documentElement.scrollHeight, top: window.scrollY };
  }
});
document.addEventListener("htmx:afterSettle", () => {
  if (!window.earlierSwap) return;
  const { height, top } = window.earlierSwap;
  window.earlierSwap = null;
  window.scrollTo(0, top + document.documentElement.scrollHeight - height);
});

// The line at the current time on today's column moves each minute.
function placeNowLine() {
  document.querySelectorAll(".timegrid").forEach((grid) => {
    const line = grid.querySelector(".now-line");
    if (!line) return;
    const first = Number(grid.dataset.firstMinute), last = Number(grid.dataset.lastMinute);
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "numeric", hourCycle: "h23" }).formatToParts(new Date());
    const minute = Number(parts.find((p) => p.type === "hour").value) * 60 + Number(parts.find((p) => p.type === "minute").value);
    line.hidden = minute < first || minute > last;
    line.style.top = `${((minute - first) / (last - first)) * 100}%`;
  });
}
document.addEventListener("DOMContentLoaded", () => {
  placeNowLine();
  setInterval(placeNowLine, 60000);
});
