import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { BarChart3, Calendar, MessageCircle, Package, RefreshCw, ShieldCheck, ShoppingBag } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { isPortalHost } from "../utils/tenant";
import api from "../api/axios";

const LOW_STOCK_THRESHOLD = 10;

const formatDateTime = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const isExpiringSoon = (value, days = 30) => {
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  const now = new Date();
  const threshold = new Date(now.getTime() + days * 24 * 60 * 60 * 1000);
  return date <= threshold;
};

const isApprovedPharmacy = (pharmacy) => {
  return String(pharmacy?.status ?? "").toUpperCase() === "APPROVED" && Boolean(pharmacy?.is_active);
};

export default function PortalHome() {
  const { token, isAdmin, isOwner, isLoadingUser } = useAuth();
  const navigate = useNavigate();

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const [pharmacyInfo, setPharmacyInfo] = useState(null);
  const [medicines, setMedicines] = useState([]);
  const [orders, setOrders] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [escalations, setEscalations] = useState([]);

  const [adminPharmacies, setAdminPharmacies] = useState([]);
  const [adminLogs, setAdminLogs] = useState([]);

  const portal = isPortalHost();

  const loadOwnerDashboard = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const pharmacyRes = await api.get("/pharmacies/me");
      const pharmacy = pharmacyRes.data ?? null;
      setPharmacyInfo(pharmacy);

      if (!isApprovedPharmacy(pharmacy)) {
        setMedicines([]);
        setOrders([]);
        setAppointments([]);
        setEscalations([]);
        return;
      }

      const [medRes, orderRes, apptRes, escRes] = await Promise.all([
        api.get("/medicines/owner"),
        api.get("/orders/owner"),
        api.get("/appointments/owner"),
        api.get("/ai/escalations/owner"),
      ]);
      setMedicines(Array.isArray(medRes.data) ? medRes.data : []);
      setOrders(Array.isArray(orderRes.data) ? orderRes.data : []);
      setAppointments(Array.isArray(apptRes.data) ? apptRes.data : []);
      setEscalations(Array.isArray(escRes.data) ? escRes.data : []);
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to load dashboard data");
      setPharmacyInfo(null);
      setMedicines([]);
      setOrders([]);
      setAppointments([]);
      setEscalations([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadAdminDashboard = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const [pharmRes, logsRes] = await Promise.all([
        api.get("/pharmacies/admin"),
        api.get("/ai/admin/logs", { params: { limit: 80 } }),
      ]);
      setAdminPharmacies(Array.isArray(pharmRes.data) ? pharmRes.data : []);
      setAdminLogs(Array.isArray(logsRes.data) ? logsRes.data : []);
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to load admin dashboard data");
      setAdminPharmacies([]);
      setAdminLogs([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!portal || !token || isLoadingUser) return;
    if (isAdmin) loadAdminDashboard();
    else if (isOwner) loadOwnerDashboard();
  }, [isAdmin, isOwner, isLoadingUser, loadAdminDashboard, loadOwnerDashboard, portal, token]);

  const inventoryRows = useMemo(() => {
    const list = Array.isArray(medicines) ? medicines : [];
    return [...list].sort((a, b) => {
      const aStock = Number(a?.stock_level ?? 0);
      const bStock = Number(b?.stock_level ?? 0);
      if (aStock !== bStock) return aStock - bStock;
      return String(a?.name ?? "").localeCompare(String(b?.name ?? ""));
    });
  }, [medicines]);

  const alerts = useMemo(() => {
    const list = Array.isArray(medicines) ? medicines : [];
    const lowStock = list
      .filter((m) => Number(m?.stock_level ?? 0) <= LOW_STOCK_THRESHOLD)
      .sort((a, b) => Number(a?.stock_level ?? 0) - Number(b?.stock_level ?? 0));
    const expiring = list
      .filter((m) => isExpiringSoon(m?.expiry_date))
      .sort((a, b) => new Date(a?.expiry_date ?? 0).getTime() - new Date(b?.expiry_date ?? 0).getTime());
    return { total: list.length, lowStock, expiring };
  }, [medicines]);

  const orderCounts = useMemo(() => {
    const norm = (v) => String(v ?? "").toUpperCase();
    return (orders ?? []).reduce(
      (acc, o) => {
        acc.total += 1;
        if (norm(o.status) === "PENDING") acc.pending += 1;
        if (norm(o.status) === "APPROVED") acc.approved += 1;
        return acc;
      },
      { total: 0, pending: 0, approved: 0 }
    );
  }, [orders]);

  const upcomingAppointments = useMemo(() => {
    const now = Date.now();
    const list = Array.isArray(appointments) ? appointments : [];
    return [...list]
      .filter((a) => new Date(a?.scheduled_time ?? 0).getTime() >= now)
      .sort((a, b) => new Date(a?.scheduled_time ?? 0).getTime() - new Date(b?.scheduled_time ?? 0).getTime())
      .slice(0, 6);
  }, [appointments]);

  const recentOrders = useMemo(() => {
    const list = Array.isArray(orders) ? orders : [];
    return [...list].sort((a, b) => new Date(b?.order_date ?? 0).getTime() - new Date(a?.order_date ?? 0).getTime()).slice(0, 6);
  }, [orders]);

  const adminCounts = useMemo(() => {
    const normalized = (v) => String(v ?? "").toUpperCase();
    const pharmacies = Array.isArray(adminPharmacies) ? adminPharmacies : [];
    const pharmacyCounts = pharmacies.reduce(
      (acc, p) => {
        const approved = normalized(p.status) === "APPROVED" && Boolean(p.is_active);
        acc.total += 1;
        if (approved) acc.approved += 1;
        else acc.pending += 1;
        return acc;
      },
      { total: 0, approved: 0, pending: 0 }
    );
    return { pharmacyCounts };
  }, [adminPharmacies]);

  const pendingPharmacies = useMemo(() => {
    const normalized = (v) => String(v ?? "").toUpperCase();
    return (adminPharmacies ?? [])
      .filter((p) => !(normalized(p.status) === "APPROVED" && Boolean(p.is_active)))
      .sort((a, b) => String(a?.name ?? "").localeCompare(String(b?.name ?? "")))
      .slice(0, 8);
  }, [adminPharmacies]);

  const statusPill = (approved) =>
    approved ? "bg-emerald-50 text-emerald-800 border-emerald-200" : "bg-amber-50 text-amber-800 border-amber-200";

  const refresh = () => {
    if (isAdmin) return loadAdminDashboard();
    if (isOwner) return loadOwnerDashboard();
    return null;
  };

  if (!portal) return <Navigate to="/" replace />;
  if (!token) return <Navigate to="/portal/login" replace />;
  if (isLoadingUser) {
    return (
      <div className="max-w-6xl mx-auto">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-slate-600 text-sm">
          Loading dashboard...
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-[0_24px_60px_rgba(15,23,42,0.12)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 flex items-center justify-between gap-4 border-b border-slate-200">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">Dashboard</h1>
            <p className="text-sm text-slate-500 mt-1">{isAdmin ? "Admin overview across tenants." : "Owner overview for daily operations."}</p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={refresh}
              disabled={isLoading}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
          </div>
        </div>

        <div className="p-6 bg-slate-50/60 space-y-4">
          {error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm" role="alert">
              {error}
            </div>
          ) : null}

          {isAdmin ? (
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <button
                  type="button"
                  onClick={() => navigate("/portal/admin/pharmacies")}
                  className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 text-left hover:bg-slate-50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-slate-900">Pending approvals</div>
                      <div className="text-xs text-slate-500 mt-1">Pharmacies waiting for approval.</div>
                    </div>
                    <ShieldCheck className="w-5 h-5 text-slate-400" />
                  </div>
                  <div className="text-3xl font-semibold text-slate-900 mt-4">{adminCounts.pharmacyCounts.pending}</div>
                </button>

                <button
                  type="button"
                  onClick={() => navigate("/portal/admin/pharmacies")}
                  className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 text-left hover:bg-slate-50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-slate-900">Approved pharmacies</div>
                      <div className="text-xs text-slate-500 mt-1">Active tenants customers can access.</div>
                    </div>
                    <ShieldCheck className="w-5 h-5 text-slate-400" />
                  </div>
                  <div className="text-3xl font-semibold text-slate-900 mt-4">{adminCounts.pharmacyCounts.approved}</div>
                </button>

                <button
                  type="button"
                  onClick={() => navigate("/portal/admin/ai-logs")}
                  className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 text-left hover:bg-slate-50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-slate-900">Recent AI activity</div>
                      <div className="text-xs text-slate-500 mt-1">Last {adminLogs.length} events.</div>
                    </div>
                    <BarChart3 className="w-5 h-5 text-slate-400" />
                  </div>
                  <div className="text-3xl font-semibold text-slate-900 mt-4">{adminLogs.length}</div>
                </button>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                  <div className="px-6 py-5 border-b border-slate-200 flex items-center justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold text-slate-900">Pending pharmacies</h2>
                      <p className="text-sm text-slate-500 mt-1">Approve tenants to enable storefront access.</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => navigate("/portal/admin/pharmacies")}
                      className="px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-sm"
                    >
                      View all
                    </button>
                  </div>
                  <div className="p-6">
                    {pendingPharmacies.length === 0 ? (
                      <div className="text-sm text-slate-600">No pending pharmacies.</div>
                    ) : (
                      <div className="space-y-3">
                        {pendingPharmacies.map((p) => (
                          <div key={p.id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 px-4 py-3">
                            <div className="min-w-0">
                              <div className="font-medium text-slate-900 truncate">{p.name ?? `Pharmacy #${p.id}`}</div>
                              <div className="text-xs text-slate-500 mt-1">
                                Domain: <span className="font-mono">{p.domain ?? "—"}</span>
                              </div>
                            </div>
                            <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs ${statusPill(false)}`}>Pending</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </section>

                <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                  <div className="px-6 py-5 border-b border-slate-200 flex items-center justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold text-slate-900">Latest AI logs</h2>
                      <p className="text-sm text-slate-500 mt-1">Quick view of recent events.</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => navigate("/portal/admin/ai-logs")}
                      className="px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-sm"
                    >
                      View all
                    </button>
                  </div>
                  <div className="p-6">
                    {adminLogs.length === 0 ? (
                      <div className="text-sm text-slate-600">No logs yet.</div>
                    ) : (
                      <div className="space-y-3">
                        {adminLogs.slice(0, 6).map((log) => (
                          <div key={log.id} className="rounded-xl border border-slate-200 px-4 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <div className="text-xs text-slate-500">{formatDateTime(log.timestamp)}</div>
                              <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-xs text-slate-700">
                                #{log.pharmacy_id}
                              </span>
                            </div>
                            <div className="mt-2 text-sm font-medium text-slate-900">{String(log.log_type ?? "unknown")}</div>
                            <div className="text-xs text-slate-500 mt-1 truncate">{String(log.details ?? "")}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </section>
              </div>
            </div>
          ) : isOwner ? (
            <div className="space-y-4">
              {!isApprovedPharmacy(pharmacyInfo) ? (
                <div className="bg-white rounded-2xl border border-amber-200 shadow-sm p-6">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <h2 className="text-lg font-semibold text-slate-900">Pharmacy approval pending</h2>
                      <p className="text-sm text-slate-600 mt-1">
                        Your pharmacy must be approved by an admin before you can manage inventory, orders, appointments, and escalations.
                      </p>
                      <div className="text-xs text-slate-500 mt-3">
                        Status:{" "}
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs ${statusPill(false)}`}>
                          {pharmacyInfo?.status ?? "PENDING"}
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => navigate("/portal/settings")}
                      className="px-4 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700"
                    >
                      Open settings
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="grid gap-4 md:grid-cols-4">
                    <button
                      type="button"
                      onClick={() => navigate("/portal/owner/inventory")}
                      className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 text-left hover:bg-slate-50"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-slate-900">Low stock</div>
                          <div className="text-xs text-slate-500 mt-1">At or below {LOW_STOCK_THRESHOLD}.</div>
                        </div>
                        <Package className="w-5 h-5 text-slate-400" />
                      </div>
                      <div className="text-3xl font-semibold text-slate-900 mt-4">{alerts.lowStock.length}</div>
                    </button>

                    <button
                      type="button"
                      onClick={() => navigate("/portal/owner/inventory")}
                      className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 text-left hover:bg-slate-50"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-slate-900">Expiring soon</div>
                          <div className="text-xs text-slate-500 mt-1">Next 30 days.</div>
                        </div>
                        <Package className="w-5 h-5 text-slate-400" />
                      </div>
                      <div className="text-3xl font-semibold text-slate-900 mt-4">{alerts.expiring.length}</div>
                    </button>

                    <button
                      type="button"
                      onClick={() => navigate("/portal/owner/orders")}
                      className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 text-left hover:bg-slate-50"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-slate-900">Pending orders</div>
                          <div className="text-xs text-slate-500 mt-1">Need review.</div>
                        </div>
                        <ShoppingBag className="w-5 h-5 text-slate-400" />
                      </div>
                      <div className="text-3xl font-semibold text-slate-900 mt-4">{orderCounts.pending}</div>
                    </button>

                    <button
                      type="button"
                      onClick={() => navigate("/portal/owner/escalations")}
                      className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 text-left hover:bg-slate-50"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-slate-900">AI escalations</div>
                          <div className="text-xs text-slate-500 mt-1">Awaiting reply.</div>
                        </div>
                        <MessageCircle className="w-5 h-5 text-slate-400" />
                      </div>
                      <div className="text-3xl font-semibold text-slate-900 mt-4">{(escalations ?? []).length}</div>
                    </button>
                  </div>

                  <div className="grid gap-4 lg:grid-cols-2">
                    <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                      <div className="px-6 py-5 border-b border-slate-200 flex items-center justify-between gap-3">
                        <div>
                          <h2 className="text-lg font-semibold text-slate-900">Medicine snapshot</h2>
                          <p className="text-sm text-slate-500 mt-1">Lowest stock items first.</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => navigate("/portal/owner/inventory")}
                          className="px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-sm"
                        >
                          Open inventory
                        </button>
                      </div>
                      <div className="max-h-[360px] overflow-auto">
                        <table className="min-w-full text-sm">
                          <thead className="bg-slate-50 sticky top-0 z-10">
                            <tr>
                              <th className="text-left font-semibold px-4 py-3 text-slate-700">Medicine</th>
                              <th className="text-left font-semibold px-4 py-3 text-slate-700">Stock</th>
                              <th className="text-left font-semibold px-4 py-3 text-slate-700">Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {inventoryRows.length === 0 ? (
                              <tr className="border-t border-slate-100">
                                <td className="px-4 py-4 text-slate-600" colSpan={3}>
                                  No medicines yet. Add items in Inventory.
                                </td>
                              </tr>
                            ) : (
                              inventoryRows.slice(0, 30).map((medicine) => {
                                const stock = Number(medicine?.stock_level ?? 0);
                                const low = stock > 0 && stock <= LOW_STOCK_THRESHOLD;
                                const out = stock <= 0;
                                const expSoon = isExpiringSoon(medicine?.expiry_date);
                                const status = out ? "Out of stock" : low ? "Low stock" : expSoon ? "Expiring soon" : "OK";
                                return (
                                  <tr key={medicine.id} className="border-t border-slate-100">
                                    <td className="px-4 py-3 text-slate-900">{medicine?.name ?? "—"}</td>
                                    <td className="px-4 py-3 text-slate-700">{Number.isFinite(stock) ? stock : 0}</td>
                                    <td className="px-4 py-3 text-slate-700">{status}</td>
                                  </tr>
                                );
                              })
                            )}
                          </tbody>
                        </table>
                      </div>
                    </section>

                    <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                      <div className="px-6 py-5 border-b border-slate-200 flex items-center justify-between gap-3">
                        <div>
                          <h2 className="text-lg font-semibold text-slate-900">Next appointments</h2>
                          <p className="text-sm text-slate-500 mt-1">Upcoming bookings.</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => navigate("/portal/owner/appointments")}
                          className="px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-sm"
                        >
                          Open appointments
                        </button>
                      </div>
                      <div className="p-6">
                        {upcomingAppointments.length === 0 ? (
                          <div className="text-sm text-slate-600">No upcoming appointments.</div>
                        ) : (
                          <div className="space-y-3">
                            {upcomingAppointments.map((appt) => (
                              <div key={appt.id} className="rounded-xl border border-slate-200 px-4 py-3 flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <div className="font-medium text-slate-900 truncate">
                                    {appt.type ?? "Appointment"} • {formatDateTime(appt.scheduled_time)}
                                  </div>
                                  <div className="text-xs text-slate-500 mt-1">{appt.customer_name ?? "—"}</div>
                                </div>
                                <Calendar className="w-5 h-5 text-slate-400" />
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </section>
                  </div>

                  <section className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                    <div className="px-6 py-5 border-b border-slate-200 flex items-center justify-between gap-3">
                      <div>
                        <h2 className="text-lg font-semibold text-slate-900">Recent orders</h2>
                        <p className="text-sm text-slate-500 mt-1">Latest activity.</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => navigate("/portal/owner/orders")}
                        className="px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-sm"
                      >
                        Open orders
                      </button>
                    </div>
                    <div className="p-6">
                      {recentOrders.length === 0 ? (
                        <div className="text-sm text-slate-600">No orders yet.</div>
                      ) : (
                        <div className="grid gap-3 md:grid-cols-2">
                          {recentOrders.map((order) => (
                            <div key={order.id} className="rounded-xl border border-slate-200 px-4 py-3">
                              <div className="flex items-center justify-between gap-3">
                                <div className="font-semibold text-slate-900">Order #{order.id}</div>
                                <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-xs text-slate-700">
                                  {order.status}
                                </span>
                              </div>
                              <div className="text-xs text-slate-500 mt-2">Placed {formatDateTime(order.order_date)}</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </section>
                </>
              )}
            </div>
          ) : (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-slate-600 text-sm">
              This account has no admin or owner access configured.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
