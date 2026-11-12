// Loaded in <head> as a normal (blocking) script so the theme is set before first paint: no flash.
// It must be an external file because the CSP forbids inline scripts.
(function () {
  var theme = null;
  try { theme = localStorage.getItem("ra-theme"); } catch (e) { /* storage blocked: fall back to system */ }
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", theme);
})();
