import { useEffect, useMemo, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import api from "../api/axios";

const formatDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const statusPill = (status) => {
  const normalized = String(status ?? "").toUpperCase();
  if (normalized === "APPROVED") return "bg-emerald-100 text-emerald-800 border-emerald-200";
  if (normalized === "DELIVERED") return "bg-blue-100 text-blue-800 border-blue-200";
  if (normalized === "CANCELLED") return "bg-red-100 text-red-800 border-red-200";
  return "bg-slate-100 text-slate-800 border-slate-200";
};

const paymentPill = (status) => {
  const normalized = String(status ?? "").toUpperCase();
  if (normalized === "PAID") return "bg-emerald-50 text-emerald-800 border-emerald-200";
  if (normalized === "UNPAID") return "bg-amber-50 text-amber-800 border-amber-200";
  return "bg-slate-50 text-slate-800 border-slate-200";
};

export default function OwnerOrders() {
  const [orders, setOrders] = useState([]);
  const [prescriptionsByOrder, setPrescriptionsByOrder] = useState({});
  const [productsById, setProductsById] = useState({});
  const [medicinesById, setMedicinesById] = useState({});

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [downloadError, setDownloadError] = useState("");
  const [isLoadingRx, setIsLoadingRx] = useState(false);

  const totalsByOrderId = useMemo(() => {
    return orders.reduce((acc, order) => {
      const total = (order.items ?? []).reduce((sum, item) => sum + item.quantity * item.unit_price, 0);
      acc[order.id] = total;
      return acc;
    }, {});
  }, [orders]);

  const loadOrders = async () => {
    setIsLoading(true);
    setError("");
    setActionError("");
    setDownloadError("");
    try {
      const res = await api.get("/orders/owner");
      setOrders(res.data ?? []);
    } catch (e) {
      setOrders([]);
      setError(e?.response?.data?.detail ?? "Failed to load orders");
    } finally {
      setIsLoading(false);
    }
  };

  const loadRx = async () => {
    setIsLoadingRx(true);
    try {
      const res = await api.get("/prescriptions/owner");
      const list = Array.isArray(res.data) ? res.data : [];
      const grouped = list.reduce((acc, item) => {
        const key = String(item.order_id ?? "");
        if (!key) return acc;
        acc[key] = acc[key] ?? [];
        acc[key].push(item);
        return acc;
      }, {});
      for (const key of Object.keys(grouped)) {
        grouped[key].sort((a, b) => new Date(b.upload_date ?? 0).getTime() - new Date(a.upload_date ?? 0).getTime());
      }
      setPrescriptionsByOrder(grouped);
    } catch {
      setPrescriptionsByOrder({});
    } finally {
      setIsLoadingRx(false);
    }
  };

  const loadCatalogIndexes = async () => {
    try {
      const [productsRes, medicinesRes] = await Promise.all([api.get("/products/owner"), api.get("/medicines/owner")]);
      const products = Array.isArray(productsRes.data) ? productsRes.data : [];
      const medicines = Array.isArray(medicinesRes.data) ? medicinesRes.data : [];
      setProductsById(
        products.reduce((acc, item) => {
          if (item?.id != null) acc[String(item.id)] = item;
          return acc;
        }, {})
      );
      setMedicinesById(
        medicines.reduce((acc, item) => {
          if (item?.id != null) acc[String(item.id)] = item;
          return acc;
        }, {})
      );
    } catch {
      setProductsById({});
      setMedicinesById({});
    }
  };

  useEffect(() => {
    loadOrders();
    loadRx();
    loadCatalogIndexes();
  }, []);

  const handleOrderAction = async (orderId, action) => {
    setActionError("");
    try {
      const res = await api.post(`/orders/${orderId}/${action}`);
      setOrders((prev) => prev.map((order) => (order.id === orderId ? res.data : order)));
    } catch (e) {
      setActionError(e?.response?.data?.detail ?? "Order update failed");
    }
  };

  const reviewPrescription = async (id, status) => {
    setActionError("");
    try {
      const res = await api.post(`/prescriptions/${id}/review`, { status });
      const updated = res.data;
      const key = String(updated?.order_id ?? "");
      if (!key) return;
      setPrescriptionsByOrder((prev) => {
        const next = { ...prev };
        const list = Array.isArray(next[key]) ? [...next[key]] : [];
        const idx = list.findIndex((p) => p.id === id);
        if (idx >= 0) list[idx] = updated;
        next[key] = list;
        return next;
      });
    } catch (e) {
      setActionError(e?.response?.data?.detail ?? "Failed to update prescription");
    }
  };

  const downloadPrescription = async (prescription) => {
    setDownloadError("");
    try {
      const res = await api.get(`/prescriptions/owner/${prescription.id}/file`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: prescription.content_type ?? "application/octet-stream" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = prescription.original_filename ?? `prescription-${prescription.id}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setDownloadError(e?.response?.data?.detail ?? "Failed to download file");
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-[0_24px_60px_rgba(15,23,42,0.12)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 flex items-center justify-between gap-4 border-b border-slate-200">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">Orders</h1>
            <p className="text-sm text-slate-500 mt-1">Review orders, verify prescriptions (if any), then approve or cancel.</p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                loadOrders();
                loadRx();
              }}
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
          {error ? <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">{error}</div> : null}
          {actionError ? (
            <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">{actionError}</div>
          ) : null}
          {downloadError ? (
            <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">{downloadError}</div>
          ) : null}

          {orders.length === 0 && !isLoading ? (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-slate-600 text-sm">
              No orders yet.
            </div>
          ) : (
            <div className="space-y-4">
              {orders.map((order) => {
                const presc = prescriptionsByOrder[String(order.id)] ?? [];
                const hasRx = Array.isArray(presc) && presc.length > 0;
                const rxApproved = hasRx && presc.some((p) => p.status === "APPROVED");
                const needsRxApproval = hasRx && !rxApproved;
                const total = totalsByOrderId[order.id] ?? 0;

                return (
                  <section key={order.id} className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                    <div className="px-6 py-5 border-b border-slate-200 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-3">
                          <h2 className="text-xl font-semibold text-slate-900">Order #{order.id}</h2>
                          <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs ${statusPill(order.status)}`}>
                            {order.status}
                          </span>
                        </div>
                        <div className="text-sm text-slate-500 mt-1">Placed {formatDate(order.order_date)}</div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs ${paymentPill(order.payment_status)}`}>
                          {order.payment_method} • {order.payment_status}
                        </span>
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full border text-xs bg-slate-50 text-slate-800 border-slate-200">
                          Items: {(order.items ?? []).length}
                        </span>
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full border text-xs bg-slate-50 text-slate-800 border-slate-200">
                          Total: ${Number(total).toFixed(2)}
                        </span>
                        {isLoadingRx ? (
                          <span className="inline-flex items-center px-2.5 py-1 rounded-full border text-xs bg-slate-50 text-slate-600 border-slate-200">
                            Loading Rx…
                          </span>
                        ) : hasRx ? (
                          <span
                            className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs ${
                              rxApproved
                                ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                                : "bg-amber-50 text-amber-800 border-amber-200"
                            }`}
                          >
                            Rx: {rxApproved ? "Approved" : "Pending"}
                          </span>
                        ) : null}
                      </div>
                    </div>

                    <div className="px-6 py-5 grid lg:grid-cols-3 gap-6">
                      <div className="lg:col-span-1 space-y-2 text-sm">
                        <div className="text-slate-900">
                          <span className="font-medium">Customer:</span> {order.customer_name ?? "—"}
                        </div>
                        <div className="text-slate-900">
                          <span className="font-medium">Phone:</span> {order.customer_phone ?? "—"}
                        </div>
                        <div className="text-slate-900">
                          <span className="font-medium">Address:</span> {order.customer_address ?? "—"}
                        </div>
                        {order.customer_notes ? (
                          <div className="text-slate-900">
                            <span className="font-medium">Notes:</span> {order.customer_notes}
                          </div>
                        ) : null}
                      </div>

                      <div className="lg:col-span-2 space-y-4">
                        <div className="rounded-xl border border-slate-200 overflow-hidden">
                          <div className="px-4 py-3 bg-slate-50 text-xs font-semibold text-slate-700">
                            Items
                          </div>
                          <div className="divide-y divide-slate-100">
                            {(order.items ?? []).map((item) => {
                              const label = item.product_id
                                ? productsById[String(item.product_id)]?.name ?? `Product #${item.product_id}`
                                : medicinesById[String(item.medicine_id)]?.name ?? `Medicine #${item.medicine_id}`;
                              return (
                                <div key={item.id} className="px-4 py-3 flex items-center justify-between gap-3 text-sm">
                                  <div className="min-w-0">
                                    <div className="font-medium text-slate-900 truncate">{label}</div>
                                    <div className="text-xs text-slate-500">Unit: ${Number(item.unit_price ?? 0).toFixed(2)}</div>
                                  </div>
                                  <div className="text-slate-700">Qty {item.quantity}</div>
                                </div>
                              );
                            })}
                          </div>
                        </div>

                        {hasRx ? (
                          <div className="rounded-xl border border-slate-200 overflow-hidden">
                            <div className="px-4 py-3 bg-slate-50 flex items-center justify-between gap-3">
                              <div className="text-xs font-semibold text-slate-700">Prescriptions</div>
                              <div className="text-xs text-slate-500">{presc.length} file(s)</div>
                            </div>
                            <div className="divide-y divide-slate-100">
                              {presc.map((p) => (
                                <div key={p.id} className="px-4 py-3">
                                  <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                                    <div className="min-w-0">
                                      <div className="font-medium text-slate-900 truncate">
                                        Rx #{p.id} • {p.original_filename ?? "Upload"}
                                      </div>
                                      <div className="text-xs text-slate-500">
                                        {p.content_type ?? "unknown"} • {formatDate(p.upload_date)}
                                      </div>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs ${statusPill(p.status)}`}>
                                        {p.status}
                                      </span>
                                      <button
                                        type="button"
                                        onClick={() => downloadPrescription(p)}
                                        className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
                                      >
                                        <Download className="w-4 h-4" />
                                        View
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => reviewPrescription(p.id, "APPROVED")}
                                        disabled={p.status === "APPROVED"}
                                        className="px-3 py-2 rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-60"
                                      >
                                        Approve
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => reviewPrescription(p.id, "REJECTED")}
                                        disabled={p.status === "REJECTED"}
                                        className="px-3 py-2 rounded-xl bg-red-600 text-white hover:bg-red-700 disabled:opacity-60"
                                      >
                                        Reject
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleOrderAction(order.id, "approve")}
                            disabled={order.status !== "PENDING" || needsRxApproval}
                            title={needsRxApproval ? "Approve at least one prescription first" : "Approve order"}
                            className="px-4 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                          >
                            Approve order
                          </button>
                          <button
                            type="button"
                            onClick={() => handleOrderAction(order.id, "deliver")}
                            disabled={order.status !== "APPROVED"}
                            className="px-4 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                          >
                            Mark delivered
                          </button>
                          <button
                            type="button"
                            onClick={() => handleOrderAction(order.id, "cancel")}
                            disabled={order.status === "CANCELLED"}
                            className="px-4 py-2 rounded-xl border border-red-200 text-red-700 hover:bg-red-50 disabled:opacity-60"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    </div>
                  </section>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

