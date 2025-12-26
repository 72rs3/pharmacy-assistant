import { useEffect, useMemo, useState } from "react";
import api from "../api/axios";
import EmptyState from "../components/ui/EmptyState";

const formatDate = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const statusTone = (status) => {
  const normalized = String(status || "").toUpperCase();
  if (normalized === "APPROVED") return "bg-emerald-100 text-emerald-800";
  if (normalized === "CANCELLED") return "bg-red-100 text-red-800";
  if (normalized === "DELIVERED") return "bg-blue-100 text-blue-800";
  return "bg-slate-100 text-slate-800";
};

export default function CustomerOrders() {
  const [trackingCode, setTrackingCode] = useState(() =>
    (typeof window !== "undefined" && localStorage.getItem("customer_order_tracking_code")) || ""
  );
  const [orders, setOrders] = useState([]);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);
  const [error, setError] = useState("");
  const [productsIndex, setProductsIndex] = useState(() => new Map());

  const canFetch = useMemo(() => trackingCode.trim().length > 0, [trackingCode]);

  const loadProductsIndex = async () => {
    try {
      const res = await api.get("/products");
      const list = Array.isArray(res.data) ? res.data : [];
      const map = new Map();
      for (const product of list) {
        if (product?.id != null) map.set(Number(product.id), product);
      }
      setProductsIndex(map);
    } catch {
      setProductsIndex(new Map());
    }
  };

  const loadOrders = async (code) => {
    const nextCode = String(code ?? "").trim();
    if (!nextCode) {
      setError("Enter your tracking code to view orders.");
      return;
    }
    setIsLoading(true);
    setError("");
    setSelectedOrder(null);
    try {
      const res = await api.get("/orders/my", {
        headers: { "X-Customer-ID": nextCode },
      });
      const list = Array.isArray(res.data) ? res.data : [];
      setOrders(list);
      if (typeof window !== "undefined") {
        localStorage.setItem("customer_order_tracking_code", nextCode);
      }
    } catch (e) {
      setOrders([]);
      setError(e?.response?.data?.detail ?? "Failed to load orders. Check your tracking code.");
    } finally {
      setIsLoading(false);
    }
  };

  const loadOrderDetails = async (order) => {
    const code = trackingCode.trim();
    if (!code || !order?.id) return;
    setIsLoadingDetails(true);
    setError("");
    try {
      const res = await api.get(`/orders/${order.id}`, {
        headers: { "X-Customer-ID": code },
      });
      setSelectedOrder(res.data ?? null);
    } catch (e) {
      setSelectedOrder(null);
      setError(e?.response?.data?.detail ?? "Failed to load order details.");
    } finally {
      setIsLoadingDetails(false);
    }
  };

  useEffect(() => {
    loadProductsIndex();
  }, []);

  useEffect(() => {
    if (!trackingCode.trim()) return;
    loadOrders(trackingCode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedTotals = useMemo(() => {
    const items = selectedOrder?.items ?? [];
    const total = items.reduce(
      (sum, item) => sum + Number(item.quantity ?? 0) * Number(item.unit_price ?? 0),
      0
    );
    return { total };
  }, [selectedOrder]);

  return (
    <div className="space-y-10">
      <section className="text-center space-y-3">
        <h1 className="text-4xl text-gray-900">Track your order</h1>
        <p className="text-gray-600">
          Enter your tracking code to see whether your order is pending, approved, cancelled, or delivered.
        </p>
      </section>

      <section className="bg-white rounded-2xl shadow-md p-6 max-w-3xl mx-auto space-y-4">
        <div>
          <label htmlFor="tracking_code" className="block text-sm text-gray-700 mb-2">
            Tracking code
          </label>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              id="tracking_code"
              value={trackingCode}
              onChange={(e) => setTrackingCode(e.target.value)}
              className="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
              placeholder="Paste tracking code…"
            />
            <button
              type="button"
              onClick={() => loadOrders(trackingCode)}
              disabled={!canFetch || isLoading}
              className="px-5 py-3 bg-[var(--brand-accent)] text-white rounded-xl hover:opacity-95 disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {isLoading ? "Loading..." : "Check status"}
            </button>
          </div>
          <div className="mt-2 text-xs text-gray-500">
            Tip: your tracking code is saved on this device after checkout.
          </div>
        </div>

        {error ? <div className="text-sm text-red-600">{error}</div> : null}
      </section>

      <section className="max-w-6xl mx-auto grid lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl shadow-md overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
            <h2 className="text-lg text-gray-900">Your orders</h2>
            <button
              type="button"
              onClick={() => loadOrders(trackingCode)}
              disabled={!canFetch || isLoading}
              className="px-4 py-2 border border-gray-200 rounded-lg text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60"
            >
              Refresh
            </button>
          </div>

          <div className="p-6">
            {isLoading ? (
              <div className="text-gray-600 text-sm">Loading orders…</div>
            ) : orders.length === 0 ? (
              <EmptyState
                title="No orders found"
                description={canFetch ? "No orders are linked to this tracking code yet." : "Enter a tracking code to view your orders."}
              />
            ) : (
              <div className="space-y-3">
                {orders.map((order) => (
                  <button
                    key={order.id}
                    type="button"
                    onClick={() => loadOrderDetails(order)}
                    className="w-full text-left border border-gray-200 rounded-xl p-4 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-gray-900 font-medium">Order #{order.id}</div>
                      <span className={`text-xs px-2 py-1 rounded-full ${statusTone(order.status)}`}>{order.status}</span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      {formatDate(order.order_date)} • {order.payment_method} • {order.payment_status}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-md overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg text-gray-900">Order details</h2>
            <div className="text-xs text-gray-500">Select an order to see items and totals.</div>
          </div>

          <div className="p-6">
            {isLoadingDetails ? (
              <div className="text-gray-600 text-sm">Loading details…</div>
            ) : !selectedOrder ? (
              <div className="text-gray-600 text-sm">No order selected.</div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-gray-900 font-semibold">Order #{selectedOrder.id}</div>
                    <div className="text-xs text-gray-500">{formatDate(selectedOrder.order_date)}</div>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded-full ${statusTone(selectedOrder.status)}`}>
                    {selectedOrder.status}
                  </span>
                </div>

                <div className="rounded-xl border border-gray-200 overflow-hidden">
                  <table className="min-w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left px-4 py-3 text-xs font-semibold text-gray-700">Item</th>
                        <th className="text-right px-4 py-3 text-xs font-semibold text-gray-700">Qty</th>
                        <th className="text-right px-4 py-3 text-xs font-semibold text-gray-700">Price</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(selectedOrder.items ?? []).map((item) => {
                        const product = item.product_id ? productsIndex.get(Number(item.product_id)) : null;
                        const label = item.product_id
                          ? product?.name ?? `Product #${item.product_id}`
                          : item.medicine_id
                            ? `Medicine #${item.medicine_id}`
                            : "Item";
                        return (
                          <tr key={item.id} className="border-t border-gray-200">
                            <td className="px-4 py-3 text-gray-900">{label}</td>
                            <td className="px-4 py-3 text-right text-gray-700">{Number(item.quantity ?? 0)}</td>
                            <td className="px-4 py-3 text-right text-gray-700">
                              {formatMoney(Number(item.unit_price ?? 0))}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-700">Total</span>
                  <span className="font-semibold text-gray-900">{formatMoney(selectedTotals.total)}</span>
                </div>

                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
                  A pharmacist reviews and approves orders before delivery. If your order stays pending for too long, contact the pharmacy.
                </div>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

