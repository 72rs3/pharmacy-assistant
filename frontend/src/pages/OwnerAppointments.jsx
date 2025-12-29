import { useEffect, useMemo, useState } from "react";
import { Copy, Phone, RefreshCw } from "lucide-react";
import api from "../api/axios";

const formatDate = (value) => {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const toLocalInputValue = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
};

const statusPill = (status) => {
  const normalized = String(status ?? "").toUpperCase();
  if (normalized === "CONFIRMED") return "bg-emerald-100 text-emerald-800 border-emerald-200";
  if (normalized === "COMPLETED") return "bg-blue-100 text-blue-800 border-blue-200";
  if (normalized === "CANCELLED") return "bg-red-100 text-red-800 border-red-200";
  return "bg-slate-100 text-slate-800 border-slate-200";
};

const STATUS_OPTIONS = ["PENDING", "CONFIRMED", "CANCELLED", "COMPLETED"];
const SORT_OPTIONS = [
  { value: "queue", label: "Queue (Pending first)" },
  { value: "schedule", label: "Schedule (Soonest first)" },
  { value: "recent", label: "Recently created" },
];
const TAB_OPTIONS = [
  { id: "today", label: "Today" },
  { id: "upcoming", label: "Upcoming" },
  { id: "past", label: "Past" },
  { id: "cancelled", label: "Cancelled" },
];
const PAGE_SIZE = 20;
const WEEK_DAYS = [
  { key: "mon", label: "Mon" },
  { key: "tue", label: "Tue" },
  { key: "wed", label: "Wed" },
  { key: "thu", label: "Thu" },
  { key: "fri", label: "Fri" },
  { key: "sat", label: "Sat" },
  { key: "sun", label: "Sun" },
];

const defaultWeeklyHours = () => ({
  mon: [{ start: "09:00", end: "18:00" }],
  tue: [{ start: "09:00", end: "18:00" }],
  wed: [{ start: "09:00", end: "18:00" }],
  thu: [{ start: "09:00", end: "18:00" }],
  fri: [{ start: "09:00", end: "18:00" }],
  sat: [{ start: "09:00", end: "14:00" }],
  sun: [],
});

const parseWeeklyHours = (raw) => {
  if (!raw) return defaultWeeklyHours();
  try {
    const parsed = JSON.parse(raw);
    return Object.keys(parsed).length ? parsed : defaultWeeklyHours();
  } catch {
    return defaultWeeklyHours();
  }
};

const addDays = (date, days) => {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
};

const formatShortDay = (date) => {
  return date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
};

export default function OwnerAppointments() {
  const [appointments, setAppointments] = useState([]);
  const [statusById, setStatusById] = useState({});
  const [timeById, setTimeById] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [isSavingId, setIsSavingId] = useState(null);
  const [activeTab, setActiveTab] = useState("today");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [sortMode, setSortMode] = useState("queue");
  const [typeFilter, setTypeFilter] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [pageIndex, setPageIndex] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [calendarDate, setCalendarDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [availability, setAvailability] = useState([]);
  const [availabilityError, setAvailabilityError] = useState("");
  const [isLoadingAvailability, setIsLoadingAvailability] = useState(false);
  const [nextUp, setNextUp] = useState([]);
  const [isLoadingNextUp, setIsLoadingNextUp] = useState(false);
  const [auditById, setAuditById] = useState({});
  const [auditOpenById, setAuditOpenById] = useState({});
  const [settings, setSettings] = useState(null);
  const [settingsDraft, setSettingsDraft] = useState({
    slot_minutes: 15,
    buffer_minutes: 0,
    timezone: "UTC",
    weekly_hours: defaultWeeklyHours(),
    no_show_minutes: 30,
    locale: "en",
  });
  const [settingsError, setSettingsError] = useState("");
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [weekStart, setWeekStart] = useState(() => {
    const now = new Date();
    const day = now.getDay();
    const diff = (day + 6) % 7;
    now.setDate(now.getDate() - diff);
    return now.toISOString().slice(0, 10);
  });
  const [weekSlots, setWeekSlots] = useState([]);
  const [weekAppointments, setWeekAppointments] = useState([]);
  const [isLoadingWeek, setIsLoadingWeek] = useState(false);

  useEffect(() => {
    const handle = setTimeout(() => setSearchQuery(searchDraft.trim()), 350);
    return () => clearTimeout(handle);
  }, [searchDraft]);

  useEffect(() => {
    setPageIndex(0);
  }, [activeTab, statusFilter, sortMode, typeFilter, searchQuery]);

  const loadAppointments = async () => {
    setIsLoading(true);
    setError("");
    setActionError("");
    try {
      const now = new Date();
      const startOfDay = new Date(now);
      startOfDay.setHours(0, 0, 0, 0);
      const endOfDay = new Date(now);
      endOfDay.setHours(23, 59, 59, 999);

      let fromParam;
      let toParam;
      let statusParam = statusFilter !== "ALL" ? statusFilter : undefined;

      if (activeTab === "today") {
        fromParam = startOfDay.toISOString();
        toParam = endOfDay.toISOString();
      } else if (activeTab === "upcoming") {
        fromParam = now.toISOString();
      } else if (activeTab === "past") {
        toParam = now.toISOString();
      } else if (activeTab === "cancelled") {
        statusParam = "CANCELLED";
      }

      const params = {
        status: statusParam,
        q: searchQuery || undefined,
        type: typeFilter.trim() || undefined,
        sort: sortMode || undefined,
        limit: PAGE_SIZE,
        offset: pageIndex * PAGE_SIZE,
        from: fromParam,
        to: toParam,
      };
      const res = await api.get("/appointments/owner", { params });
      const data = Array.isArray(res.data) ? res.data : [];
      const headerTotal = Number(res.headers?.["x-total-count"]);
      setTotalCount(Number.isFinite(headerTotal) ? headerTotal : data.length);
      setAppointments(data);
      setStatusById(
        data.reduce((acc, appt) => {
          acc[appt.id] = appt.status;
          return acc;
        }, {})
      );
      setTimeById(
        data.reduce((acc, appt) => {
          acc[appt.id] = toLocalInputValue(appt.scheduled_time);
          return acc;
        }, {})
      );
    } catch (e) {
      setAppointments([]);
      setError(e?.response?.data?.detail ?? "Failed to load appointments");
    } finally {
      setIsLoading(false);
    }
  };

  const loadSettings = async () => {
    setSettingsError("");
    try {
      const res = await api.get("/appointments/settings");
      const data = res.data ?? null;
      setSettings(data);
      setSettingsDraft({
        slot_minutes: Number(data?.slot_minutes ?? 15),
        buffer_minutes: Number(data?.buffer_minutes ?? 0),
        timezone: data?.timezone ?? "UTC",
        weekly_hours: parseWeeklyHours(data?.weekly_hours_json),
        no_show_minutes: Number(data?.no_show_minutes ?? 30),
        locale: data?.locale ?? "en",
      });
    } catch (e) {
      setSettingsError(e?.response?.data?.detail ?? "Failed to load schedule settings");
    }
  };

  const saveSettings = async () => {
    setSettingsError("");
    setIsSavingSettings(true);
    try {
      const payload = {
        slot_minutes: Number(settingsDraft.slot_minutes) || 15,
        buffer_minutes: Number(settingsDraft.buffer_minutes) || 0,
        timezone: settingsDraft.timezone || "UTC",
        weekly_hours_json: JSON.stringify(settingsDraft.weekly_hours ?? defaultWeeklyHours()),
        no_show_minutes: Number(settingsDraft.no_show_minutes) || 30,
        locale: settingsDraft.locale || "en",
      };
      const res = await api.put("/appointments/settings", payload);
      setSettings(res.data ?? null);
    } catch (e) {
      setSettingsError(e?.response?.data?.detail ?? "Failed to save schedule settings");
    } finally {
      setIsSavingSettings(false);
    }
  };

  const loadAvailability = async () => {
    if (!calendarDate) return;
    setIsLoadingAvailability(true);
    setAvailabilityError("");
    try {
      const res = await api.get("/appointments/availability", { params: { date: calendarDate } });
      const slots = Array.isArray(res.data?.slots) ? res.data.slots : [];
      setAvailability(slots);
    } catch (e) {
      setAvailability([]);
      setAvailabilityError(e?.response?.data?.detail ?? "Failed to load availability");
    } finally {
      setIsLoadingAvailability(false);
    }
  };

  const loadNextUp = async () => {
    setIsLoadingNextUp(true);
    try {
      const res = await api.get("/appointments/owner", {
        params: {
          sort: "schedule",
          from: new Date().toISOString(),
          limit: 5,
          offset: 0,
        },
      });
      setNextUp(Array.isArray(res.data) ? res.data : []);
    } catch {
      setNextUp([]);
    } finally {
      setIsLoadingNextUp(false);
    }
  };

  const loadAudits = async (appointmentId) => {
    try {
      const res = await api.get(`/appointments/${appointmentId}/audits`);
      setAuditById((prev) => ({ ...prev, [appointmentId]: Array.isArray(res.data) ? res.data : [] }));
    } catch {
      setAuditById((prev) => ({ ...prev, [appointmentId]: [] }));
    }
  };

  const loadWeekView = async () => {
    setIsLoadingWeek(true);
    try {
      const start = new Date(weekStart);
      const days = Array.from({ length: 7 }, (_, idx) => addDays(start, idx));
      const slotsResults = await Promise.all(
        days.map((day) =>
          api.get("/appointments/availability", { params: { date: day.toISOString().slice(0, 10) } })
        )
      );
      const nextSlots = slotsResults.map((res, idx) => ({
        date: days[idx],
        slots: Array.isArray(res.data?.slots) ? res.data.slots : [],
      }));
      setWeekSlots(nextSlots);

      const from = days[0].toISOString();
      const to = addDays(days[6], 1).toISOString();
      const apptRes = await api.get("/appointments/owner", {
        params: { from, to, limit: 300, offset: 0, sort: "schedule" },
      });
      setWeekAppointments(Array.isArray(apptRes.data) ? apptRes.data : []);
    } catch {
      setWeekSlots([]);
      setWeekAppointments([]);
    } finally {
      setIsLoadingWeek(false);
    }
  };

  useEffect(() => {
    loadAppointments();
  }, [activeTab, statusFilter, sortMode, typeFilter, searchQuery, pageIndex]);

  useEffect(() => {
    loadSettings();
  }, []);

  useEffect(() => {
    loadAvailability();
  }, [calendarDate]);

  useEffect(() => {
    loadNextUp();
  }, []);

  useEffect(() => {
    loadWeekView();
  }, [weekStart]);

  const updateAppointment = async (appointmentId) => {
    setActionError("");
    setIsSavingId(appointmentId);
    try {
      const res = await api.patch(`/appointments/${appointmentId}`, {
        status: statusById[appointmentId],
        scheduled_time: timeById[appointmentId] || null,
      });
      setAppointments((prev) => prev.map((item) => (item.id === appointmentId ? res.data : item)));
    } catch (e) {
      setActionError(e?.response?.data?.detail ?? "Failed to update appointment");
    } finally {
      setIsSavingId(null);
    }
  };

  const rescheduleAppointment = async (appointmentId, scheduledTime) => {
    if (!scheduledTime) return;
    setActionError("");
    setIsSavingId(appointmentId);
    try {
      const res = await api.patch(`/appointments/${appointmentId}`, {
        scheduled_time: scheduledTime,
      });
      setAppointments((prev) => prev.map((item) => (item.id === appointmentId ? res.data : item)));
      setWeekAppointments((prev) => prev.map((item) => (item.id === appointmentId ? res.data : item)));
    } catch (e) {
      setActionError(e?.response?.data?.detail ?? "Failed to reschedule appointment");
    } finally {
      setIsSavingId(null);
    }
  };

  const markNoShow = async (appointmentId) => {
    setActionError("");
    setIsSavingId(appointmentId);
    try {
      const res = await api.post(`/appointments/${appointmentId}/no-show`);
      setAppointments((prev) => prev.map((item) => (item.id === appointmentId ? res.data : item)));
    } catch (e) {
      setActionError(e?.response?.data?.detail ?? "Failed to mark no-show");
    } finally {
      setIsSavingId(null);
    }
  };

  const counts = useMemo(() => {
    const normalized = (value) => String(value ?? "").toUpperCase();
    return appointments.reduce(
      (acc, appt) => {
        const s = normalized(appt.status);
        acc.total += 1;
        if (s === "PENDING") acc.pending += 1;
        if (s === "CONFIRMED") acc.confirmed += 1;
        if (s === "COMPLETED") acc.completed += 1;
        if (s === "CANCELLED") acc.cancelled += 1;
        return acc;
      },
      { total: 0, pending: 0, confirmed: 0, completed: 0, cancelled: 0 }
    );
  }, [appointments]);

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const pageStart = totalCount === 0 ? 0 : pageIndex * PAGE_SIZE + 1;
  const pageEnd = Math.min(totalCount, (pageIndex + 1) * PAGE_SIZE);

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-[0_24px_60px_rgba(15,23,42,0.12)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 flex items-center justify-between gap-4 border-b border-slate-200">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">Appointments</h1>
            <p className="text-sm text-slate-500 mt-1">Confirm bookings and keep the schedule updated.</p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={loadAppointments}
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

          <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
            <div className="space-y-4">
          <div className="flex flex-wrap gap-2 items-center">
            <input
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="Search name, phone, type…"
              className="flex-1 min-w-[220px] px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm focus:outline-none focus:ring-4 focus:ring-blue-100"
            />
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm focus:outline-none focus:ring-4 focus:ring-blue-100"
              title="Filter status"
            >
              <option value="ALL">Filter status</option>
              {STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <select
              value={sortMode}
              onChange={(event) => setSortMode(event.target.value)}
              className="px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm focus:outline-none focus:ring-4 focus:ring-blue-100"
              title="Sort"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <input
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value)}
              placeholder="Filter by type…"
              className="min-w-[180px] px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm focus:outline-none focus:ring-4 focus:ring-blue-100"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            {TAB_OPTIONS.map((tab) => {
              const isActive = tab.id === activeTab;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => {
                    setActiveTab(tab.id);
                    if (tab.id === "cancelled") {
                      setStatusFilter("CANCELLED");
                    } else if (statusFilter === "CANCELLED") {
                      setStatusFilter("ALL");
                    }
                  }}
                  className={`px-3 py-1.5 rounded-full border text-xs transition ${
                    isActive
                      ? "border-blue-600 bg-blue-50 text-blue-700"
                      : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          <div className="flex flex-wrap gap-2">
            <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
              Total: {counts.total}
            </span>
            <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
              Pending: {counts.pending}
            </span>
            <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
              Confirmed: {counts.confirmed}
            </span>
            <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
              Completed: {counts.completed}
            </span>
            <span className="inline-flex items-center px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs text-slate-700">
              Cancelled: {counts.cancelled}
            </span>
            <span className="ml-auto text-xs text-slate-500">
              Showing {pageStart}-{pageEnd} of {totalCount}
            </span>
          </div>

          {appointments.length === 0 && !isLoading ? (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-slate-600 text-sm">
              No appointments booked yet.
            </div>
          ) : (
            <div className="space-y-4">
              {appointments.map((appt) => (
                <section key={appt.id} className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                  <div className="px-6 py-5 border-b border-slate-200 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-3">
                        <h2 className="text-xl font-semibold text-slate-900">Appointment #{appt.id}</h2>
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs ${statusPill(appt.status)}`}>
                          {appt.status}
                        </span>
                        {appt.no_show ? (
                          <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-red-200 bg-red-50 text-xs text-red-700">
                            No-show
                          </span>
                        ) : null}
                      </div>
                      <div className="text-sm text-slate-500 mt-1">
                        {appt.type ?? "Appointment"} - {formatDate(appt.scheduled_time)}
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-slate-800">
                        Customer: {appt.customer_name ?? "--"}
                      </span>
                      <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-slate-800">
                        Phone: {appt.customer_phone ?? "--"}
                      </span>
                      {appt.customer_email ? (
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-slate-800">
                          Email: {appt.customer_email}
                        </span>
                      ) : null}
                      {appt.customer_phone ? (
                        <a
                          href={`tel:${appt.customer_phone}`}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                          title="Call customer"
                        >
                          <Phone className="w-3.5 h-3.5" />
                          Call
                        </a>
                      ) : null}
                      {appt.customer_phone ? (
                        <button
                          type="button"
                          onClick={() => navigator.clipboard?.writeText(appt.customer_phone)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                          title="Copy phone"
                        >
                          <Copy className="w-3.5 h-3.5" />
                          Copy
                        </button>
                      ) : null}
                      {appt.vaccine_name ? (
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-slate-800">
                          Vaccine: {appt.vaccine_name}
                        </span>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => {
                          setAuditOpenById((prev) => ({ ...prev, [appt.id]: !prev[appt.id] }));
                          if (!auditById[appt.id]) {
                            loadAudits(appt.id);
                          }
                        }}
                        className="inline-flex items-center px-2.5 py-1 rounded-full border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                      >
                        History
                      </button>
                    </div>
                  </div>

                  <div className="px-6 py-5 grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor={`appt-status-${appt.id}`}>
                        Status
                      </label>
                      <select
                        id={`appt-status-${appt.id}`}
                        value={statusById[appt.id] ?? appt.status}
                        onChange={(event) => setStatusById((prev) => ({ ...prev, [appt.id]: event.target.value }))}
                        className="w-full md:w-64 px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100"
                      >
                        {STATUS_OPTIONS.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor={`appt-time-${appt.id}`}>
                        Reschedule time
                      </label>
                      <input
                        id={`appt-time-${appt.id}`}
                        type="datetime-local"
                        value={timeById[appt.id] ?? ""}
                        onChange={(event) => setTimeById((prev) => ({ ...prev, [appt.id]: event.target.value }))}
                        className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100"
                      />
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => updateAppointment(appt.id)}
                        disabled={isSavingId === appt.id}
                        className="px-5 py-3 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                      >
                        {isSavingId === appt.id ? "Updating..." : "Update"}
                      </button>
                      {!appt.no_show && ["PENDING", "CONFIRMED"].includes(String(appt.status ?? "").toUpperCase()) ? (
                        <button
                          type="button"
                          onClick={() => markNoShow(appt.id)}
                          disabled={isSavingId === appt.id}
                          className="px-4 py-3 rounded-xl border border-red-200 text-red-700 hover:bg-red-50 disabled:opacity-60"
                        >
                          Mark no-show
                        </button>
                      ) : null}
                    </div>
                  </div>
                  {auditOpenById[appt.id] ? (
                    <div className="px-6 pb-5">
                      <div className="text-xs text-slate-500 mb-2">Audit trail</div>
                      {auditById[appt.id] && auditById[appt.id].length ? (
                        <div className="space-y-2">
                          {auditById[appt.id].map((entry) => (
                            <div key={entry.id} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
                              <div className="font-medium">{entry.action}</div>
                              <div className="text-[11px] text-slate-500">{formatDate(entry.created_at)}</div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-xs text-slate-500">No audit history yet.</div>
                      )}
                    </div>
                  ) : null}
                </section>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between pt-2">
            <button
              type="button"
              onClick={() => setPageIndex((prev) => Math.max(0, prev - 1))}
              disabled={pageIndex === 0}
              className="px-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-700 disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-xs text-slate-500">
              Page {pageIndex + 1} of {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPageIndex((prev) => Math.min(totalPages - 1, prev + 1))}
              disabled={pageIndex >= totalPages - 1}
              className="px-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-700 disabled:opacity-50"
            >
              Next
            </button>
          </div>
            </div>
            <aside className="space-y-4">
              <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-semibold text-slate-900">Next up</h3>
                  <button
                    type="button"
                    onClick={loadNextUp}
                    className="text-xs text-slate-500 hover:text-slate-700"
                  >
                    Refresh
                  </button>
                </div>
                {isLoadingNextUp ? (
                  <div className="text-sm text-slate-500 mt-3">Loading...</div>
                ) : nextUp.length ? (
                  <div className="mt-3 space-y-3">
                    {nextUp.map((appt) => (
                      <div key={appt.id} className="rounded-xl border border-slate-200 p-3">
                        <div className="text-sm font-medium text-slate-900">{appt.customer_name ?? "Customer"}</div>
                        <div className="text-xs text-slate-500">
                          {appt.type ?? "Appointment"} · {formatDate(appt.scheduled_time)}
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {appt.customer_phone ? (
                            <a
                              href={`tel:${appt.customer_phone}`}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-slate-200 bg-white text-xs text-slate-700 hover:bg-slate-50"
                            >
                              <Phone className="w-3.5 h-3.5" />
                              Call
                            </a>
                          ) : null}
                          <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-[11px] ${statusPill(appt.status)}`}>
                            {appt.status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-slate-500 mt-3">No upcoming appointments.</div>
                )}
              </section>

              <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-base font-semibold text-slate-900">Day view</h3>
                  <input
                    type="date"
                    value={calendarDate}
                    onChange={(event) => setCalendarDate(event.target.value)}
                    className="px-3 py-2 rounded-lg border border-slate-200 text-sm"
                  />
                </div>
                {availabilityError ? <div className="text-xs text-red-600 mt-2">{availabilityError}</div> : null}
                {isLoadingAvailability ? (
                  <div className="text-sm text-slate-500 mt-3">Loading slots…</div>
                ) : availability.length ? (
                  <div className="mt-3 space-y-2 max-h-[360px] overflow-auto pr-1">
                    {availability.map((slot) => (
                      <div
                        key={slot.start}
                        className={`flex items-center justify-between rounded-lg border px-3 py-2 text-xs ${
                          slot.booked ? "border-amber-200 bg-amber-50 text-amber-900" : "border-slate-200 bg-white text-slate-700"
                        }`}
                      >
                        <span>
                          {new Date(slot.start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} -{" "}
                          {new Date(slot.end).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </span>
                        <span>{slot.booked ? `Booked (${slot.status ?? "PENDING"})` : "Open"}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-slate-500 mt-3">No slots for this day.</div>
                )}
              </section>

              <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-base font-semibold text-slate-900">Schedule settings</h3>
                  <button
                    type="button"
                    onClick={saveSettings}
                    disabled={isSavingSettings}
                    className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs disabled:opacity-60"
                  >
                    {isSavingSettings ? "Saving…" : "Save"}
                  </button>
                </div>
                {settingsError ? <div className="text-xs text-red-600 mt-2">{settingsError}</div> : null}
                <div className="mt-3 grid gap-3">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[11px] text-slate-500 mb-1">Slot (minutes)</label>
                      <input
                        type="number"
                        min="5"
                        value={settingsDraft.slot_minutes}
                        onChange={(event) =>
                          setSettingsDraft((prev) => ({ ...prev, slot_minutes: Number(event.target.value) }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-500 mb-1">Buffer (minutes)</label>
                      <input
                        type="number"
                        min="0"
                        value={settingsDraft.buffer_minutes}
                        onChange={(event) =>
                          setSettingsDraft((prev) => ({ ...prev, buffer_minutes: Number(event.target.value) }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[11px] text-slate-500 mb-1">No-show after (minutes)</label>
                      <input
                        type="number"
                        min="5"
                        value={settingsDraft.no_show_minutes}
                        onChange={(event) =>
                          setSettingsDraft((prev) => ({ ...prev, no_show_minutes: Number(event.target.value) }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-500 mb-1">Reminder language</label>
                      <select
                        value={settingsDraft.locale}
                        onChange={(event) => setSettingsDraft((prev) => ({ ...prev, locale: event.target.value }))}
                        className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm bg-white"
                      >
                        <option value="en">English</option>
                        <option value="ar">Arabic</option>
                        <option value="fr">French</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-500 mb-1">Timezone</label>
                    <input
                      value={settingsDraft.timezone}
                      onChange={(event) => setSettingsDraft((prev) => ({ ...prev, timezone: event.target.value }))}
                      className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm"
                    />
                  </div>
                  <div className="space-y-2">
                    {WEEK_DAYS.map((day) => {
                      const slots = settingsDraft.weekly_hours?.[day.key] ?? [];
                      const enabled = slots.length > 0;
                      const start = enabled ? slots[0].start : "09:00";
                      const end = enabled ? slots[0].end : "18:00";
                      return (
                        <div key={day.key} className="grid grid-cols-[auto_1fr_1fr] items-center gap-2">
                          <label className="text-xs text-slate-600 flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={enabled}
                              onChange={(event) => {
                                const next = { ...(settingsDraft.weekly_hours ?? {}) };
                                next[day.key] = event.target.checked ? [{ start, end }] : [];
                                setSettingsDraft((prev) => ({ ...prev, weekly_hours: next }));
                              }}
                            />
                            {day.label}
                          </label>
                          <input
                            type="time"
                            value={start}
                            disabled={!enabled}
                            onChange={(event) => {
                              const next = { ...(settingsDraft.weekly_hours ?? {}) };
                              next[day.key] = [{ start: event.target.value, end }];
                              setSettingsDraft((prev) => ({ ...prev, weekly_hours: next }));
                            }}
                            className="px-2 py-1 rounded-lg border border-slate-200 text-xs"
                          />
                          <input
                            type="time"
                            value={end}
                            disabled={!enabled}
                            onChange={(event) => {
                              const next = { ...(settingsDraft.weekly_hours ?? {}) };
                              next[day.key] = [{ start, end: event.target.value }];
                              setSettingsDraft((prev) => ({ ...prev, weekly_hours: next }));
                            }}
                            className="px-2 py-1 rounded-lg border border-slate-200 text-xs"
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>
                {!settings ? <div className="text-xs text-slate-500 mt-2">Using default hours until saved.</div> : null}
              </section>
              <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-base font-semibold text-slate-900">Week view</h3>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        const next = addDays(new Date(weekStart), -7);
                        setWeekStart(next.toISOString().slice(0, 10));
                      }}
                      className="px-2 py-1 rounded-lg border border-slate-200 text-xs text-slate-600"
                    >
                      Prev
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const next = addDays(new Date(weekStart), 7);
                        setWeekStart(next.toISOString().slice(0, 10));
                      }}
                      className="px-2 py-1 rounded-lg border border-slate-200 text-xs text-slate-600"
                    >
                      Next
                    </button>
                  </div>
                </div>
                {isLoadingWeek ? (
                  <div className="text-sm text-slate-500 mt-3">Loading week view…</div>
                ) : weekSlots.length ? (
                  <div className="mt-3 overflow-auto">
                    <div className="grid gap-2" style={{ minWidth: "540px" }}>
                      <div className="grid grid-cols-[90px_repeat(7,1fr)] gap-2 text-[11px] text-slate-500">
                        <div></div>
                        {weekSlots.map((day) => (
                          <div key={day.date.toISOString()} className="text-center">
                            {formatShortDay(day.date)}
                          </div>
                        ))}
                      </div>
                      {Array.from({
                        length: Math.max(0, ...weekSlots.map((day) => day.slots.length)),
                      }).map((_, rowIdx) => {
                        const firstSlot = weekSlots.find((day) => day.slots[rowIdx])?.slots[rowIdx];
                        if (!firstSlot) return null;
                        const timeLabel = new Date(firstSlot.start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
                        return (
                          <div key={firstSlot.start} className="grid grid-cols-[90px_repeat(7,1fr)] gap-2">
                            <div className="text-[11px] text-slate-500 text-right pr-2">{timeLabel}</div>
                            {weekSlots.map((day) => {
                              const slotMatch = day.slots[rowIdx];
                              const slotStart = slotMatch?.start;
                              const appointmentsForSlot = weekAppointments.filter(
                                (appt) => slotStart && new Date(appt.scheduled_time).toISOString() === slotStart
                              );
                              return (
                                <div
                                  key={`${day.date.toISOString()}-${slotStart}`}
                                  onDragOver={(event) => event.preventDefault()}
                                  onDrop={(event) => {
                                    const apptId = event.dataTransfer.getData("text/plain");
                                    if (!apptId || !slotStart) return;
                                    rescheduleAppointment(Number(apptId), slotStart);
                                  }}
                                  className={`min-h-[42px] rounded-lg border text-[11px] px-2 py-1 ${
                                    slotMatch?.booked ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-white"
                                  }`}
                                >
                                  {appointmentsForSlot.map((appt) => (
                                    <div
                                      key={appt.id}
                                      draggable
                                      onDragStart={(event) => event.dataTransfer.setData("text/plain", String(appt.id))}
                                      className="rounded-md bg-slate-900 text-white px-2 py-1 mb-1"
                                    >
                                      {appt.customer_name ?? "Customer"}
                                    </div>
                                  ))}
                                </div>
                              );
                            })}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-slate-500 mt-3">No slots for this week.</div>
                )}
              </section>
            </aside>
          </div>
        </div>
      </div>
    </div>
  );
}
