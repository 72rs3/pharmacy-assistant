const DEFAULT_PORTAL_HOSTS = ["localhost", "127.0.0.1", "::1"];

function portalHostSet() {
  const raw = import.meta.env.VITE_PORTAL_HOSTS;
  const hosts = (raw ? raw.split(",") : DEFAULT_PORTAL_HOSTS)
    .map((host) => host.trim().toLowerCase())
    .filter(Boolean);
  return new Set(hosts);
}

export function isPortalHost(hostname = typeof window !== "undefined" ? window.location.hostname : "") {
  const normalized = (hostname ?? "").trim().toLowerCase();
  if (!normalized) return false;
  return portalHostSet().has(normalized);
}

export function isTenantHost(hostname = typeof window !== "undefined" ? window.location.hostname : "") {
  const normalized = (hostname ?? "").trim().toLowerCase();
  if (!normalized) return false;
  return !isPortalHost(normalized);
}

