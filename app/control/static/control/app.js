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
