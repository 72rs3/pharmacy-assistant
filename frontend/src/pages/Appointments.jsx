import { useEffect, useMemo, useState } from "react";
import { CalendarDays, RefreshCw } from "lucide-react";
import api from "../api/axios";
import EmptyState from "../components/ui/EmptyState";

const APPOINTMENT_TRACKING_CODE_KEY = "customer_appointment_tracking_code";

const formatDateTime = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const appointmentTypes = [
  { value: "Consultation", label: "Consultation" },
  { value: "Medication Review", label: "Medication review" },
  { value: "Vaccination", label: "Vaccination" },
];

export default function Appointments() {
  const [form, setForm] = useState({
    customer_name: "",
    customer_phone: "",
    type: appointmentTypes[0].value,
    scheduled_time: "",
    vaccine_name: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [trackingCode, setTrackingCode] = useState(() =>
    typeof window !== "undefined" ? localStorage.getItem(APPOINTMENT_TRACKING_CODE_KEY) ?? "" : ""
  );
  const [myAppointments, setMyAppointments] = useState([]);
  const [isLoadingMyAppointments, setIsLoadingMyAppointments] = useState(false);
  const [myAppointmentsError, setMyAppointmentsError] = useState("");

  const shouldShowVaccineName = form.type === "Vaccination";

  const canSubmit = useMemo(() => {
    if (!form.customer_name.trim() || !form.customer_phone.trim() || !form.type.trim() || !form.scheduled_time) return false;
    if (shouldShowVaccineName && !form.vaccine_name.trim()) return false;
    return true;
  }, [form, shouldShowVaccineName]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const submitAppointment = async (event) => {
    event.preventDefault();
    if (!canSubmit || isSubmitting) return;

    setIsSubmitting(true);
    setResult(null);
    try {
      const payload = {
        customer_name: form.customer_name.trim(),
        customer_phone: form.customer_phone.trim(),
        type: form.type.trim(),
        scheduled_time: form.scheduled_time,
        vaccine_name: shouldShowVaccineName ? form.vaccine_name.trim() : null,
      };
      const res = await api.post("/appointments", payload);
      const nextTracking = res.data?.tracking_code ?? "";
      if (typeof window !== "undefined" && nextTracking) {
        localStorage.setItem(APPOINTMENT_TRACKING_CODE_KEY, nextTracking);
      }
      setTrackingCode(nextTracking);
      setResult({
        id: res.data?.id,
        status: res.data?.status,
        scheduled_time: res.data?.scheduled_time,
        type: res.data?.type,
        vaccine_name: res.data?.vaccine_name,
        tracking_code: nextTracking,
      });
      setForm((prev) => ({ ...prev, scheduled_time: "", vaccine_name: "" }));
    } catch (e) {
      setResult({ error: e?.response?.data?.detail ?? "Unable to create appointment. Please try again." });
    } finally {
      setIsSubmitting(false);
    }
  };

  const loadMyAppointments = async () => {
    const safeCode = trackingCode.trim();
    if (!safeCode) return;
    setIsLoadingMyAppointments(true);
    setMyAppointmentsError("");
    try {
      const res = await api.get("/appointments/my", { headers: { "X-Customer-ID": safeCode } });
      setMyAppointments(res.data ?? []);
    } catch (e) {
      setMyAppointments([]);
      setMyAppointmentsError(e?.response?.data?.detail ?? "Unable to load your appointments. Please check the code.");
    } finally {
      setIsLoadingMyAppointments(false);
    }
  };

  useEffect(() => {
    loadMyAppointments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSaveTrackingCode = () => {
    const next = trackingCode.trim();
    setTrackingCode(next);
    if (typeof window !== "undefined") {
      if (next) localStorage.setItem(APPOINTMENT_TRACKING_CODE_KEY, next);
      else localStorage.removeItem(APPOINTMENT_TRACKING_CODE_KEY);
    }
    setMyAppointments([]);
    setMyAppointmentsError("");
  };

  return (
    <div className="space-y-12">
      <section className="text-center space-y-4">
        <h1 className="text-5xl text-gray-900">Book Appointment</h1>
        <p className="text-xl text-gray-600 max-w-3xl mx-auto">
          Reserve an appointment manually. A pharmacist will confirm your request.
        </p>
      </section>

      <section className="grid lg:grid-cols-2 gap-8">
        <div className="bg-white rounded-2xl p-6 md:p-8 shadow-md">
          <h2 className="text-2xl text-gray-900 mb-6">Appointment details</h2>
          <form onSubmit={submitAppointment} className="space-y-4">
            <div>
              <label htmlFor="customer_name" className="block text-sm text-gray-700 mb-2">
                Full name *
              </label>
              <input
                id="customer_name"
                name="customer_name"
                value={form.customer_name}
                onChange={handleChange}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="John Doe"
                required
              />
            </div>

            <div>
              <label htmlFor="customer_phone" className="block text-sm text-gray-700 mb-2">
                Phone number *
              </label>
              <input
                id="customer_phone"
                name="customer_phone"
                value={form.customer_phone}
                onChange={handleChange}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="(555) 123-4567"
                required
              />
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="type" className="block text-sm text-gray-700 mb-2">
                  Appointment type *
                </label>
                <select
                  id="type"
                  name="type"
                  value={form.type}
                  onChange={handleChange}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)] bg-white"
                >
                  {appointmentTypes.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="scheduled_time" className="block text-sm text-gray-700 mb-2">
                  Preferred time *
                </label>
                <input
                  id="scheduled_time"
                  name="scheduled_time"
                  type="datetime-local"
                  value={form.scheduled_time}
                  onChange={handleChange}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                  required
                />
              </div>
            </div>

            {shouldShowVaccineName ? (
              <div>
                <label htmlFor="vaccine_name" className="block text-sm text-gray-700 mb-2">
                  Vaccine name *
                </label>
                <input
                  id="vaccine_name"
                  name="vaccine_name"
                  value={form.vaccine_name}
                  onChange={handleChange}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                  placeholder="Flu, COVID-19, etc."
                  required
                />
              </div>
            ) : null}

            {result?.error ? <div className="text-sm text-red-600">{result.error}</div> : null}

            {result && !result.error ? (
              <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-sm text-green-900 space-y-1">
                <div className="font-semibold">Request submitted</div>
                <div>
                  {result.type} • {formatDateTime(result.scheduled_time)} • {result.status}
                </div>
                <div className="break-all">Tracking code: {result.tracking_code}</div>
              </div>
            ) : null}

            <button
              type="submit"
              disabled={!canSubmit || isSubmitting}
              className="w-full py-3 bg-[var(--brand-accent)] text-white rounded-lg hover:opacity-95 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              {isSubmitting ? "Submitting…" : "Reserve appointment"}
            </button>
          </form>
        </div>

        <div className="bg-white rounded-2xl p-6 md:p-8 shadow-md space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-2xl text-gray-900">My appointments</h2>
              <p className="text-gray-600">
                Enter your tracking code to view your appointment requests.
              </p>
            </div>
            <CalendarDays className="w-8 h-8 text-gray-300" />
          </div>

          <div className="grid md:grid-cols-[1fr_auto] gap-3 items-end">
            <div>
              <label htmlFor="tracking_code" className="block text-sm text-gray-700 mb-2">
                Tracking code
              </label>
              <input
                id="tracking_code"
                value={trackingCode}
                onChange={(event) => setTrackingCode(event.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="Paste tracking code"
              />
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleSaveTrackingCode}
                className="px-5 py-3 bg-[var(--brand-primary)] text-white rounded-lg hover:bg-[var(--brand-primary-600)] transition-colors"
              >
                Save
              </button>
              <button
                type="button"
                onClick={loadMyAppointments}
                disabled={!trackingCode.trim() || isLoadingMyAppointments}
                className="px-5 py-3 border border-gray-300 text-gray-900 rounded-lg hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed transition-colors inline-flex items-center gap-2"
              >
                <RefreshCw className="w-4 h-4" />
                Refresh
              </button>
            </div>
          </div>

          {myAppointmentsError ? <div className="text-sm text-red-600">{myAppointmentsError}</div> : null}

          {trackingCode.trim() ? (
            myAppointments.length ? (
              <div className="space-y-3">
                {myAppointments.map((appt) => (
                  <div key={appt.id} className="bg-gray-50 border border-gray-200 rounded-xl p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-gray-900 font-medium">{appt.type}</div>
                        <div className="text-sm text-gray-600">{formatDateTime(appt.scheduled_time)}</div>
                        {appt.vaccine_name ? <div className="text-xs text-gray-600 mt-1">Vaccine: {appt.vaccine_name}</div> : null}
                      </div>
                      <div className="text-xs text-gray-700">{appt.status}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : isLoadingMyAppointments ? (
              <div className="text-sm text-gray-600">Loading…</div>
            ) : (
              <EmptyState title="No appointments found" description="No appointment requests found for this tracking code." />
            )
          ) : (
            <EmptyState title="No tracking code yet" description="After you reserve an appointment, we will show you a tracking code here." />
          )}
        </div>
      </section>
    </div>
  );
}

