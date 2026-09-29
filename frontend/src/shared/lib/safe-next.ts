/**
 * A post-login return path, or `fallback`.
 *
 * `next` arrives in a query string or a form field, so it is attacker-chosen.
 * Only an in-app path is accepted: it must start with exactly one "/", and it
 * must still resolve to this origin once a URL parser has read it. The parse
 * is what catches the forms a prefix check misses - a backslash or an
 * embedded tab or newline that the WHATWG parser turns into "//evil.example".
 */
const PROBE_ORIGIN = "https://aevrin.invalid";

export function safeNextPath(value: unknown, fallback: string): string {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) {
    return fallback;
  }
  if (value.includes("\\") || /[\u0000-\u001f\u007f]/.test(value)) return fallback;
  try {
    const url = new URL(value, PROBE_ORIGIN);
    if (url.origin !== PROBE_ORIGIN) return fallback;
    // Dot segments are resolved by the parse, so "/..//evil.example" comes
    // back as "//evil.example": protocol-relative, and off-site once a
    // browser follows it. The normalised result is checked again.
    const path = `${url.pathname}${url.search}${url.hash}`;
    return path.startsWith("//") ? fallback : path;
  } catch {
    return fallback;
  }
}
