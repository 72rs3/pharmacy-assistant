import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import api from "../api/axios";
import { useTenant } from "../context/TenantContext";
import { isPortalHost } from "../utils/tenant";

const ORDER_TRACKING_KEY = "customer_order_tracking";
const APPOINTMENT_TRACKING_KEY = "customer_appointment_tracking";

const formatDate = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

export default function Home() {
  if (isPortalHost()) {
    return <Navigate to="/portal" replace />;
  }

  const { pharmacy, isLoadingTenant, tenantError, reloadTenant } = useTenant() ?? {};
  const [medicines, setMedicines] = useState([]);
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [medicineError, setMedicineError] = useState("");

  const [cart, setCart] = useState([]);
  const [checkout, setCheckout] = useState({
    name: "",
    phone: "",
    address: "",
    notes: "",
  });
  const [isSubmittingOrder, setIsSubmittingOrder] = useState(false);
  const [orderError, setOrderError] = useState("");
  const [orderSuccess, setOrderSuccess] = useState(null);
  const [requiresPrescription, setRequiresPrescription] = useState(false);

  const [orderTrackingCode, setOrderTrackingCode] = useState(() =>
    typeof window !== "undefined" ? localStorage.getItem(ORDER_TRACKING_KEY) ?? "" : ""
  );
  const [orders, setOrders] = useState([]);
  const [ordersError, setOrdersError] = useState("");
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [orderDetailError, setOrderDetailError] = useState("");

  const [prescriptionOrderId, setPrescriptionOrderId] = useState("");
  const [prescriptionFile, setPrescriptionFile] = useState(null);
  const [prescriptionStatus, setPrescriptionStatus] = useState("");
  const [prescriptionError, setPrescriptionError] = useState("");

  const [appointmentForm, setAppointmentForm] = useState({
    name: "",
    phone: "",
    type: "Vaccination",
    scheduledTime: "",
    vaccineName: "",
  });
  const [appointmentTrackingCode, setAppointmentTrackingCode] = useState(() =>
    typeof window !== "undefined" ? localStorage.getItem(APPOINTMENT_TRACKING_KEY) ?? "" : ""
  );
  const [appointmentSuccess, setAppointmentSuccess] = useState("");
  const [appointmentError, setAppointmentError] = useState("");
  const [appointments, setAppointments] = useState([]);
  const [appointmentsLoading, setAppointmentsLoading] = useState(false);

  const filteredMedicines = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return medicines;

    return medicines.filter((medicine) => {
      const name = medicine?.name?.toLowerCase() ?? "";
      const category = medicine?.category?.toLowerCase() ?? "";
      return name.includes(query) || category.includes(query);
    });
  }, [medicines, search]);

  const cartTotal = useMemo(() => {
    return cart.reduce((sum, item) => sum + item.quantity * item.price, 0);
  }, [cart]);

  const stockBadge = (medicine) => {
    const stock = Number(medicine?.stock_level ?? 0);
    if (!Number.isFinite(stock) || stock <= 0) {
      return <span className="badge badge-danger">Out of stock</span>;
    }
    if (stock <= 5) {
      return <span className="badge badge-warning">Low stock</span>;
    }
    return <span className="badge badge-success">In stock</span>;
  };

  const loadMedicines = async () => {
    setIsLoading(true);
    setMedicineError("");
    try {
      const medicinesRes = await api.get("/medicines/");
      setMedicines(medicinesRes.data ?? []);
    } catch (e) {
      setMedicines([]);
      setMedicineError(e?.response?.data?.detail ?? "Failed to load medicines");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!pharmacy) return;
    loadMedicines();
  }, [pharmacy?.name]);

  const addToCart = (medicine) => {
    setCart((prev) => {
      const existing = prev.find((item) => item.id === medicine.id);
      if (existing) {
        return prev.map((item) => (item.id === medicine.id ? { ...item, quantity: item.quantity + 1 } : item));
      }
      return [...prev, { id: medicine.id, name: medicine.name, price: medicine.price, quantity: 1 }];
    });
  };

  const updateCartQuantity = (medicineId, quantity) => {
    if (quantity <= 0) {
      setCart((prev) => prev.filter((item) => item.id !== medicineId));
      return;
    }
    setCart((prev) => prev.map((item) => (item.id === medicineId ? { ...item, quantity } : item)));
  };

  const loadOrders = async (tracking) => {
    const code = tracking?.trim();
    if (!code) {
      setOrders([]);
      return;
    }

    setOrdersLoading(true);
    setOrdersError("");
    try {
      const res = await api.get("/orders/my", {
        headers: { "X-Customer-ID": code },
      });
      setOrders(res.data ?? []);
    } catch (err) {
      setOrders([]);
      setOrdersError(err?.response?.data?.detail ?? "Failed to load orders");
    } finally {
      setOrdersLoading(false);
    }
  };

  const handleCheckout = async (event) => {
    event.preventDefault();
    setOrderError("");
    setOrderSuccess(null);
    setRequiresPrescription(false);

    if (!cart.length) {
      setOrderError("Add at least one medicine to the cart.");
      return;
    }

    if (!pharmacy?.support_cod) {
      setOrderError("This pharmacy is not accepting cash on delivery right now.");
      return;
    }

    setIsSubmittingOrder(true);
    try {
      const payload = {
        customer_name: checkout.name,
        customer_phone: checkout.phone,
        customer_address: checkout.address,
        customer_notes: checkout.notes || null,
        items: cart.map((item) => ({
          medicine_id: item.id,
          quantity: item.quantity,
        })),
      };
      const res = await api.post("/orders", payload);
      setOrderSuccess(res.data);
      setRequiresPrescription(Boolean(res.data?.requires_prescription));
      setCart([]);
      if (res.data?.tracking_code) {
        setOrderTrackingCode(res.data.tracking_code);
        if (typeof window !== "undefined") {
          localStorage.setItem(ORDER_TRACKING_KEY, res.data.tracking_code);
        }
      }
      if (res.data?.order_id) {
        setPrescriptionOrderId(String(res.data.order_id));
      }
      await loadOrders(res.data?.tracking_code ?? orderTrackingCode);
    } catch (err) {
      setOrderError(err?.response?.data?.detail ?? "Checkout failed");
    } finally {
      setIsSubmittingOrder(false);
    }
  };

  const handleOrderLookup = async () => {
    if (!orderTrackingCode.trim()) {
      setOrdersError("Enter a tracking code to view orders.");
      return;
    }
    if (typeof window !== "undefined") {
      localStorage.setItem(ORDER_TRACKING_KEY, orderTrackingCode.trim());
    }
    await loadOrders(orderTrackingCode);
  };

  const loadOrderDetail = async (orderId) => {
    setOrderDetailError("");
    setSelectedOrder(null);
    try {
      const res = await api.get(`/orders/${orderId}`, {
        headers: { "X-Customer-ID": orderTrackingCode },
      });
      setSelectedOrder(res.data);
    } catch (err) {
      setOrderDetailError(err?.response?.data?.detail ?? "Unable to load order details");
    }
  };

  const uploadPrescription = async (event) => {
    event.preventDefault();
    setPrescriptionError("");
    setPrescriptionStatus("");
    if (!prescriptionOrderId || !prescriptionFile) {
      setPrescriptionError("Provide an order ID and prescription file.");
      return;
    }

    const formData = new FormData();
    formData.append("order_id", prescriptionOrderId);
    formData.append("file", prescriptionFile);

    try {
      const res = await api.post("/prescriptions/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPrescriptionStatus(`Uploaded. Status: ${res.data?.status ?? "PENDING"}`);
    } catch (err) {
      setPrescriptionError(err?.response?.data?.detail ?? "Upload failed");
    }
  };

  const loadAppointments = async (tracking) => {
    const code = tracking?.trim();
    if (!code) {
      setAppointments([]);
      return;
    }

    setAppointmentsLoading(true);
    setAppointmentError("");
    try {
      const res = await api.get("/appointments/my", {
        headers: { "X-Customer-ID": code },
      });
      setAppointments(res.data ?? []);
    } catch (err) {
      setAppointments([]);
      setAppointmentError(err?.response?.data?.detail ?? "Failed to load appointments");
    } finally {
      setAppointmentsLoading(false);
    }
  };

  const bookAppointment = async (event) => {
    event.preventDefault();
    setAppointmentError("");
    setAppointmentSuccess("");

    if (!appointmentForm.scheduledTime) {
      setAppointmentError("Pick a time for your appointment.");
      return;
    }

    try {
      const payload = {
        customer_name: appointmentForm.name,
        customer_phone: appointmentForm.phone,
        type: appointmentForm.type,
        scheduled_time: new Date(appointmentForm.scheduledTime).toISOString(),
        vaccine_name: appointmentForm.vaccineName || null,
      };
      const res = await api.post("/appointments", payload);
      if (res.data?.tracking_code) {
        setAppointmentTrackingCode(res.data.tracking_code);
        if (typeof window !== "undefined") {
          localStorage.setItem(APPOINTMENT_TRACKING_KEY, res.data.tracking_code);
        }
        setAppointmentSuccess(`Booked. Tracking code: ${res.data.tracking_code}`);
      } else {
        setAppointmentSuccess("Booked. Keep your tracking code from the confirmation message.");
      }
      setAppointmentForm((prev) => ({ ...prev, scheduledTime: "" }));
      await loadAppointments(res.data?.tracking_code ?? appointmentTrackingCode);
    } catch (err) {
      setAppointmentError(err?.response?.data?.detail ?? "Booking failed");
    }
  };

  const handleAppointmentLookup = async () => {
    if (!appointmentTrackingCode.trim()) {
      setAppointmentError("Enter a tracking code to view appointments.");
      return;
    }
    if (typeof window !== "undefined") {
      localStorage.setItem(APPOINTMENT_TRACKING_KEY, appointmentTrackingCode.trim());
    }
    await loadAppointments(appointmentTrackingCode);
  };

  if (!pharmacy) {
    return (
      <div className="container">
        <h1 className="page-title">Pharmacy not available</h1>
        <p className="page-subtitle">This pharmacy could not be found or is not yet approved.</p>

        <div className="card" style={{ marginTop: "1.25rem" }}>
          <header className="card-header">
            <div>
              <h2 className="card-title">Try again</h2>
              <p className="card-description">
                Check the pharmacy address and try again. If you are staff, use the portal on{" "}
                <span className="badge">localhost</span>.
              </p>
            </div>
            <button type="button" className="btn btn-ghost" onClick={reloadTenant} disabled={Boolean(isLoadingTenant)}>
              {isLoadingTenant ? "Retrying..." : "Retry"}
            </button>
          </header>

          {tenantError ? <div className="alert alert-danger">{tenantError}</div> : null}
        </div>
      </div>
    );
  }

  return (
    <div className="container">
      <section className="hero reveal">
        <div>
          <h1 className="hero-title">{pharmacy.name}</h1>
          <p className="hero-subtitle">
            Browse medicines, place a cash-on-delivery order, upload prescriptions, or book a vaccine appointment.
          </p>
          <div className="hero-badges">
            <span className="badge badge-success">{pharmacy.support_cod ? "COD available" : "COD unavailable"}</span>
            {pharmacy.operating_hours ? <span className="badge">Hours: {pharmacy.operating_hours}</span> : null}
          </div>
        </div>
        <div className="hero-card">
          <h2 className="card-title">About this pharmacy</h2>
          <p className="help">{pharmacy.branding_details || "This pharmacy has not added additional details yet."}</p>
        </div>
      </section>

      <div className="storefront-grid" style={{ marginTop: "1.5rem" }}>
        <section className="card reveal">
          <header className="card-header">
            <div>
              <h2 className="card-title">Medicines</h2>
              <p className="card-description">Search, filter, and add medicines to your cart.</p>
            </div>
            <button type="button" className="btn btn-ghost" onClick={loadMedicines} disabled={isLoading}>
              {isLoading ? "Refreshing..." : "Refresh"}
            </button>
          </header>

          <div className="grid" style={{ gap: "0.75rem" }}>
            {medicineError ? <div className="alert alert-danger">{medicineError}</div> : null}

            <input
              type="text"
              className="input"
              placeholder="Search by name or category"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />

            {isLoading && medicines.length === 0 ? <p className="help">Loading medicines...</p> : null}

            {filteredMedicines.length === 0 ? (
              <p className="help">{medicines.length === 0 ? "No medicines listed yet." : "No matches found."}</p>
            ) : (
              <ul className="list">
                {filteredMedicines.map((medicine) => (
                  <li key={medicine.id} className="list-item">
                    <div>
                      <p className="list-item-title">
                        {medicine.name} <span className="help">$ {medicine.price}</span>
                      </p>
                      <p className="list-item-meta">
                        {medicine.category ? `Category: ${medicine.category} · ` : ""}
                        {medicine.prescription_required ? "Prescription required" : "OTC"}
                        {` · Stock: ${medicine.stock_level}`}
                      </p>
                    </div>
                    <div className="inline" style={{ flexWrap: "wrap", justifyContent: "flex-end" }}>
                      {stockBadge(medicine)}
                      <button type="button" className="btn btn-primary" onClick={() => addToCart(medicine)} disabled={medicine.stock_level <= 0}>
                        Add
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="card reveal">
          <header className="card-header">
            <div>
              <h2 className="card-title">Your cart</h2>
              <p className="card-description">Review quantities and submit your COD order.</p>
            </div>
            <span className="badge">${cartTotal.toFixed(2)}</span>
          </header>

          <div className="grid" style={{ gap: "0.8rem" }}>
            {cart.length === 0 ? (
              <p className="help">Add medicines from the list to get started.</p>
            ) : (
              <ul className="list compact">
                {cart.map((item) => (
                  <li key={item.id} className="list-item compact">
                    <div>
                      <p className="list-item-title">{item.name}</p>
                      <p className="list-item-meta">
                        ${item.price.toFixed(2)} · Qty {item.quantity}
                      </p>
                    </div>
                    <div className="inline">
                      <input
                        type="number"
                        min="1"
                        className="input input-compact"
                        value={item.quantity}
                        onChange={(e) => updateCartQuantity(item.id, Number(e.target.value))}
                      />
                      <button type="button" className="btn btn-ghost" onClick={() => updateCartQuantity(item.id, 0)}>
                        Remove
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}

            <form className="form" onSubmit={handleCheckout}>
              {orderError ? <div className="alert alert-danger">{orderError}</div> : null}
              {orderSuccess ? (
                <div className="alert">
                  <strong>Order placed.</strong> Tracking code: {orderSuccess.tracking_code}
                </div>
              ) : null}

              <div className="form-row">
                <label className="label" htmlFor="customerName">
                  Full name
                </label>
                <input id="customerName" className="input" value={checkout.name} onChange={(e) => setCheckout((prev) => ({ ...prev, name: e.target.value }))} required />
              </div>

              <div className="form-row">
                <label className="label" htmlFor="customerPhone">
                  Phone
                </label>
                <input id="customerPhone" className="input" value={checkout.phone} onChange={(e) => setCheckout((prev) => ({ ...prev, phone: e.target.value }))} required />
              </div>

              <div className="form-row">
                <label className="label" htmlFor="customerAddress">
                  Delivery address
                </label>
                <input id="customerAddress" className="input" value={checkout.address} onChange={(e) => setCheckout((prev) => ({ ...prev, address: e.target.value }))} required />
              </div>

              <div className="form-row">
                <label className="label" htmlFor="customerNotes">
                  Notes (optional)
                </label>
                <textarea id="customerNotes" className="textarea" rows="3" value={checkout.notes} onChange={(e) => setCheckout((prev) => ({ ...prev, notes: e.target.value }))} />
              </div>

              <button className="btn btn-primary" type="submit" disabled={isSubmittingOrder}>
                {isSubmittingOrder ? "Placing order..." : "Place COD order"}
              </button>
            </form>
          </div>
        </section>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1.5rem" }}>
        <section className="card reveal">
          <header className="card-header">
            <div>
              <h2 className="card-title">Track your order</h2>
              <p className="card-description">Use the tracking code to view order status.</p>
            </div>
          </header>

          <div className="grid" style={{ gap: "0.75rem" }}>
            <label className="form-row">
              <span className="label">Tracking code</span>
              <input className="input" value={orderTrackingCode} onChange={(e) => setOrderTrackingCode(e.target.value)} placeholder="Paste tracking code" />
            </label>
            <button type="button" className="btn btn-primary" onClick={handleOrderLookup}>
              View orders
            </button>
            {ordersError ? <div className="alert alert-danger">{ordersError}</div> : null}
            {ordersLoading ? <p className="help">Loading orders...</p> : null}
            {orders.length === 0 && !ordersLoading ? <p className="help">No orders found.</p> : null}

            {orders.length > 0 ? (
              <ul className="list compact">
                {orders.map((order) => (
                  <li key={order.id} className="list-item compact">
                    <div>
                      <p className="list-item-title">Order #{order.id}</p>
                      <p className="list-item-meta">
                        {formatDate(order.order_date)} · {order.status}
                      </p>
                    </div>
                    <button type="button" className="btn btn-ghost" onClick={() => loadOrderDetail(order.id)}>
                      Details
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            {orderDetailError ? <div className="alert alert-danger">{orderDetailError}</div> : null}
            {selectedOrder ? (
              <div className="card-subtle">
                <h3 className="card-title">Order #{selectedOrder.id} items</h3>
                {(selectedOrder.items ?? []).length === 0 ? (
                  <p className="help">No items returned.</p>
                ) : (
                  <ul className="list compact">
                    {selectedOrder.items.map((item) => (
                      <li key={item.id} className="list-item compact">
                        <div>
                          <p className="list-item-title">Medicine #{item.medicine_id}</p>
                          <p className="list-item-meta">
                            Qty {item.quantity} · ${item.unit_price.toFixed(2)} each
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : null}
          </div>
        </section>

        <section className="card reveal">
          <header className="card-header">
            <div>
              <h2 className="card-title">Prescription upload</h2>
              <p className="card-description">Upload a prescription if your order requires one.</p>
            </div>
            {requiresPrescription ? <span className="badge badge-warning">Required</span> : null}
          </header>

          <form className="form" onSubmit={uploadPrescription}>
            {prescriptionError ? <div className="alert alert-danger">{prescriptionError}</div> : null}
            {prescriptionStatus ? <div className="alert">{prescriptionStatus}</div> : null}

            <div className="form-row">
              <label className="label" htmlFor="prescriptionOrderId">
                Order ID
              </label>
              <input id="prescriptionOrderId" className="input" value={prescriptionOrderId} onChange={(e) => setPrescriptionOrderId(e.target.value)} placeholder="e.g. 42" />
            </div>

            <div className="form-row">
              <label className="label" htmlFor="prescriptionFile">
                Prescription file
              </label>
              <input id="prescriptionFile" className="input" type="file" onChange={(e) => setPrescriptionFile(e.target.files?.[0] ?? null)} />
            </div>

            <button className="btn btn-primary" type="submit">
              Upload prescription
            </button>
          </form>
        </section>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1.5rem" }}>
        <section className="card reveal">
          <header className="card-header">
            <div>
              <h2 className="card-title">Book a vaccine appointment</h2>
              <p className="card-description">Request a time and keep your tracking code for follow-ups.</p>
            </div>
          </header>

          <form className="form" onSubmit={bookAppointment}>
            {appointmentError ? <div className="alert alert-danger">{appointmentError}</div> : null}
            {appointmentSuccess ? <div className="alert">{appointmentSuccess}</div> : null}

            <div className="form-row">
              <label className="label" htmlFor="apptName">
                Full name
              </label>
              <input id="apptName" className="input" value={appointmentForm.name} onChange={(e) => setAppointmentForm((prev) => ({ ...prev, name: e.target.value }))} required />
            </div>

            <div className="form-row">
              <label className="label" htmlFor="apptPhone">
                Phone
              </label>
              <input id="apptPhone" className="input" value={appointmentForm.phone} onChange={(e) => setAppointmentForm((prev) => ({ ...prev, phone: e.target.value }))} required />
            </div>

            <div className="form-row">
              <label className="label" htmlFor="apptType">
                Appointment type
              </label>
              <input id="apptType" className="input" value={appointmentForm.type} onChange={(e) => setAppointmentForm((prev) => ({ ...prev, type: e.target.value }))} />
            </div>

            <div className="form-row">
              <label className="label" htmlFor="apptVaccine">
                Vaccine name (optional)
              </label>
              <input id="apptVaccine" className="input" value={appointmentForm.vaccineName} onChange={(e) => setAppointmentForm((prev) => ({ ...prev, vaccineName: e.target.value }))} />
            </div>

            <div className="form-row">
              <label className="label" htmlFor="apptTime">
                Scheduled time
              </label>
              <input id="apptTime" className="input" type="datetime-local" value={appointmentForm.scheduledTime} onChange={(e) => setAppointmentForm((prev) => ({ ...prev, scheduledTime: e.target.value }))} required />
            </div>

            <button className="btn btn-primary" type="submit">
              Book appointment
            </button>
          </form>
        </section>

        <section className="card reveal">
          <header className="card-header">
            <div>
              <h2 className="card-title">My appointments</h2>
              <p className="card-description">Track appointment status with your code.</p>
            </div>
          </header>

          <div className="grid" style={{ gap: "0.75rem" }}>
            <label className="form-row">
              <span className="label">Tracking code</span>
              <input className="input" value={appointmentTrackingCode} onChange={(e) => setAppointmentTrackingCode(e.target.value)} placeholder="Paste tracking code" />
            </label>
            <button type="button" className="btn btn-primary" onClick={handleAppointmentLookup}>
              View appointments
            </button>

            {appointmentsLoading ? <p className="help">Loading appointments...</p> : null}
            {appointments.length === 0 && !appointmentsLoading ? <p className="help">No appointments found.</p> : null}

            {appointments.length > 0 ? (
              <ul className="list compact">
                {appointments.map((appt) => (
                  <li key={appt.id} className="list-item compact">
                    <div>
                      <p className="list-item-title">{appt.type}</p>
                      <p className="list-item-meta">
                        {formatDate(appt.scheduled_time)} · {appt.status}
                      </p>
                    </div>
                    {appt.vaccine_name ? <span className="badge">{appt.vaccine_name}</span> : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}

