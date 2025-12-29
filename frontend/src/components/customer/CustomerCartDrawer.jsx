import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { BadgeCheck, X } from "lucide-react";
import api from "../../api/axios";
import { useCustomerCart } from "../../context/CustomerCartContext";
import { useTenant } from "../../context/TenantContext";
import { isValidE164 } from "../../utils/validation";
import PhoneInput from "../ui/PhoneInput";

const formatMoney = (value) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(value);
const CUSTOMER_TRACKING_KEY = "customer_order_tracking_code";

const getOrCreateCustomerTrackingCode = () => {
  if (typeof window === "undefined") return "";
  const existing = (localStorage.getItem(CUSTOMER_TRACKING_KEY) ?? "").trim();
  if (existing) return existing;
  const generated = `cust_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  localStorage.setItem(CUSTOMER_TRACKING_KEY, generated);
  return generated;
};

export default function CustomerCartDrawer({ isOpen, onClose }) {
  const { items, totalItems, totalPrice, updateItemQuantity, removeItem, clearCart } = useCustomerCart();
  const { pharmacy } = useTenant() ?? {};
  const theme = String(pharmacy?.theme_preset ?? "classic").toLowerCase();
  const isGlass = theme === "glass";
  const isNeumorph = theme === "neumorph";
  const isMinimal = theme === "minimal";
  const [form, setForm] = useState({
    customer_name: "",
    customer_phone: "",
    customer_address: "",
    customer_notes: "",
  });
  const [phoneError, setPhoneError] = useState("");
  const [showCheckout, setShowCheckout] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (items.length === 0) {
      setShowCheckout(false);
      return;
    }
    if (items.length > 3) {
      setShowCheckout(false);
    }
  }, [items.length]);

  const hasInvalidItems = useMemo(() => {
    if (items.length === 0) return false;
    return items.some((item) => {
      const resolvedId = String(item.item_type ?? "").toLowerCase() === "medicine" ? item.item_id : item.item_id ?? item.id;
      const id = Number(resolvedId);
      const qty = Number(item.quantity ?? 0);
      return !Number.isFinite(id) || id <= 0 || qty <= 0;
    });
  }, [items]);

  const canSubmit = useMemo(() => {
    if (!form.customer_name.trim()) return false;
    if (!form.customer_phone.trim()) return false;
    if (!isValidE164(form.customer_phone)) return false;
    if (!form.customer_address.trim()) return false;
    if (items.length === 0) return false;
    return !hasInvalidItems;
  }, [form, items, hasInvalidItems]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    if (name === "customer_phone" && phoneError) {
      setPhoneError("");
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!isValidE164(form.customer_phone)) {
      setPhoneError("Use E.164 format, e.g. +15551234567.");
      return;
    }
    if (!canSubmit || isSubmitting) return;
    setIsSubmitting(true);
    setResult(null);
    try {
      let draftPrescriptionTokens = [];
      if (typeof window !== "undefined") {
        try {
          const raw = localStorage.getItem("customer_prescription_draft_tokens");
          const parsed = raw ? JSON.parse(raw) : [];
          draftPrescriptionTokens = Array.isArray(parsed) ? parsed.filter(Boolean) : [];
        } catch {
          draftPrescriptionTokens = [];
        }
      }
      const payload = {
        customer_name: form.customer_name.trim(),
        customer_phone: form.customer_phone.trim(),
        customer_address: form.customer_address.trim(),
        customer_notes: form.customer_notes.trim() ? form.customer_notes.trim() : null,
        items: items.map((item) => ({
          ...(String(item.item_type ?? "").toLowerCase() === "medicine"
            ? { medicine_id: Number(item.item_id) }
            : { product_id: Number(item.item_id ?? item.id) }),
          quantity: Number(item.quantity ?? 0),
        })),
        draft_prescription_tokens: draftPrescriptionTokens.length > 0 ? draftPrescriptionTokens : null,
      };
      const customerTrackingCode = getOrCreateCustomerTrackingCode();
      const res = await api.post("/orders", payload, {
        headers: customerTrackingCode ? { "X-Customer-ID": customerTrackingCode } : {},
      });
      const trackingCodeFromServer = res.data?.tracking_code ?? "";
      if (typeof window !== "undefined" && trackingCodeFromServer) {
        localStorage.setItem("customer_order_tracking_code", trackingCodeFromServer);
      }
      setResult({
        tracking_code: trackingCodeFromServer,
        status: res.data?.status,
      });
      clearCart();
      setForm({
        customer_name: "",
        customer_phone: "",
        customer_address: "",
        customer_notes: "",
      });
      setPhoneError("");
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const msg =
        Array.isArray(detail) ? detail.map((d) => d?.msg ?? String(d)).filter(Boolean).join(" ") : detail ?? null;
      setResult({
        error: msg ?? "Unable to place your order. Please try again.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCopyTrackingCode = async (code) => {
    if (!code) return;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(code);
      } else {
        const tempInput = document.createElement("input");
        tempInput.value = code;
        document.body.appendChild(tempInput);
        tempInput.select();
        document.execCommand("copy");
        document.body.removeChild(tempInput);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      <button type="button" className="flex-1 bg-black/40" onClick={onClose} aria-label="Close cart overlay" />
      <aside
        className={`w-full max-w-md h-full flex flex-col ${
          isNeumorph ? "bg-slate-100 border-l border-slate-200" : "bg-white/90 border-l border-white/70"
        } ${isGlass ? "backdrop-blur-xl" : ""} shadow-2xl`}
      >
        <div
          className={`px-6 py-5 border-b ${
            isNeumorph ? "border-slate-200 bg-slate-100" : "border-slate-200/70 bg-white/80"
          } ${isGlass ? "backdrop-blur" : ""} flex items-center justify-between`}
        >
          <div>
            <div className="text-lg text-gray-900 font-semibold">Your cart</div>
            <div className="text-xs text-gray-500 uppercase tracking-wide">{totalItems} items</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-full hover:bg-slate-100 transition-colors"
            aria-label="Close cart"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          <div className="flex items-center justify-between text-xs uppercase tracking-wide text-gray-500">
            <span>Items</span>
            {items.length > 0 ? (
              <button
                type="button"
                onClick={() => setShowCheckout((prev) => !prev)}
                className="text-[var(--brand-accent)] font-semibold hover:opacity-80"
              >
                {showCheckout ? "Hide checkout" : "Show checkout"}
              </button>
            ) : null}
          </div>
          {items.length === 0 ? (
            <div className="text-sm text-gray-500">Your cart is empty.</div>
          ) : (
            items.map((item) => {
              const price = Number(item.price ?? 0);
              const qty = Number(item.quantity ?? 0);
              const lineTotal = price * qty;
              const itemCardClass = isGlass
                ? "border border-white/70 bg-white/70 backdrop-blur shadow-lg"
                : isNeumorph
                  ? "border border-slate-200 bg-slate-100 shadow-[inset_-10px_-10px_18px_rgba(255,255,255,0.85),inset_10px_10px_18px_rgba(15,23,42,0.12)]"
                  : isMinimal
                    ? "border border-slate-200 bg-white shadow-none"
                    : "border border-slate-200/70 bg-white/80 shadow-sm";
              return (
                <div key={item.id} className={`flex gap-4 items-center rounded-2xl p-3 ${itemCardClass}`}>
                  <div className="w-16 h-16 rounded-xl bg-gray-100 overflow-hidden flex-shrink-0 border border-slate-100">
                    {item.image ? (
                      <img src={item.image} alt={item.name} className="w-full h-full object-cover" />
                    ) : null}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-gray-900 text-sm font-medium truncate">{item.name}</div>
                    <div className="text-xs text-gray-500">{formatMoney(price)}</div>
                    <div className="mt-3 flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => updateItemQuantity(item.id, qty - 1)}
                        className="w-8 h-8 rounded-full border border-slate-200 text-gray-700 hover:bg-slate-100"
                        aria-label="Decrease quantity"
                      >
                        -
                      </button>
                      <span className="text-sm text-gray-700 w-6 text-center">{qty}</span>
                      <button
                        type="button"
                        onClick={() => updateItemQuantity(item.id, qty + 1)}
                        className="w-8 h-8 rounded-full border border-slate-200 text-gray-700 hover:bg-slate-100"
                        aria-label="Increase quantity"
                      >
                        +
                      </button>
                    </div>
                  </div>
                  <div className="text-right space-y-2">
                    <div className="text-sm font-semibold text-gray-900">{formatMoney(lineTotal)}</div>
                    <button
                      type="button"
                      onClick={() => removeItem(item.id)}
                      className="text-xs text-red-600 hover:text-red-700"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              );
            })
          )}
          {items.length > 0 ? (
            <div className="rounded-2xl border border-slate-200/70 bg-white/90 p-4 shadow-sm">
              <div className="flex items-center justify-between text-sm text-gray-600">
                <span>Order total</span>
                <span className="text-lg font-semibold text-gray-900">{formatMoney(totalPrice)}</span>
              </div>
            </div>
          ) : null}
          {!showCheckout && items.length > 0 ? (
            <button
              type="button"
              onClick={() => setShowCheckout(true)}
              className="w-full py-3 bg-[var(--brand-accent)] text-white rounded-xl hover:opacity-95 transition-colors font-semibold"
            >
              Continue to checkout
            </button>
          ) : null}
        </div>

        {showCheckout ? (
          <div
            className={`border-t p-6 space-y-4 ${
              isNeumorph ? "border-slate-200 bg-slate-100" : "border-slate-200/70 bg-white/80"
            } ${isGlass ? "backdrop-blur" : ""}`}
          >
            <div className="rounded-2xl border border-amber-200/70 bg-amber-50 px-4 py-3 text-xs text-amber-900 flex items-start gap-2">
              <BadgeCheck className="w-4 h-4 text-amber-700 mt-0.5" />
              <div>
                <div className="font-semibold">Cash on delivery</div>
                <div className="text-amber-800">A pharmacist will confirm your order by phone.</div>
              </div>
            </div>
            {hasInvalidItems ? (
              <div className="text-sm text-red-600">
                Some items cannot be ordered online. Please remove them and try again.
              </div>
            ) : null}
            {result?.error ? <div className="text-sm text-red-600">{result.error}</div> : null}
            {result?.tracking_code ? (
              <div className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg p-3">
                <div className="text-xs text-green-800 uppercase tracking-wide">Tracking code</div>
                <div className="mt-2 flex items-center gap-2">
                  <code className="flex-1 px-3 py-2 rounded-lg border border-green-200 bg-white text-green-900 break-all">
                    {result.tracking_code}
                  </code>
                  <button
                    type="button"
                    onClick={() => handleCopyTrackingCode(result.tracking_code)}
                    className="px-3 py-2 rounded-lg border border-green-200 text-green-800 hover:bg-green-100 text-xs font-semibold"
                  >
                    {copied ? "Copied" : "Copy"}
                  </button>
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
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)] bg-white/90"
                  placeholder="John Doe"
                  required
                />
              </div>
            <div>
              <label htmlFor="customer_phone" className="block text-xs text-gray-600 mb-1">
                Phone number *
              </label>
              <PhoneInput
                id="customer_phone"
                name="customer_phone"
                value={form.customer_phone}
                onChange={(next) => handleChange({ target: { name: "customer_phone", value: next } })}
                required
                className="bg-white/90"
                placeholder="Enter phone number"
              />
              {phoneError ? <div className="text-xs text-red-600 mt-1">{phoneError}</div> : null}
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
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)] bg-white/90"
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
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)] bg-white/90"
                  placeholder="Gate code, preferred time, etc."
                />
              </div>
              <button
                type="submit"
                disabled={!canSubmit || isSubmitting}
                className="w-full py-3 bg-[var(--brand-accent)] text-white rounded-xl hover:opacity-95 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors font-semibold"
              >
                {isSubmitting ? "Placing order..." : "Place COD order"}
              </button>
            </form>
            <button
              type="button"
              onClick={clearCart}
              disabled={items.length === 0}
              className="w-full py-2.5 border border-slate-200 rounded-xl text-gray-700 hover:bg-slate-50 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              Clear cart
            </button>
          </div>
        ) : null}
      </aside>
    </div>
  );
}
