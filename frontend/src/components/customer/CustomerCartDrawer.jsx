import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { X } from "lucide-react";
import api from "../../api/axios";
import { useCustomerCart } from "../../context/CustomerCartContext";

const formatMoney = (value) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(value);

export default function CustomerCartDrawer({ isOpen, onClose }) {
  const { items, totalItems, totalPrice, updateItemQuantity, removeItem, clearCart } = useCustomerCart();
  const [form, setForm] = useState({
    customer_name: "",
    customer_phone: "",
    customer_address: "",
    customer_notes: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const hasInvalidItems = useMemo(() => {
    if (items.length === 0) return false;
    return items.some((item) => {
      const id = Number(item.id);
      const qty = Number(item.quantity ?? 0);
      return !Number.isFinite(id) || id <= 0 || qty <= 0;
    });
  }, [items]);

  const canSubmit = useMemo(() => {
    if (!form.customer_name.trim()) return false;
    if (!form.customer_phone.trim()) return false;
    if (!form.customer_address.trim()) return false;
    if (items.length === 0) return false;
    return !hasInvalidItems;
  }, [form, items, hasInvalidItems]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!canSubmit || isSubmitting) return;
    setIsSubmitting(true);
    setResult(null);
    try {
      const payload = {
        customer_name: form.customer_name.trim(),
        customer_phone: form.customer_phone.trim(),
        customer_address: form.customer_address.trim(),
        customer_notes: form.customer_notes.trim() ? form.customer_notes.trim() : null,
        items: items.map((item) => ({
          product_id: Number(item.id),
          quantity: Number(item.quantity ?? 0),
        })),
      };
      const res = await api.post("/orders", payload);
      const trackingCode = res.data?.tracking_code ?? "";
      if (typeof window !== "undefined" && trackingCode) {
        localStorage.setItem("customer_order_tracking_code", trackingCode);
      }
      setResult({
        tracking_code: trackingCode,
        status: res.data?.status,
      });
      clearCart();
      setForm({
        customer_name: "",
        customer_phone: "",
        customer_address: "",
        customer_notes: "",
      });
    } catch (err) {
      setResult({
        error: err?.response?.data?.detail ?? "Unable to place your order. Please try again.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      <button type="button" className="flex-1 bg-black/40" onClick={onClose} aria-label="Close cart overlay" />
      <aside className="w-full max-w-md bg-white h-full shadow-2xl flex flex-col">
        <div className="px-6 py-5 border-b flex items-center justify-between">
          <div>
            <div className="text-lg text-gray-900">Your cart</div>
            <div className="text-sm text-gray-500">{totalItems} items</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-full hover:bg-gray-100 transition-colors"
            aria-label="Close cart"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {items.length === 0 ? (
            <div className="text-sm text-gray-500">Your cart is empty.</div>
          ) : (
            items.map((item) => (
              <div key={item.id} className="flex gap-4 items-center border rounded-xl p-3">
                <div className="w-16 h-16 rounded-lg bg-gray-100 overflow-hidden flex-shrink-0">
                  {item.image ? (
                    <img src={item.image} alt={item.name} className="w-full h-full object-cover" />
                  ) : null}
                </div>
                <div className="flex-1">
                  <div className="text-gray-900 text-sm font-medium">{item.name}</div>
                  <div className="text-xs text-gray-500">{formatMoney(Number(item.price ?? 0))}</div>
                  <div className="mt-2 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => updateItemQuantity(item.id, Number(item.quantity ?? 0) - 1)}
                      className="w-8 h-8 rounded-full border border-gray-300 text-gray-700 hover:bg-gray-100"
                      aria-label="Decrease quantity"
                    >
                      -
                    </button>
                    <span className="text-sm text-gray-700 w-6 text-center">{item.quantity}</span>
                    <button
                      type="button"
                      onClick={() => updateItemQuantity(item.id, Number(item.quantity ?? 0) + 1)}
                      className="w-8 h-8 rounded-full border border-gray-300 text-gray-700 hover:bg-gray-100"
                      aria-label="Increase quantity"
                    >
                      +
                    </button>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => removeItem(item.id)}
                  className="text-xs text-red-600 hover:text-red-700"
                >
                  Remove
                </button>
              </div>
            ))
          )}
        </div>

        <div className="border-t p-6 space-y-4">
          <div className="flex items-center justify-between text-sm text-gray-700">
            <span>Total</span>
            <span className="font-semibold text-gray-900">{formatMoney(totalPrice)}</span>
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Cash on delivery. A pharmacist will confirm your order.
          </div>
          {hasInvalidItems ? (
            <div className="text-sm text-red-600">
              Some items cannot be ordered online. Please remove them and try again.
            </div>
          ) : null}
          {result?.error ? <div className="text-sm text-red-600">{result.error}</div> : null}
          {result?.tracking_code ? (
            <div className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg p-3">
              <div>
                Order placed. Tracking code: <span className="font-semibold break-all">{result.tracking_code}</span>
              </div>
              <div className="mt-2">
                <Link to="/orders" className="underline text-green-800 hover:text-green-900">
                  Track this order
                </Link>
              </div>
            </div>
          ) : null}
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label htmlFor="customer_name" className="block text-xs text-gray-600 mb-1">
                Full name *
              </label>
              <input
                id="customer_name"
                name="customer_name"
                value={form.customer_name}
                onChange={handleChange}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="John Doe"
                required
              />
            </div>
            <div>
              <label htmlFor="customer_phone" className="block text-xs text-gray-600 mb-1">
                Phone number *
              </label>
              <input
                id="customer_phone"
                name="customer_phone"
                value={form.customer_phone}
                onChange={handleChange}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="(555) 123-4567"
                required
              />
            </div>
            <div>
              <label htmlFor="customer_address" className="block text-xs text-gray-600 mb-1">
                Delivery address *
              </label>
              <textarea
                id="customer_address"
                name="customer_address"
                value={form.customer_address}
                onChange={handleChange}
                rows="2"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="Street, city, postal code"
                required
              />
            </div>
            <div>
              <label htmlFor="customer_notes" className="block text-xs text-gray-600 mb-1">
                Delivery notes (optional)
              </label>
              <textarea
                id="customer_notes"
                name="customer_notes"
                value={form.customer_notes}
                onChange={handleChange}
                rows="2"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="Gate code, preferred time, etc."
              />
            </div>
            <button
              type="submit"
              disabled={!canSubmit || isSubmitting}
              className="w-full py-2.5 bg-[var(--brand-accent)] text-white rounded-lg hover:opacity-95 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              {isSubmitting ? "Placing order..." : "Place COD order"}
            </button>
          </form>
          <button
            type="button"
            onClick={clearCart}
            disabled={items.length === 0}
            className="w-full py-2.5 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            Clear cart
          </button>
        </div>
      </aside>
    </div>
  );
}
