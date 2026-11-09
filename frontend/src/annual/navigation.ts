import { indexRoute } from "./model";

// The return target is always the current document. Only its query can vary.
export function filingHash(hash: string) {
  const [path, query = ""] = hash.split("?");
  const p = new URLSearchParams(query);
  if (p.get("workspace") !== "company") return hash;
  const original = p.get("from");
  if (original !== null) return path + (original ? "?" + original : "");
  // A direct company link may have a cutoff but no originating report view.
  return (
    path +
    (p.has("day") ? "?" + new URLSearchParams({ day: p.get("day")! }) : "")
  );
}
export function rememberFiling(hash: string) {
  if (!hash.startsWith(indexRoute + "/")) return;
  try {
    sessionStorage.setItem("finrisk:last-filing", filingHash(hash));
  } catch {
    /* Storage is optional. */
  }
}
export function lastFiling() {
  try {
    const h = sessionStorage.getItem("finrisk:last-filing");
    return h?.startsWith(indexRoute + "/") ? h : null;
  } catch {
    return null;
  }
}

export function lastCompany() {
  try {
    const path = sessionStorage.getItem("finrisk:last-company");
    return path &&
      /^#\/companies\/[\w%-]+\/dossier(?:\?day=[0-9-]+)?$/.test(path)
      ? path
      : null;
  } catch {
    return null;
  }
}
