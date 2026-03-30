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

function cleanPath(pathname = typeof window !== "undefined" ? window.location.pathname : "") {
  const normalized = String(pathname ?? "").trim();
  if (!normalized) return "/";
  return normalized.startsWith("/") ? normalized : `/${normalized}`;
}

function firstPathSegment(pathname = typeof window !== "undefined" ? window.location.pathname : "") {
  const normalizedPath = cleanPath(pathname);
  return normalizedPath.split("/").filter(Boolean)[0]?.trim().toLowerCase() ?? "";
}

function portalHostSet() {
  const raw = import.meta?.env?.VITE_PORTAL_HOSTS;
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
  const firstSegment = firstPathSegment(pathname);
  if (portalHostSet().has(normalized) && firstSegment && firstSegment !== "portal") {
    return false;
  }
  return portalHostSet().has(normalized);
}

export function getTenantSlug(
  hostname = typeof window !== "undefined" ? window.location.hostname : "",
  pathname = typeof window !== "undefined" ? window.location.pathname : ""
) {
  if (isPortalHost(hostname, pathname)) return "";
  const firstSegment = firstPathSegment(pathname);
  if (!firstSegment || firstSegment === "portal") return "";
  const normalizedHost = normalizeHost(hostname);
  if (!normalizedHost) return "";
  if (portalHostSet().has(normalizedHost)) return firstSegment;
  return "";
}

export function getCustomerBasePath(
  hostname = typeof window !== "undefined" ? window.location.hostname : "",
  pathname = typeof window !== "undefined" ? window.location.pathname : ""
) {
  const slug = getTenantSlug(hostname, pathname);
  return slug ? `/${slug}` : "";
}

export function getStorefrontUrlForDomain(
  domain,
  origin = typeof window !== "undefined" ? window.location.origin : "",
  portalHosts = portalHostSet()
) {
  const normalizedDomain = normalizeHost(domain);
  if (!normalizedDomain) return null;
  try {
    const current = new URL(origin);
    const currentHost = normalizeHost(current.hostname);
    const isCurrentLocalPortal = DEFAULT_PORTAL_HOSTS.includes(currentHost);
    if (normalizedDomain.includes(".localhost") && isCurrentLocalPortal) {
      current.hostname = normalizedDomain;
      current.pathname = "/";
      current.search = "";
      current.hash = "";
      return current.origin;
    }
    if (!portalHosts.has(currentHost) && currentHost === normalizedDomain) {
      current.hostname = normalizedDomain;
      current.pathname = "/";
      current.search = "";
      current.hash = "";
      return current.origin;
    }
    const slug = normalizedDomain.split(".")[0]?.trim().toLowerCase();
    if (!slug) return null;
    current.pathname = `/${slug}`;
    current.search = "";
    current.hash = "";
    return current.toString().replace(/\/$/, "");
  } catch {
    return null;
  }
}

export function isTenantHost(
  hostname = typeof window !== "undefined" ? window.location.hostname : "",
  pathname = typeof window !== "undefined" ? window.location.pathname : ""
) {
  const normalized = normalizeHost(hostname);
  if (!normalized) return false;
  return !isPortalHost(normalized, pathname);
}

