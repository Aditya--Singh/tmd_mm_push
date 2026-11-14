// Embed mode: open the app as  http://<host>:8090/?embed=1  (optionally &theme=light|dark) inside the
// Top Management Dashboard. The left sidebar is replaced by a slim tab bar so it fits in a dashboard tab.
// The dashboard may say it either way: "embed" and "embedded" are both read.
let cached: boolean | null = null;

export function isEmbed(): boolean {
  if (cached !== null) return cached;
  const params = new URLSearchParams(window.location.search);
  try {
    if (params.get("embed") === "1" || params.get("embedded") === "1") sessionStorage.setItem("embed", "1");
    if (params.get("embed") === "0" || params.get("embedded") === "0") sessionStorage.removeItem("embed");
    cached = sessionStorage.getItem("embed") === "1";
  } catch {
    cached = params.get("embed") === "1" || params.get("embedded") === "1";
  }
  const theme = params.get("theme");
  if (theme === "dark" || theme === "light") {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try { localStorage.setItem("theme", theme); } catch { /* ignore */ }
  }
  return cached;
}
