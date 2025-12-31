import { useEffect, useMemo, useState } from "react";
import { CalendarDays, RefreshCw } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import api from "../api/axios";
import EmptyState from "../components/ui/EmptyState";
import { isValidE164 } from "../utils/validation";
import PhoneInput from "../components/ui/PhoneInput";

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
    customer_email: "",
    type: appointmentTypes[0].value,
    scheduled_time: "",
    vaccine_name: "",
  });
  const [slotDate, setSlotDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [availableSlots, setAvailableSlots] = useState([]);
  const [isLoadingSlots, setIsLoadingSlots] = useState(false);
  const [slotsError, setSlotsError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [phoneError, setPhoneError] = useState("");
  const [trackingCode, setTrackingCode] = useState(() =>
    typeof window !== "undefined" ? localStorage.getItem(APPOINTMENT_TRACKING_CODE_KEY) ?? "" : ""
  );
  const [searchParams] = useSearchParams();
  const [myAppointments, setMyAppointments] = useState([]);
  const [isLoadingMyAppointments, setIsLoadingMyAppointments] = useState(false);
  const [myAppointmentsError, setMyAppointmentsError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [pendingAction, setPendingAction] = useState({ appointmentId: null, type: null });
  const [rescheduleTime, setRescheduleTime] = useState("");

  const shouldShowVaccineName = form.type === "Vaccination";

  const canSubmit = useMemo(() => {
    if (!form.customer_name.trim() || !form.customer_phone.trim() || !form.type.trim() || !form.scheduled_time) return false;
    if (!isValidE164(form.customer_phone)) return false;
    if (shouldShowVaccineName && !form.vaccine_name.trim()) return false;
    return true;
  }, [form, shouldShowVaccineName]);

  const openSlots = useMemo(() => availableSlots.filter((slot) => !slot.booked), [availableSlots]);

  const fetchSlots = async (dateValue, onDone) => {
    if (!dateValue) return;
    setIsLoadingSlots(true);
    setSlotsError("");
    try {
      const res = await api.get("/appointments/availability/public", { params: { date: dateValue } });
      const slots = Array.isArray(res.data?.slots) ? res.data.slots : [];
      setAvailableSlots(slots);
      if (onDone) onDone(true);
    } catch (e) {
      setAvailableSlots([]);
      setSlotsError(e?.response?.data?.detail ?? "Unable to load available slots.");
      if (onDone) onDone(false);
    } finally {
      setIsLoadingSlots(false);
    }
  };

  useEffect(() => {
    let active = true;
    fetchSlots(slotDate, (ok) => {
      if (!active) return;
      if (!ok) return;
    });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slotDate]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    if (name === "customer_phone" && phoneError) {
      setPhoneError("");
    }
  };

  const handleSlotDateChange = (event) => {
    const nextDate = event.target.value;
    setSlotDate(nextDate);
    setForm((prev) => ({ ...prev, scheduled_time: "" }));
  };

  const handleSlotSelect = (slot) => {
    setForm((prev) => ({ ...prev, scheduled_time: slot.start }));
  };

  const submitAppointment = async (event) => {
    event.preventDefault();
    if (!isValidE164(form.customer_phone)) {
      setPhoneError("Use E.164 format, e.g. +15551234567.");
      return;
    }
    if (!canSubmit || isSubmitting) return;

    setIsSubmitting(true);
    setResult(null);
    try {
      const payload = {
        customer_name: form.customer_name.trim(),
        customer_phone: form.customer_phone.trim(),
        customer_email: form.customer_email.trim() || null,
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
      setPhoneError("");
    } catch (e) {
      if (e?.response?.status === 409) {
        setResult({ error: "That slot was just taken. Please pick another time." });
        setForm((prev) => ({ ...prev, scheduled_time: "" }));
        fetchSlots(slotDate);
      } else {
        setResult({ error: e?.response?.data?.detail ?? "Unable to create appointment. Please try again." });
      }
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

  const loadMyAppointmentsFor = async (code) => {
    const safeCode = (code ?? "").trim();
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

  const handlePublicUpdate = async (appointmentId, payload) => {
    setActionMessage("");
    setMyAppointmentsError("");
    try {
      const res = await api.patch(`/appointments/${appointmentId}/public`, payload, {
        headers: { "X-Customer-ID": trackingCode.trim() },
      });
      setMyAppointments((prev) => prev.map((item) => (item.id === appointmentId ? res.data : item)));
      setPendingAction({ appointmentId: null, type: null });
      setRescheduleTime("");
      setActionMessage("Your appointment has been updated.");
    } catch (e) {
      setMyAppointmentsError(e?.response?.data?.detail ?? "Unable to update appointment.");
    }
  };

  useEffect(() => {
    loadMyAppointments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const code = searchParams.get("code");
    const appointmentId = searchParams.get("appointment_id");
    const action = searchParams.get("action");
    if (code) {
      setTrackingCode(code);
      if (typeof window !== "undefined") {
        localStorage.setItem(APPOINTMENT_TRACKING_CODE_KEY, code);
      }
      loadMyAppointmentsFor(code);
    }
    if (appointmentId && action) {
      setPendingAction({ appointmentId: Number(appointmentId), type: action });
    }
  }, [searchParams]);

  useEffect(() => {
    if (trackingCode.trim()) {
      loadMyAppointmentsFor(trackingCode);
    }
  }, [trackingCode]);

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
              <PhoneInput
                id="customer_phone"
                name="customer_phone"
                value={form.customer_phone}
                onChange={(next) => handleChange({ target: { name: "customer_phone", value: next } })}
                required
                placeholder="Enter phone number"
              />
              {phoneError ? <div className="text-xs text-red-600 mt-1">{phoneError}</div> : null}
            </div>
            <div>
              <label htmlFor="customer_email" className="block text-sm text-gray-700 mb-2">
                Email for reminders (optional)
              </label>
              <input
                id="customer_email"
                name="customer_email"
                type="email"
                value={form.customer_email}
                onChange={handleChange}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="you@example.com"
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
                <label htmlFor="scheduled_date" className="block text-sm text-gray-700 mb-2">
                  Select date *
                </label>
                <input
                  id="scheduled_date"
                  type="date"
                  value={slotDate}
                  onChange={handleSlotDateChange}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                  required
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="block text-sm text-gray-700 mb-2">Available slots</label>
                {isLoadingSlots ? <span className="text-xs text-gray-500">Loading...</span> : null}
              </div>
              {slotsError ? <div className="text-xs text-red-600 mb-2">{slotsError}</div> : null}
              {openSlots.length === 0 && !isLoadingSlots ? (
                <div className="text-sm text-gray-600">No open slots for this day.</div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {openSlots.map((slot) => {
                    const start = new Date(slot.start);
                    const label = start.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
                    const isSelected = form.scheduled_time === slot.start;
                    return (
                      <button
                        key={slot.start}
                        type="button"
                        onClick={() => handleSlotSelect(slot)}
                        className={`px-3 py-2 rounded-lg border text-sm transition ${
                          isSelected
                            ? "border-blue-600 bg-blue-600 text-white"
                            : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                        }`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              )}
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
                  {result.type} - {formatDateTime(result.scheduled_time)} - {result.status}
                </div>
                <div className="break-all">Tracking code: {result.tracking_code}</div>
              </div>
            ) : null}

            <button
              type="submit"
              disabled={!canSubmit || isSubmitting}
              className="w-full py-3 bg-[var(--brand-accent)] text-white rounded-lg hover:opacity-95 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              {isSubmitting ? "Submitting..." : "Reserve appointment"}
            </button>
          </form>
        </div>

        <div className="bg-white rounded-2xl p-6 md:p-8 shadow-md space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-2xl text-gray-900">My appointments</h2>
              <p className="text-gray-600">Enter your tracking code to view your appointment requests.</p>
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
          {actionMessage ? <div className="text-sm text-emerald-700">{actionMessage}</div> : null}

          {trackingCode.trim() ? (
            myAppointments.length ? (
              <div className="space-y-3">
                {myAppointments.map((appt) => (
                  <div key={appt.id} className="bg-gray-50 border border-gray-200 rounded-xl p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-gray-900 font-medium">{appt.type}</div>
                        <div className="text-sm text-gray-600">{formatDateTime(appt.scheduled_time)}</div>
                        {appt.customer_name ? <div className="text-xs text-gray-600 mt-1">Name: {appt.customer_name}</div> : null}
                        {appt.customer_phone ? <div className="text-xs text-gray-600 mt-1">Phone: {appt.customer_phone}</div> : null}
                        {appt.vaccine_name ? <div className="text-xs text-gray-600 mt-1">Vaccine: {appt.vaccine_name}</div> : null}
                      </div>
                      <div className="text-xs text-gray-700">{appt.status}</div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setPendingAction({ appointmentId: appt.id, type: "reschedule" })}
                        className="px-3 py-1.5 text-xs rounded-full border border-gray-300 text-gray-700 hover:bg-gray-100"
                      >
                        Reschedule
                      </button>
                      <button
                        type="button"
                        onClick={() => setPendingAction({ appointmentId: appt.id, type: "cancel" })}
                        className="px-3 py-1.5 text-xs rounded-full border border-red-200 text-red-700 hover:bg-red-50"
                      >
                        Cancel
                      </button>
                    </div>
                    {pendingAction.appointmentId === appt.id && pendingAction.type === "cancel" ? (
                      <div className="mt-3 flex items-center gap-2 text-xs">
                        <span>Confirm cancellation?</span>
                        <button
                          type="button"
                          onClick={() => handlePublicUpdate(appt.id, { cancel: true })}
                          className="px-3 py-1.5 rounded-full bg-red-600 text-white"
                        >
                          Yes, cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => setPendingAction({ appointmentId: null, type: null })}
                          className="px-3 py-1.5 rounded-full border border-gray-300 text-gray-700"
                        >
                          Keep
                        </button>
                      </div>
                    ) : null}
                    {pendingAction.appointmentId === appt.id && pendingAction.type === "reschedule" ? (
                      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                        <input
                          type="datetime-local"
                          value={rescheduleTime}
                          onChange={(event) => setRescheduleTime(event.target.value)}
                          className="px-3 py-2 rounded-lg border border-gray-300 text-xs"
                        />
                        <button
                          type="button"
                          onClick={() => handlePublicUpdate(appt.id, { scheduled_time: rescheduleTime })}
                          className="px-3 py-1.5 rounded-full bg-[var(--brand-primary)] text-white"
                        >
                          Confirm
                        </button>
                        <button
                          type="button"
                          onClick={() => setPendingAction({ appointmentId: null, type: null })}
                          className="px-3 py-1.5 rounded-full border border-gray-300 text-gray-700"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : isLoadingMyAppointments ? (
              <div className="text-sm text-gray-600">Loading...</div>
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
