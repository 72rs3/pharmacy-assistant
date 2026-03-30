const DEFAULT_PORTAL_HOSTS = ["localhost", "127.0.0.1", "::1"];

function normalizeHost(value) {
  const raw = String(value ?? "").trim().toLowerCase();
  if (!raw) return "";
  const withoutProtocol = raw.replace(/^[a-z]+:\/\//, "");
  const withoutPath = withoutProtocol.split("/")[0].trim();
  return withoutPath.split(":")[0].trim();
}

function isPortalPath(pathname = typeof window !== "undefined" ? window.location.pathname : "") {
  const normalized = String(pathname ?? "").trim().toLowerCase();
  return normalized === "/portal" || normalized.startsWith("/portal/");
}

function portalHostSet() {
  const raw = import.meta.env.VITE_PORTAL_HOSTS;
  const hosts = (raw ? raw.split(",") : DEFAULT_PORTAL_HOSTS)
    .map((host) => normalizeHost(host))
    .filter(Boolean);
  return new Set(hosts);
}

export function isPortalHost(
  hostname = typeof window !== "undefined" ? window.location.hostname : "",
  pathname = typeof window !== "undefined" ? window.location.pathname : ""
) {
  if (isPortalPath(pathname)) return true;
  const normalized = normalizeHost(hostname);
  if (!normalized) return false;
  return portalHostSet().has(normalized);
}

export function isTenantHost(
  hostname = typeof window !== "undefined" ? window.location.hostname : "",
  pathname = typeof window !== "undefined" ? window.location.pathname : ""
) {
  const normalized = normalizeHost(hostname);
  if (!normalized) return false;
  return !isPortalHost(normalized, pathname);
}

