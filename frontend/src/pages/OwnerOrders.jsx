import { useEffect, useMemo, useState } from "react";
import api from "../api/axios";

const formatDate = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const statusTone = (status) => {
  const normalized = String(status || "").toUpperCase();
  if (normalized === "APPROVED") return "status-pill status-pill--success";
  if (normalized === "CANCELLED") return "status-pill status-pill--danger";
  if (normalized === "DELIVERED") return "status-pill status-pill--info";
  return "status-pill";
};

export default function OwnerOrders() {
  const [orders, setOrders] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");

  const loadOrders = async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await api.get("/orders/owner");
      setOrders(res.data ?? []);
    } catch (err) {
      setOrders([]);
      setError(err?.response?.data?.detail ?? "Failed to load orders");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadOrders();
  }, []);

  const totals = useMemo(() => {
    return orders.reduce((acc, order) => {
      const total = (order.items ?? []).reduce((sum, item) => sum + item.quantity * item.unit_price, 0);
      acc[order.id] = total;
      return acc;
    }, {});
  }, [orders]);

  const handleAction = async (orderId, action) => {
    setActionError("");
    try {
      const res = await api.post(`/orders/${orderId}/${action}`);
      setOrders((prev) => prev.map((order) => (order.id === orderId ? res.data : order)));
    } catch (err) {
      setActionError(err?.response?.data?.detail ?? "Order update failed");
    }
  };

  return (
    <div className="container">
      <div className="section-header">
        <div>
          <h1 className="page-title">Orders</h1>
          <p className="page-subtitle">Review COD orders and approve or cancel them.</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={loadOrders} disabled={isLoading}>
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error ? <div className="alert alert-danger" style={{ marginTop: "1rem" }}>{error}</div> : null}
      {actionError ? <div className="alert alert-danger" style={{ marginTop: "1rem" }}>{actionError}</div> : null}

      {orders.length === 0 && !isLoading ? (
        <div className="card reveal" style={{ marginTop: "1rem" }}>
          <p className="help">No orders yet.</p>
        </div>
      ) : (
        <div className="stack" style={{ marginTop: "1rem" }}>
          {orders.map((order) => (
            <section key={order.id} className="card reveal">
              <header className="card-header">
                <div>
                  <h2 className="card-title">Order #{order.id}</h2>
                  <p className="card-description">Placed {formatDate(order.order_date)}</p>
                </div>
                <span className={statusTone(order.status)}>{order.status}</span>
              </header>

              <div className="grid" style={{ gap: "0.6rem" }}>
                <div className="inline" style={{ flexWrap: "wrap" }}>
                  <span className="badge">Payment: {order.payment_method}</span>
                  <span className="badge">Status: {order.payment_status}</span>
                  <span className="badge">Items: {(order.items ?? []).length}</span>
                  <span className="badge">Total: ${totals[order.id]?.toFixed(2) ?? "0.00"}</span>
                </div>

                <div className="grid" style={{ gap: "0.25rem" }}>
                  {order.customer_name ? <p className="help"><strong>Customer:</strong> {order.customer_name}</p> : null}
                  {order.customer_phone ? <p className="help"><strong>Phone:</strong> {order.customer_phone}</p> : null}
                  {order.customer_address ? <p className="help"><strong>Address:</strong> {order.customer_address}</p> : null}
                  {order.customer_notes ? <p className="help"><strong>Notes:</strong> {order.customer_notes}</p> : null}
                </div>

                {(order.items ?? []).length > 0 ? (
                  <ul className="list compact">
                    {order.items.map((item) => (
                      <li key={item.id} className="list-item compact">
                        <div>
                          <p className="list-item-title">Medicine #{item.medicine_id}</p>
                          <p className="list-item-meta">Qty {item.quantity} • ${item.unit_price.toFixed(2)} each</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="help">No order items found.</p>
                )}

                <div className="actions" style={{ justifyContent: "flex-start" }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => handleAction(order.id, "approve")}
                    disabled={order.status !== "PENDING"}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => handleAction(order.id, "deliver")}
                    disabled={order.status !== "APPROVED"}
                  >
                    Mark delivered
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={() => handleAction(order.id, "cancel")}
                    disabled={order.status === "CANCELLED"}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
