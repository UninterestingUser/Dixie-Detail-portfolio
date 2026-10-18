// Register the service worker, which makes the control app installable.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
}
