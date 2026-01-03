import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3,
  Bell,
  Calendar,
  ChevronDown,
  Copy,
  Home,
  LayoutGrid,
  LogOut,
  Mail,
  MessageCircle,
  Package,
  RefreshCw,
  Settings,
  ShieldCheck,
  Share2,
  ShoppingBag,
  ExternalLink,
  User,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import api from "../../api/axios";

const linkClass = ({ isActive }) =>
  `w-full flex items-center gap-3 px-5 py-3 text-sm transition-colors ${
    isActive
      ? "bg-blue-50 text-blue-600 border-r-2 border-blue-600"
      : "text-gray-600 hover:bg-gray-50"
  }`;

export default function PortalShell({ children }) {
  const { token, user, isAdmin, isOwner, isLoadingUser, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [appointmentsOpen, setAppointmentsOpen] = useState(false);
  const [activePopover, setActivePopover] = useState(null); // "notifications" | "share" | "account" | null
  const headerRef = useRef(null);

  const [pharmacyDomain, setPharmacyDomain] = useState(null);
  const [pharmacyInfo, setPharmacyInfo] = useState(null);
  const [pharmacyInfoError, setPharmacyInfoError] = useState("");
  const [isLoadingPharmacyInfo, setIsLoadingPharmacyInfo] = useState(false);

  const [notifications, setNotifications] = useState({
    ordersPending: 0,
    appointmentsPending: 0,
    escalationsPending: 0,
    rxPending: 0,
  });
  const [notificationError, setNotificationError] = useState("");
  const [isLoadingNotifications, setIsLoadingNotifications] = useState(false);

  const [shareStatus, setShareStatus] = useState("");

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    setActivePopover(null);
  }, [location.pathname]);

  useEffect(() => {
    if (location.pathname.startsWith("/portal/owner/appointments")) {
      setAppointmentsOpen(true);
    }
  }, [location.pathname]);

  useEffect(() => {
    const handler = (event) => {
      if (!headerRef.current) return;
      if (headerRef.current.contains(event.target)) return;
      setActivePopover(null);
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setActivePopover(null);
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  const baseLinks = useMemo(() => [{ to: "/portal", label: "Dashboard", icon: Home }], []);

  const ownerLinks = useMemo(
    () => [
      { to: "/portal/owner/inventory", label: "Inventory", icon: Package },
      { to: "/portal/owner/products", label: "Products", icon: ShoppingBag },
      { to: "/portal/owner/orders", label: "Orders", icon: ShoppingBag },
      { to: "/portal/owner/appointments", label: "Appointments", icon: Calendar },
    { to: "/portal/owner/escalations", label: "Escalations", icon: MessageCircle },
    { to: "/portal/owner/inbox", label: "Inbox", icon: Mail },
    ],
    []
  );

  const appointmentSubLinks = useMemo(
    () => [
      { label: "Overview", to: "/portal/owner/appointments", end: true },
      { label: "Week view", to: "/portal/owner/appointments/week" },
      { label: "Schedule settings", to: "/portal/owner/appointments/schedule" },
    ],
    []
  );

  const adminLinks = useMemo(
    () => [
      { to: "/portal/admin/pharmacies", label: "Pharmacies", icon: ShieldCheck },
      { to: "/portal/admin/ai-logs", label: "AI Logs", icon: BarChart3 },
    ],
    []
  );

  const profileRole = isAdmin ? "Admin" : isOwner ? "Owner" : "Staff";
  const isAppointmentsActive = location.pathname.startsWith("/portal/owner/appointments");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const next = (localStorage.getItem("pharmacy_domain") || "").trim() || null;
    setPharmacyDomain(next);
  }, [token]);

  useEffect(() => {
    const domain = (pharmacyInfo?.domain || "").trim();
    if (domain) setPharmacyDomain(domain);
  }, [pharmacyInfo]);

  const publicOrigin = useMemo(() => {
    if (!pharmacyDomain) return null;
    const raw = pharmacyDomain.trim();
    try {
      if (raw.includes("://")) {
        const url = new URL(raw);
        return url.origin;
      }
      const base = new URL(window.location.origin);
      const [host, port] = raw.split(":");
      base.hostname = host;
      if (port) base.port = port;
      return base.origin;
    } catch {
      return `http://${raw}`;
    }
  }, [pharmacyDomain]);

  const shareLinks = useMemo(() => {
    if (!publicOrigin) return null;
    return {
      storefront: `${publicOrigin}/`,
      shop: `${publicOrigin}/shop`,
      assistant: `${publicOrigin}/shop#assistant`,
    };
  }, [publicOrigin]);

  const copyToClipboard = useCallback(async (text) => {
    setShareStatus("");
    try {
      await navigator.clipboard.writeText(text);
      setShareStatus("Copied to clipboard.");
    } catch {
      try {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
        setShareStatus("Copied to clipboard.");
      } catch {
        setShareStatus("Copy failed. Please copy manually.");
      }
    }
  }, []);

  const loadPharmacyInfo = useCallback(async () => {
    if (!token || !isOwner) return;
    setIsLoadingPharmacyInfo(true);
    setPharmacyInfoError("");
    try {
      const res = await api.get("/pharmacies/me");
      setPharmacyInfo(res.data ?? null);
    } catch (err) {
      setPharmacyInfo(null);
      setPharmacyInfoError(err?.response?.data?.detail ?? "Failed to load pharmacy info");
    } finally {
      setIsLoadingPharmacyInfo(false);
    }
  }, [isOwner, token]);

  useEffect(() => {
    loadPharmacyInfo();
  }, [loadPharmacyInfo]);

  const loadNotifications = useCallback(async () => {
    if (!token || !isOwner) return;
    setIsLoadingNotifications(true);
    setNotificationError("");
    try {
      const [ordersRes, appointmentsRes, escalationsRes, rxRes] = await Promise.all([
        api.get("/orders/owner"),
        api.get("/appointments/owner"),
        api.get("/admin/pharmacist/sessions", { params: { status_filter: "ESCALATED" } }),
        api.get("/prescriptions/owner"),
      ]);

      const orders = Array.isArray(ordersRes.data) ? ordersRes.data : [];
      const appointments = Array.isArray(appointmentsRes.data) ? appointmentsRes.data : [];
      const escalations = Array.isArray(escalationsRes.data) ? escalationsRes.data : [];
      const prescriptions = Array.isArray(rxRes.data) ? rxRes.data : [];

      const norm = (value) => String(value ?? "").toUpperCase();
      setNotifications({
        ordersPending: orders.filter((o) => norm(o.status) === "PENDING").length,
        appointmentsPending: appointments.filter((a) => norm(a.status) === "PENDING").length,
        escalationsPending: escalations.length,
        rxPending: prescriptions.filter((p) => norm(p.status) === "PENDING").length,
      });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setNotificationError(detail ?? "Failed to load notifications");
      setNotifications({ ordersPending: 0, appointmentsPending: 0, escalationsPending: 0, rxPending: 0 });
    } finally {
      setIsLoadingNotifications(false);
    }
  }, [isOwner, token]);

  useEffect(() => {
    if (!token || !isOwner) return undefined;
    loadNotifications();
    const id = window.setInterval(loadNotifications, 60000);
    return () => window.clearInterval(id);
  }, [isOwner, loadNotifications, token]);

  const totalAlerts = notifications.ordersPending + notifications.appointmentsPending + notifications.escalationsPending + notifications.rxPending;

  const togglePopover = useCallback((name) => {
    setShareStatus("");
    setActivePopover((prev) => (prev === name ? null : name));
    if (name === "notifications") loadNotifications();
    if (name === "account") loadPharmacyInfo();
  }, [loadNotifications, loadPharmacyInfo]);

  const openExternal = useCallback((url) => {
    if (!url) return;
    window.open(url, "_blank", "noopener,noreferrer");
  }, []);

  if (!token) {
    return <Navigate to="/portal/login" replace />;
  }
  if (isLoadingUser) {
    return (
      <div className="flex min-h-screen bg-[#f6f7fb] items-center justify-center p-6">
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm px-6 py-4 text-sm text-gray-600">
          Loading portal...
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-[#f6f7fb]">
      {menuOpen ? (
        <button
          type="button"
          className="fixed inset-0 bg-black/30 z-30"
          aria-label="Close navigation menu"
          onClick={() => setMenuOpen(false)}
        />
      ) : null}

      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 bg-white border-r border-gray-200 flex flex-col transition-transform lg:translate-x-0 lg:static ${
          menuOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="px-6 py-6 border-b border-gray-200">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-full bg-blue-600 text-white flex items-center justify-center">
              <div className="w-3 h-3 rounded-full bg-white/90"></div>
            </div>
            <div>
              <div className="text-sm font-semibold text-gray-900">PHARMACY</div>
              <div className="text-xs text-gray-500">MANAGEMENT</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 py-4">
          {baseLinks.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.to} to={item.to} className={linkClass}>
                <Icon className="w-5 h-5" />
                {item.label}
              </NavLink>
            );
          })}
          {isOwner
            ? ownerLinks.map((item) => {
              const Icon = item.icon;
              if (item.label !== "Appointments") {
                return (
                  <NavLink key={item.to} to={item.to} className={linkClass}>
                    <Icon className="w-5 h-5" />
                    {item.label}
                  </NavLink>
                );
              }
              return (
                <div key={item.to} className="w-full">
                  <div
                    className={`w-full flex items-center justify-between px-5 py-3 text-sm transition-colors ${
                      isAppointmentsActive
                        ? "bg-blue-50 text-blue-600 border-r-2 border-blue-600"
                        : "text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => navigate("/portal/owner/appointments")}
                      className="flex items-center gap-3 flex-1 text-left"
                    >
                      <Icon className="w-5 h-5" />
                      {item.label}
                    </button>
                    <button
                      type="button"
                      onClick={() => setAppointmentsOpen((prev) => !prev)}
                      className={`p-1 rounded-md ${isAppointmentsActive ? "text-blue-600" : "text-gray-400 hover:text-gray-600"}`}
                      aria-label="Toggle appointments menu"
                      aria-expanded={appointmentsOpen}
                    >
                      <ChevronDown className={`w-4 h-4 transition-transform ${appointmentsOpen ? "rotate-180" : ""}`} />
                    </button>
                  </div>
                  {appointmentsOpen ? (
                    <div className="mt-1 mb-2 ml-11 mr-4 space-y-1">
                      {appointmentSubLinks.map((sub) => (
                        <NavLink
                          key={sub.to}
                          to={sub.to}
                          end={sub.end}
                          className={({ isActive }) =>
                            `block rounded-lg px-3 py-2 text-xs transition-colors ${
                              isActive ? "bg-blue-50 text-blue-600" : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                            }`
                          }
                        >
                          {sub.label}
                        </NavLink>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })
            : null}
          {isAdmin ? (
            <div className="mt-4">
              <div className="px-5 py-2 text-xs uppercase tracking-wide text-gray-400">Admin</div>
              {adminLinks.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink key={item.to} to={item.to} className={linkClass}>
                    <Icon className="w-5 h-5" />
                    {item.label}
                  </NavLink>
                );
              })}
            </div>
          ) : null}
          <div className="mt-4">
            <NavLink to="/portal/settings" className={linkClass}>
              <Settings className="w-5 h-5" />
              Settings
            </NavLink>
          </div>
        </nav>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header
          ref={headerRef}
          className="bg-white border-b border-gray-200 px-6 md:px-8 py-4 flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMenuOpen((prev) => !prev)}
              className="p-2 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50"
              aria-label="Toggle navigation"
            >
              <LayoutGrid className="w-5 h-5" />
            </button>
          </div>

          <div className="flex items-center gap-3">
            {token ? (
              <>
                <button
                  type="button"
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  title="Inbox"
                  onClick={() => navigate("/portal/owner/inbox")}
                >
                  <Mail className="w-5 h-5 text-gray-600" />
                </button>

                <div className="relative">
                  <button
                    type="button"
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors relative"
                    title="Notifications"
                    onClick={() => togglePopover("notifications")}
                  >
                    <Bell className="w-5 h-5 text-gray-600" />
                    {totalAlerts > 0 ? (
                      <span className="absolute top-1.5 right-1.5 min-w-2 h-2 px-1 bg-red-500 rounded-full"></span>
                    ) : null}
                  </button>

                  {activePopover === "notifications" ? (
                    <div className="absolute right-0 mt-2 w-[360px] max-w-[90vw] bg-white border border-gray-200 rounded-2xl shadow-lg overflow-hidden z-50">
                      <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
                        <div className="text-sm font-semibold text-gray-900">Notifications</div>
                        <button
                          type="button"
                          onClick={loadNotifications}
                          disabled={isLoadingNotifications}
                          className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-gray-200 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                        >
                          <RefreshCw className="w-4 h-4" />
                          Refresh
                        </button>
                      </div>

                      <div className="p-4 space-y-3">
                        {notificationError ? (
                          <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">
                            {notificationError}
                          </div>
                        ) : null}

                        <button
                          type="button"
                          onClick={() => navigate("/portal/owner/orders")}
                          className="w-full text-left px-4 py-3 rounded-xl border border-gray-200 hover:bg-gray-50"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm font-medium text-gray-900">Pending orders</div>
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-gray-200 bg-gray-50 text-xs text-gray-700">
                              {notifications.ordersPending}
                            </span>
                          </div>
                          <div className="text-xs text-gray-500 mt-1">Approve or cancel new orders.</div>
                        </button>

                        <button
                          type="button"
                          onClick={() => navigate("/portal/owner/orders")}
                          className="w-full text-left px-4 py-3 rounded-xl border border-gray-200 hover:bg-gray-50"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm font-medium text-gray-900">Prescriptions to review</div>
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-gray-200 bg-gray-50 text-xs text-gray-700">
                              {notifications.rxPending}
                            </span>
                          </div>
                          <div className="text-xs text-gray-500 mt-1">Approve/reject Rx files attached to orders.</div>
                        </button>

                        <button
                          type="button"
                          onClick={() => navigate("/portal/owner/appointments")}
                          className="w-full text-left px-4 py-3 rounded-xl border border-gray-200 hover:bg-gray-50"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm font-medium text-gray-900">Pending appointments</div>
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-gray-200 bg-gray-50 text-xs text-gray-700">
                              {notifications.appointmentsPending}
                            </span>
                          </div>
                          <div className="text-xs text-gray-500 mt-1">Confirm bookings or update schedule.</div>
                        </button>

                        <button
                          type="button"
                          onClick={() => navigate("/portal/owner/escalations")}
                          className="w-full text-left px-4 py-3 rounded-xl border border-gray-200 hover:bg-gray-50"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm font-medium text-gray-900">AI escalations</div>
                            <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-gray-200 bg-gray-50 text-xs text-gray-700">
                              {notifications.escalationsPending}
                            </span>
                          </div>
                          <div className="text-xs text-gray-500 mt-1">Reply to medical-risk customer questions.</div>
                        </button>

                        <div className="text-xs text-gray-500">
                          {isLoadingNotifications ? "Updating…" : totalAlerts > 0 ? "You have items to review." : "All caught up."}
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="relative">
                  <button
                    type="button"
                    className="p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                    title="Share"
                    onClick={() => togglePopover("share")}
                  >
                    <Share2 className="w-4 h-4" />
                  </button>

                  {activePopover === "share" ? (
                    <div className="absolute right-0 mt-2 w-[420px] max-w-[92vw] bg-white border border-gray-200 rounded-2xl shadow-lg overflow-hidden z-50">
                      <div className="px-4 py-3 border-b border-gray-100">
                        <div className="text-sm font-semibold text-gray-900">Share your pharmacy</div>
                        <div className="text-xs text-gray-500 mt-1">
                          Customer URL base: {shareLinks?.storefront ?? "Set pharmacy domain first"}
                        </div>
                      </div>
                      <div className="p-4 space-y-3">
                        {shareStatus ? (
                          <div className="rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 px-4 py-3 text-sm">
                            {shareStatus}
                          </div>
                        ) : null}

                        <div className="rounded-xl border border-gray-200 p-3">
                          <div className="text-xs font-semibold text-gray-700">Storefront</div>
                          <div className="mt-2 flex items-center gap-2">
                            <input
                              readOnly
                              value={shareLinks?.storefront ?? ""}
                              className="flex-1 px-3 py-2 rounded-lg border border-gray-200 bg-gray-50 text-sm text-gray-700"
                            />
                            <button
                              type="button"
                              onClick={() => copyToClipboard(shareLinks?.storefront ?? "")}
                              disabled={!shareLinks?.storefront}
                              className="p-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                              title="Copy"
                            >
                              <Copy className="w-4 h-4" />
                            </button>
                            <button
                              type="button"
                              onClick={() => openExternal(shareLinks?.storefront)}
                              disabled={!shareLinks?.storefront}
                              className="p-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                              title="Open"
                            >
                              <ExternalLink className="w-4 h-4" />
                            </button>
                          </div>
                        </div>

                        <div className="rounded-xl border border-gray-200 p-3">
                          <div className="text-xs font-semibold text-gray-700">Shop</div>
                          <div className="mt-2 flex items-center gap-2">
                            <input
                              readOnly
                              value={shareLinks?.shop ?? ""}
                              className="flex-1 px-3 py-2 rounded-lg border border-gray-200 bg-gray-50 text-sm text-gray-700"
                            />
                            <button
                              type="button"
                              onClick={() => copyToClipboard(shareLinks?.shop ?? "")}
                              disabled={!shareLinks?.shop}
                              className="p-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                              title="Copy"
                            >
                              <Copy className="w-4 h-4" />
                            </button>
                            <button
                              type="button"
                              onClick={() => openExternal(shareLinks?.shop)}
                              disabled={!shareLinks?.shop}
                              className="p-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                              title="Open"
                            >
                              <ExternalLink className="w-4 h-4" />
                            </button>
                          </div>
                        </div>

                        <div className="rounded-xl border border-gray-200 p-3">
                          <div className="text-xs font-semibold text-gray-700">AI assistant</div>
                          <div className="mt-2 flex items-center gap-2">
                            <input
                              readOnly
                              value={shareLinks?.assistant ?? ""}
                              className="flex-1 px-3 py-2 rounded-lg border border-gray-200 bg-gray-50 text-sm text-gray-700"
                            />
                            <button
                              type="button"
                              onClick={() => copyToClipboard(shareLinks?.assistant ?? "")}
                              disabled={!shareLinks?.assistant}
                              className="p-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                              title="Copy"
                            >
                              <Copy className="w-4 h-4" />
                            </button>
                            <button
                              type="button"
                              onClick={() => openExternal(shareLinks?.assistant)}
                              disabled={!shareLinks?.assistant}
                              className="p-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                              title="Open"
                            >
                              <ExternalLink className="w-4 h-4" />
                            </button>
                          </div>
                        </div>

                        <div className="text-xs text-gray-500">
                          Uses your saved pharmacy domain ({pharmacyDomain ?? "not set"}), e.g.{" "}
                          <span className="font-mono">http://sunrise.localhost:5173/</span>.
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="relative">
                  <button
                    type="button"
                    className="hidden sm:flex items-center gap-3 pl-1 pr-2 py-1 rounded-xl hover:bg-gray-50"
                    onClick={() => togglePopover("account")}
                  >
                    <div className="w-9 h-9 bg-gray-100 rounded-full flex items-center justify-center">
                      <User className="w-5 h-5 text-gray-600" />
                    </div>
                    <div className="text-sm text-left">
                      <div className="text-gray-900 font-medium">{user?.email ?? "Portal account"}</div>
                      <div className="text-xs text-gray-500">{profileRole}</div>
                    </div>
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                  </button>

                  {activePopover === "account" ? (
                    <div className="absolute right-0 mt-2 w-[320px] max-w-[90vw] bg-white border border-gray-200 rounded-2xl shadow-lg overflow-hidden z-50">
                      <div className="px-4 py-3 border-b border-gray-100">
                        <div className="text-sm font-semibold text-gray-900">Account</div>
                        <div className="text-xs text-gray-500 mt-1">{user?.email ?? "Portal account"}</div>
                      </div>
                      <div className="p-4 space-y-3">
                        {pharmacyInfoError ? (
                          <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">
                            {pharmacyInfoError}
                          </div>
                        ) : null}

                        {isOwner ? (
                          <div className="rounded-xl border border-gray-200 p-3">
                            <div className="flex items-center justify-between gap-3">
                              <div>
                                <div className="text-xs font-semibold text-gray-700">Pharmacy</div>
                                <div className="text-sm text-gray-900 mt-1">{pharmacyInfo?.name ?? "Your pharmacy"}</div>
                              </div>
                              <span
                                className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs ${
                                  String(pharmacyInfo?.status ?? "").toUpperCase() === "APPROVED"
                                    ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                                    : "bg-amber-50 text-amber-800 border-amber-200"
                                }`}
                              >
                                {pharmacyInfo?.status ?? (isLoadingPharmacyInfo ? "Loading…" : "—")}
                              </span>
                            </div>
                            <div className="text-xs text-gray-500 mt-2">
                              Domain: <span className="font-mono">{pharmacyDomain ?? "—"}</span>
                            </div>
                            <div className="flex items-center gap-2 mt-3">
                              <button
                                type="button"
                                onClick={() => copyToClipboard(shareLinks?.storefront ?? "")}
                                disabled={!shareLinks?.storefront}
                                className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-gray-200 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                              >
                                <Copy className="w-4 h-4" />
                                Copy link
                              </button>
                              <button
                                type="button"
                                onClick={() => openExternal(shareLinks?.storefront)}
                                disabled={!shareLinks?.storefront}
                                className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-gray-200 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                              >
                                <ExternalLink className="w-4 h-4" />
                                Open
                              </button>
                            </div>
                          </div>
                        ) : null}

                        <div className="space-y-2">
                          <button
                            type="button"
                            onClick={() => navigate("/portal/settings")}
                            className="w-full text-left px-4 py-3 rounded-xl border border-gray-200 hover:bg-gray-50"
                          >
                            <div className="text-sm font-medium text-gray-900">Settings</div>
                            <div className="text-xs text-gray-500 mt-1">Password and pharmacy branding.</div>
                          </button>

                          <button
                            type="button"
                            onClick={logout}
                            className="w-full text-left px-4 py-3 rounded-xl border border-gray-200 hover:bg-gray-50"
                          >
                            <div className="text-sm font-medium text-gray-900">Logout</div>
                            <div className="text-xs text-gray-500 mt-1">Sign out of the portal.</div>
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>

                <button
                  type="button"
                  onClick={logout}
                  className="hidden md:flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50"
                >
                  <LogOut className="w-4 h-4" />
                  Logout
                </button>
              </>
            ) : (
              <div className="flex items-center gap-2">
                <NavLink
                  to="/portal/login"
                  className="px-3 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50"
                >
                  Login
                </NavLink>
                <NavLink
                  to="/portal/register"
                  className="px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
                >
                  Register
                </NavLink>
              </div>
            )}
          </div>
        </header>

        <main className="flex-1 overflow-auto p-6 md:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
