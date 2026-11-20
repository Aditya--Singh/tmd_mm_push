// Embed mode: the app is opened as http://<host>:8095/?embed=1 inside the Executive
// Intelligence Hub. The hub may say it either way: "embed" and "embedded" are both read.
let cached: boolean | null = null;

export function isEmbed(): boolean {
  if (cached !== null) return cached;
  const params = new URLSearchParams(window.location.search);
  try {
    if (params.get("embed") === "1" || params.get("embedded") === "1")
      sessionStorage.setItem("embed", "1");
    if (params.get("embed") === "0" || params.get("embedded") === "0")
      sessionStorage.removeItem("embed");
    cached = sessionStorage.getItem("embed") === "1";
  } catch {
    cached =
      params.get("embed") === "1" || params.get("embedded") === "1";
  }
  return cached;
}
