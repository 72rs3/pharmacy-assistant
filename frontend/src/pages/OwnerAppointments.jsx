import { useEffect, useMemo, useState } from "react";
import { Calendar, ChevronDown, Copy, Phone, RefreshCw, Search } from "lucide-react";
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
  if (normalized === "PENDING") return "bg-blue-100 text-blue-700 border-blue-200";
  if (normalized === "CONFIRMED") return "bg-emerald-100 text-emerald-800 border-emerald-200";
  if (normalized === "COMPLETED") return "bg-blue-100 text-blue-800 border-blue-200";
  if (normalized === "CANCELLED") return "bg-red-100 text-red-800 border-red-200";
  return "bg-gray-100 text-gray-700 border-gray-200";
};

const statusAccent = (status) => {
  const normalized = String(status ?? "").toUpperCase();
  if (normalized === "CONFIRMED") return "border-l-emerald-400";
  if (normalized === "COMPLETED") return "border-l-blue-400";
  if (normalized === "CANCELLED") return "border-l-red-400";
  return "border-l-yellow-400";
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

const formatAuditDetails = (entry) => {
  try {
    const oldValues = entry.old_values_json ? JSON.parse(entry.old_values_json) : {};
    const newValues = entry.new_values_json ? JSON.parse(entry.new_values_json) : {};
    const keys = Array.from(new Set([...Object.keys(oldValues), ...Object.keys(newValues)]));
    if (!keys.length) return null;
    return keys
      .map((key) => {
        const prev = oldValues[key];
        const next = newValues[key];
        return `${key}: ${prev ?? "-"} -> ${next ?? "-"}`;
      })
      .join(" | ");
  } catch {
    return null;
  }
};

export default function OwnerAppointments({ view = "overview" }) {
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
  const [remindersById, setRemindersById] = useState({});
  const [remindersOpenById, setRemindersOpenById] = useState({});
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
  const [actionMessage, setActionMessage] = useState("");
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
  const [dragOverSlot, setDragOverSlot] = useState("");

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

  const loadReminders = async (appointmentId) => {
    try {
      const res = await api.get(`/appointments/${appointmentId}/reminders`);
      setRemindersById((prev) => ({ ...prev, [appointmentId]: Array.isArray(res.data) ? res.data : [] }));
    } catch {
      setRemindersById((prev) => ({ ...prev, [appointmentId]: [] }));
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

  const isOverview = view === "overview";
  const isWeekView = view === "week";
  const isScheduleView = view === "schedule";

  useEffect(() => {
    loadAppointments();
  }, [activeTab, statusFilter, sortMode, typeFilter, searchQuery, pageIndex]);

  useEffect(() => {
    if (isScheduleView) loadSettings();
  }, [isScheduleView]);

  useEffect(() => {
    if (isOverview) loadAvailability();
  }, [calendarDate, isOverview]);

  useEffect(() => {
    if (isOverview) loadNextUp();
  }, [isOverview]);

  useEffect(() => {
    if (isWeekView) loadWeekView();
  }, [weekStart, isWeekView]);

  const updateAppointment = async (appointmentId) => {
    setActionError("");
    setActionMessage("");
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
    setActionMessage("");
    setIsSavingId(appointmentId);
    try {
      const res = await api.patch(`/appointments/${appointmentId}`, {
        scheduled_time: scheduledTime,
      });
      setAppointments((prev) => prev.map((item) => (item.id === appointmentId ? res.data : item)));
      setWeekAppointments((prev) => prev.map((item) => (item.id === appointmentId ? res.data : item)));
      loadWeekView();
      loadAvailability();
      setActionMessage("Appointment rescheduled.");
    } catch (e) {
      setActionError(e?.response?.data?.detail ?? "Failed to reschedule appointment");
    } finally {
      setIsSavingId(null);
    }
  };

  const markNoShow = async (appointmentId) => {
    setActionError("");
    setActionMessage("");
    setIsSavingId(appointmentId);
    try {
      const res = await api.post(`/appointments/${appointmentId}/no-show`);
      setAppointments((prev) => prev.map((item) => (item.id === appointmentId ? res.data : item)));
      setActionMessage("No-show marked.");
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

  const renderNextUpBody = () => {
    if (isLoadingNextUp) {
      return <div className="text-sm text-gray-500 mt-3">Loading...</div>;
    }
    if (!nextUp.length) {
      return <div className="text-sm text-gray-500 mt-3">No upcoming appointments.</div>;
    }
    return (
      <div className="mt-3 space-y-3">
        {nextUp.map((appt) => (
          <div key={appt.id} className="rounded-lg border border-gray-200 bg-gray-50/60 p-3">
            <div className="text-sm font-semibold text-gray-900">{appt.customer_name ?? "Customer"}</div>
            <div className="text-xs text-gray-500 mt-1">
              {appt.type ?? "Appointment"} | {formatDate(appt.scheduled_time)}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {appt.customer_phone ? (
                <a
                  href={`tel:${appt.customer_phone}`}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 bg-white text-xs text-gray-700 hover:bg-gray-50"
                >
                  <Phone className="w-3.5 h-3.5" />
                  Call
                </a>
              ) : null}
              <span className={`inline-flex items-center px-2.5 py-1 rounded-lg border text-[11px] ${statusPill(appt.status)}`}>
                {appt.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderDayViewBody = () => {
    if (availabilityError) {
      return <div className="text-xs text-red-600 mt-2">{availabilityError}</div>;
    }
    if (isLoadingAvailability) {
      return <div className="text-sm text-gray-500 mt-3">Loading slots...</div>;
    }
    if (!availability.length) {
      return <div className="text-sm text-gray-500 mt-3">No slots for this day.</div>;
    }
    return (
      <div className="mt-3 space-y-2 max-h-[360px] overflow-auto pr-1">
        {availability.map((slot) => (
          <div
            key={slot.start}
            className={`flex items-center justify-between rounded-lg border px-3 py-2 text-[11px] ${
              slot.booked ? "border-amber-200 bg-amber-50 text-amber-900" : "border-gray-200 bg-white text-gray-700"
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
    );
  };

  const renderWeekViewBody = () => {
    if (isLoadingWeek) {
      return <div className="text-sm text-gray-500 mt-3">Loading week view...</div>;
    }
    if (!weekSlots.length) {
      return <div className="text-sm text-gray-500 mt-3">No slots for this week.</div>;
    }
    return (
      <div className="mt-3 overflow-auto">
        <div className="grid gap-2" style={{ minWidth: "540px" }}>
          <div className="grid grid-cols-[90px_repeat(7,1fr)] gap-2 text-[11px] text-gray-500">
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
                <div className="text-[11px] text-gray-500 text-right pr-2">{timeLabel}</div>
                {weekSlots.map((day) => {
                  const slotMatch = day.slots[rowIdx];
                  const slotStart = slotMatch?.start;
                  const slotTime = slotStart ? new Date(slotStart).getTime() : null;
                  const appointmentsForSlot = weekAppointments.filter(
                    (appt) => slotTime && new Date(appt.scheduled_time).getTime() === slotTime
                  );
                  return (
                    <div
                      key={`${day.date.toISOString()}-${slotStart}`}
                      onDragOver={(event) => event.preventDefault()}
                      onDragEnter={() => slotStart && setDragOverSlot(slotStart)}
                      onDragLeave={() => setDragOverSlot("")}
                      onDrop={(event) => {
                        const apptId = event.dataTransfer.getData("text/plain");
                        if (!apptId || !slotStart) return;
                        rescheduleAppointment(Number(apptId), slotStart);
                        setDragOverSlot("");
                      }}
                      className={`min-h-[42px] rounded-lg border text-[11px] px-2 py-1 ${
                        dragOverSlot === slotStart
                          ? "border-blue-300 bg-blue-50"
                          : slotMatch?.booked
                          ? "border-amber-200 bg-amber-50"
                          : "border-gray-200 bg-white"
                      }`}
                    >
                      {appointmentsForSlot.map((appt) => (
                        <div
                          key={appt.id}
                          draggable
                          onDragStart={(event) => event.dataTransfer.setData("text/plain", String(appt.id))}
                          className="rounded-md bg-gray-900 text-white px-2 py-1 mb-1"
                        >
                          <div className="font-medium">{appt.customer_name ?? "Customer"}</div>
                          <div className="text-[10px] opacity-80">{appt.type ?? "Appointment"}</div>
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
    );
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-6 py-5 flex items-center justify-between gap-4 border-b border-gray-200">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-gray-900 tracking-tight">Appointments</h1>
            <p className="text-sm text-gray-500 mt-1">Confirm bookings and keep the schedule updated.</p>
          </div>

          <div className="flex items-center gap-2">
            {isOverview ? (
              <button
                type="button"
                onClick={loadAppointments}
                disabled={isLoading}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                title="Refresh"
              >
                <RefreshCw className="w-4 h-4" />
                Refresh
              </button>
            ) : null}
          </div>
        </div>

        <div className="p-6 bg-gray-50 space-y-4">
          {error ? <div className="rounded-lg border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">{error}</div> : null}
          {actionError ? (
            <div className="rounded-lg border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">{actionError}</div>
          ) : null}
          {actionMessage ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-800 px-4 py-3 text-sm">
              {actionMessage}
            </div>
          ) : null}

          <div className={`grid gap-6 ${isOverview ? "lg:grid-cols-[minmax(0,1fr)_360px]" : "lg:grid-cols-1"}`}>
            <div className="space-y-4">
          {isOverview ? (
            <>
          <section className="bg-white rounded-lg border border-gray-200 shadow-sm p-5 space-y-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Filters</div>
            <div className="grid gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  value={searchDraft}
                  onChange={(event) => setSearchDraft(event.target.value)}
                  placeholder="Search name, phone, type..."
                  className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-gray-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div className="relative">
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-200 bg-white text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                  title="Filter status"
                >
                  <option value="ALL">Filter status</option>
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className="relative">
                <select
                  value={sortMode}
                  onChange={(event) => setSortMode(event.target.value)}
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-200 bg-white text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                  title="Sort"
                >
                  {SORT_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
              <div className="relative">
                <input
                  value={typeFilter}
                  onChange={(event) => setTypeFilter(event.target.value)}
                  placeholder="Filter by type..."
                  className="w-full px-4 py-2.5 rounded-lg border border-gray-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
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
                    className={`px-4 py-2 rounded-lg text-xs transition ${
                      isActive
                        ? "bg-blue-600 text-white shadow-sm"
                        : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                    }`}
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>

            <div className="flex flex-wrap items-center gap-4 text-xs text-gray-600">
              <span>
                Total: <span className="font-medium text-gray-700">{counts.total}</span>
              </span>
              <span>
                Pending: <span className="font-medium text-gray-700">{counts.pending}</span>
              </span>
              <span>
                Confirmed: <span className="font-medium text-gray-700">{counts.confirmed}</span>
              </span>
              <span>
                Completed: <span className="font-medium text-gray-700">{counts.completed}</span>
              </span>
              <span>
                Cancelled: <span className="font-medium text-gray-700">{counts.cancelled}</span>
              </span>
              <span className="ml-auto">Showing {pageStart}-{pageEnd} of {totalCount}</span>
            </div>
          </section>

          {appointments.length === 0 && !isLoading ? (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-8 text-gray-600 text-sm">
              No appointments booked yet.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-900">Appointments</div>
                <div className="text-xs text-blue-600 hover:text-blue-700 cursor-pointer">Manage updates and reminders</div>
              </div>
              {appointments.map((appt) => (
                <section
                  key={appt.id}
                  className={`bg-white rounded-lg border border-gray-200 shadow-sm border-l-4 ${statusAccent(appt.status)}`}
                >
                  <div className="px-6 py-5 border-b border-gray-200 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-semibold text-gray-900">Appointment #{appt.id}</h2>
                        <span className={`inline-flex items-center px-3 py-1 rounded-full border text-xs ${statusPill(appt.status)}`}>
                          {appt.status}
                        </span>
                        {appt.no_show ? (
                          <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-red-200 bg-red-50 text-xs text-red-700">
                            No-show
                          </span>
                        ) : null}
                      </div>
                      <div className="text-sm text-gray-600">
                        {appt.type ?? "Appointment"} <span className="mx-2">|</span> {formatDate(appt.scheduled_time)}
                      </div>
                      {appt.updated_at ? (
                        <div className="text-xs text-gray-400">Last updated: {formatDate(appt.updated_at)}</div>
                      ) : null}
                      <div className="flex flex-wrap gap-3 pt-1 text-xs">
                        {appt.customer_phone ? (
                          <a
                            href={`tel:${appt.customer_phone}`}
                            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
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
                            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                            title="Copy phone"
                          >
                            <Copy className="w-3.5 h-3.5" />
                            Copy
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => {
                            setAuditOpenById((prev) => ({ ...prev, [appt.id]: !prev[appt.id] }));
                            if (!auditById[appt.id]) {
                              loadAudits(appt.id);
                            }
                          }}
                          className="inline-flex items-center px-4 py-2 rounded-lg border border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                        >
                          History
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setRemindersOpenById((prev) => ({ ...prev, [appt.id]: !prev[appt.id] }));
                            if (!remindersById[appt.id]) {
                              loadReminders(appt.id);
                            }
                          }}
                          className="inline-flex items-center px-4 py-2 rounded-lg border border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                        >
                          Reminders
                        </button>
                      </div>
                    </div>
                    <div className="grid gap-2 text-xs lg:text-right">
                      <div className="text-gray-700 font-medium">Customer: {appt.customer_name ?? "--"}</div>
                      <div className="text-gray-600">Phone: {appt.customer_phone ?? "--"}</div>
                      {appt.customer_email ? (
                        <div className="text-gray-600 break-all">Email: {appt.customer_email}</div>
                      ) : null}
                      {appt.vaccine_name ? (
                        <div className="text-gray-600">Vaccine: {appt.vaccine_name}</div>
                      ) : null}
                    </div>
                  </div>

                  <div className="px-6 py-5 bg-white grid gap-4 md:flex md:flex-wrap md:items-end">
                    <div>
                      <label className="block text-sm text-gray-600 mb-1" htmlFor={`appt-status-${appt.id}`}>
                        Status
                      </label>
                      <select
                        id={`appt-status-${appt.id}`}
                        value={statusById[appt.id] ?? appt.status}
                        onChange={(event) => setStatusById((prev) => ({ ...prev, [appt.id]: event.target.value }))}
                        className="w-44 px-4 py-2.5 rounded-lg border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {STATUS_OPTIONS.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm text-gray-600 mb-1" htmlFor={`appt-time-${appt.id}`}>
                        Reschedule time
                      </label>
                      <div className="relative">
                        <input
                          id={`appt-time-${appt.id}`}
                          type="datetime-local"
                          value={timeById[appt.id] ?? ""}
                          onChange={(event) => setTimeById((prev) => ({ ...prev, [appt.id]: event.target.value }))}
                          className="w-60 px-4 py-2.5 rounded-lg border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 pr-10"
                        />
                        <Calendar className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={() => updateAppointment(appt.id)}
                        disabled={isSavingId === appt.id}
                        className="px-6 py-2.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                      >
                        {isSavingId === appt.id ? "Updating..." : "Update"}
                      </button>
                      {!appt.no_show && ["PENDING", "CONFIRMED"].includes(String(appt.status ?? "").toUpperCase()) ? (
                        <button
                          type="button"
                          onClick={() => markNoShow(appt.id)}
                          disabled={isSavingId === appt.id}
                          className="px-6 py-2.5 text-sm text-red-600 hover:bg-red-50 rounded-lg disabled:opacity-60"
                        >
                          Mark no-show
                        </button>
                      ) : null}
                    </div>
                  </div>
                  {auditOpenById[appt.id] ? (
                    <div className="px-6 pb-5">
                      <div className="text-xs text-gray-500 mb-2">Audit trail</div>
                      {auditById[appt.id] && auditById[appt.id].length ? (
                        <div className="space-y-2">
                          {auditById[appt.id].map((entry) => (
                            <div key={entry.id} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-700">
                              <div className="font-medium">{entry.action}</div>
                              {formatAuditDetails(entry) ? (
                                <div className="text-[11px] text-gray-600">{formatAuditDetails(entry)}</div>
                              ) : null}
                              <div className="text-[11px] text-gray-500">{formatDate(entry.created_at)}</div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-xs text-gray-500">No audit history yet.</div>
                      )}
                    </div>
                  ) : null}
                  {remindersOpenById[appt.id] ? (
                    <div className="px-6 pb-5">
                      <div className="flex items-center justify-between">
                        <div className="text-xs text-gray-500">Reminder status</div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => loadReminders(appt.id)}
                            className="text-xs text-gray-500 hover:text-gray-700"
                          >
                            Refresh
                          </button>
                          <button
                            type="button"
                            onClick={async () => {
                              try {
                                const res = await api.get("/appointments/reminders/preview", {
                                  params: { appointment_id: appt.id, template: "24h" },
                                });
                                const win = window.open("", "_blank");
                                if (win) {
                                  win.document.write(res.data?.html ?? "<p>No preview</p>");
                                  win.document.close();
                                }
                              } catch (e) {
                                setActionError(e?.response?.data?.detail ?? "Failed to load preview");
                              }
                            }}
                            className="text-xs text-gray-500 hover:text-gray-700"
                          >
                            Preview
                          </button>
                          <button
                            type="button"
                            onClick={async () => {
                              const email = window.prompt("Send test email to:", appt.customer_email ?? "");
                              if (!email) return;
                              try {
                                await api.post("/appointments/reminders/test", null, {
                                  params: { appointment_id: appt.id, to_email: email },
                                });
                                setActionMessage("Test email sent.");
                              } catch (e) {
                                setActionError(e?.response?.data?.detail ?? "Failed to send test email");
                              }
                            }}
                            className="text-xs text-gray-500 hover:text-gray-700"
                          >
                            Send test
                          </button>
                        </div>
                      </div>
                      {remindersById[appt.id] && remindersById[appt.id].length ? (
                        <div className="mt-2 space-y-2">
                          {remindersById[appt.id].map((reminder) => (
                            <div key={reminder.id} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-700">
                              <div className="flex items-center justify-between">
                                <span>{reminder.template} | {reminder.channel}</span>
                                <span className="text-[11px] text-gray-500">{reminder.status}</span>
                              </div>
                              <div className="text-[11px] text-gray-500">Send at: {formatDate(reminder.send_at)}</div>
                              {reminder.sent_at ? (
                                <div className="text-[11px] text-gray-500">Sent at: {formatDate(reminder.sent_at)}</div>
                              ) : null}
                              {reminder.error_message ? (
                                <div className="text-[11px] text-red-600">Error: {reminder.error_message}</div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-xs text-gray-500 mt-2">No reminders scheduled yet.</div>
                      )}
                    </div>
                  ) : null}
                </section>
              ))}
            </div>
          )}

          <div className="mt-4 flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-500">
            <span>
              Page {pageIndex + 1} of {totalPages}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPageIndex((prev) => Math.max(0, prev - 1))}
                disabled={pageIndex === 0}
                className="px-3 py-1 text-gray-400 hover:text-gray-600 disabled:opacity-40"
              >
                Previous
              </button>
              <button
                type="button"
                onClick={() => setPageIndex((prev) => Math.min(totalPages - 1, prev + 1))}
                disabled={pageIndex >= totalPages - 1}
                className="px-3 py-1 text-gray-400 hover:text-gray-600 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
            </>
          ) : (
            <div className="space-y-4">
              {isScheduleView ? (
                <section className="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-base font-semibold text-gray-900">Schedule settings</h3>
                    <button
                      type="button"
                      onClick={saveSettings}
                      disabled={isSavingSettings}
                      className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs disabled:opacity-60"
                    >
                      {isSavingSettings ? "Saving..." : "Save"}
                    </button>
                  </div>
                  {settingsError ? <div className="text-xs text-red-600 mt-2">{settingsError}</div> : null}
                  <div className="mt-3 grid gap-3">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[11px] text-gray-500 mb-1">Slot (minutes)</label>
                        <input
                          type="number"
                          min="5"
                          value={settingsDraft.slot_minutes}
                          onChange={(event) =>
                            setSettingsDraft((prev) => ({ ...prev, slot_minutes: Number(event.target.value) }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-gray-500 mb-1">Buffer (minutes)</label>
                        <input
                          type="number"
                          min="0"
                          value={settingsDraft.buffer_minutes}
                          onChange={(event) =>
                            setSettingsDraft((prev) => ({ ...prev, buffer_minutes: Number(event.target.value) }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[11px] text-gray-500 mb-1">No-show after (minutes)</label>
                        <input
                          type="number"
                          min="5"
                          value={settingsDraft.no_show_minutes}
                          onChange={(event) =>
                            setSettingsDraft((prev) => ({ ...prev, no_show_minutes: Number(event.target.value) }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-gray-500 mb-1">Reminder language</label>
                        <select
                          value={settingsDraft.locale}
                          onChange={(event) => setSettingsDraft((prev) => ({ ...prev, locale: event.target.value }))}
                          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm bg-white"
                        >
                          <option value="en">English</option>
                          <option value="ar">Arabic</option>
                          <option value="fr">French</option>
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="block text-[11px] text-gray-500 mb-1">Timezone</label>
                      <input
                        value={settingsDraft.timezone}
                        onChange={(event) => setSettingsDraft((prev) => ({ ...prev, timezone: event.target.value }))}
                        className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm"
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
                            <label className="text-xs text-gray-600 flex items-center gap-2">
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
                              className="px-2 py-1 rounded-lg border border-gray-200 text-xs"
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
                              className="px-2 py-1 rounded-lg border border-gray-200 text-xs"
                            />
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  {!settings ? <div className="text-xs text-gray-500 mt-2">Using default hours until saved.</div> : null}
                </section>
              ) : null}
              {isWeekView ? (
                <section className="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-base font-semibold text-gray-900">Week view</h3>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          const next = addDays(new Date(weekStart), -7);
                          setWeekStart(next.toISOString().slice(0, 10));
                        }}
                        className="px-2 py-1 rounded-lg border border-gray-200 text-xs text-gray-600"
                      >
                        Prev
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          const next = addDays(new Date(weekStart), 7);
                          setWeekStart(next.toISOString().slice(0, 10));
                        }}
                        className="px-2 py-1 rounded-lg border border-gray-200 text-xs text-gray-600"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                  {renderWeekViewBody()}
                </section>
              ) : null}
            </div>
          )}

            </div>
            {isOverview ? (
              <div className="space-y-3 lg:hidden">
              {isOverview ? (
                <details className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
                  <summary className="cursor-pointer text-sm font-semibold text-gray-900">Next up</summary>
                  {renderNextUpBody()}
                </details>
              ) : null}
              {isOverview ? (
                <details className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
                  <summary className="cursor-pointer text-sm font-semibold text-gray-900">Day view</summary>
                  <div className="mt-2">
                    <input
                      type="date"
                      value={calendarDate}
                      onChange={(event) => setCalendarDate(event.target.value)}
                      className="px-3 py-2 rounded-lg border border-gray-200 text-sm"
                    />
                  </div>
                  {renderDayViewBody()}
                </details>
              ) : null}
              {isScheduleView ? (
                <details className="bg-white rounded-lg border border-gray-200 shadow-sm p-4" open>
                  <summary className="cursor-pointer text-sm font-semibold text-gray-900">Schedule settings</summary>
                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={saveSettings}
                      disabled={isSavingSettings}
                      className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs disabled:opacity-60"
                    >
                      {isSavingSettings ? "Saving..." : "Save"}
                    </button>
                  </div>
                  {settingsError ? <div className="text-xs text-red-600 mt-2">{settingsError}</div> : null}
                  <div className="mt-3 grid gap-3">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[11px] text-gray-500 mb-1">Slot (minutes)</label>
                        <input
                          type="number"
                          min="5"
                          value={settingsDraft.slot_minutes}
                          onChange={(event) =>
                            setSettingsDraft((prev) => ({ ...prev, slot_minutes: Number(event.target.value) }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-gray-500 mb-1">Buffer (minutes)</label>
                        <input
                          type="number"
                          min="0"
                          value={settingsDraft.buffer_minutes}
                          onChange={(event) =>
                            setSettingsDraft((prev) => ({ ...prev, buffer_minutes: Number(event.target.value) }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[11px] text-gray-500 mb-1">No-show after (minutes)</label>
                        <input
                          type="number"
                          min="5"
                          value={settingsDraft.no_show_minutes}
                          onChange={(event) =>
                            setSettingsDraft((prev) => ({ ...prev, no_show_minutes: Number(event.target.value) }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-gray-500 mb-1">Reminder language</label>
                        <select
                          value={settingsDraft.locale}
                          onChange={(event) => setSettingsDraft((prev) => ({ ...prev, locale: event.target.value }))}
                          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm bg-white"
                        >
                          <option value="en">English</option>
                          <option value="ar">Arabic</option>
                          <option value="fr">French</option>
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="block text-[11px] text-gray-500 mb-1">Timezone</label>
                      <input
                        value={settingsDraft.timezone}
                        onChange={(event) => setSettingsDraft((prev) => ({ ...prev, timezone: event.target.value }))}
                        className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm"
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
                            <label className="text-xs text-gray-600 flex items-center gap-2">
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
                              className="px-2 py-1 rounded-lg border border-gray-200 text-xs"
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
                              className="px-2 py-1 rounded-lg border border-gray-200 text-xs"
                            />
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </details>
              ) : null}
              {isWeekView ? (
                <details className="bg-white rounded-lg border border-gray-200 shadow-sm p-4" open>
                  <summary className="cursor-pointer text-sm font-semibold text-gray-900">Week view</summary>
                  <div className="mt-3 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        const next = addDays(new Date(weekStart), -7);
                        setWeekStart(next.toISOString().slice(0, 10));
                      }}
                      className="px-2 py-1 rounded-lg border border-gray-200 text-xs text-gray-600"
                    >
                      Prev
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const next = addDays(new Date(weekStart), 7);
                        setWeekStart(next.toISOString().slice(0, 10));
                      }}
                      className="px-2 py-1 rounded-lg border border-gray-200 text-xs text-gray-600"
                    >
                      Next
                    </button>
                  </div>
                  {renderWeekViewBody()}
                </details>
              ) : null}
              </div>
            ) : null}
            {isOverview ? (
              <aside className="hidden lg:block space-y-4 lg:sticky lg:top-6 lg:self-start">
              {isOverview ? (
                <section className="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
                  <div className="flex items-center justify-between">
                    <h3 className="text-base font-semibold text-gray-900">Next up</h3>
                    <button
                      type="button"
                      onClick={loadNextUp}
                      className="text-xs text-blue-600 hover:text-blue-700"
                    >
                      Refresh
                    </button>
                  </div>
                  {renderNextUpBody()}
                </section>
              ) : null}

              {isOverview ? (
                <section className="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-base font-semibold text-gray-900">Day view</h3>
                    <input
                      type="date"
                      value={calendarDate}
                      onChange={(event) => setCalendarDate(event.target.value)}
                      className="px-3 py-1.5 rounded-lg border border-gray-200 text-xs"
                    />
                  </div>
                  {renderDayViewBody()}
                </section>
              ) : null}

              {isScheduleView ? (
                <section className="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-base font-semibold text-gray-900">Schedule settings</h3>
                    <button
                      type="button"
                      onClick={saveSettings}
                      disabled={isSavingSettings}
                      className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs disabled:opacity-60"
                    >
                      {isSavingSettings ? "Saving..." : "Save"}
                    </button>
                  </div>
                  {settingsError ? <div className="text-xs text-red-600 mt-2">{settingsError}</div> : null}
                  <div className="mt-3 grid gap-3">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[11px] text-gray-500 mb-1">Slot (minutes)</label>
                        <input
                          type="number"
                          min="5"
                          value={settingsDraft.slot_minutes}
                          onChange={(event) =>
                            setSettingsDraft((prev) => ({ ...prev, slot_minutes: Number(event.target.value) }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-gray-500 mb-1">Buffer (minutes)</label>
                        <input
                          type="number"
                          min="0"
                          value={settingsDraft.buffer_minutes}
                          onChange={(event) =>
                            setSettingsDraft((prev) => ({ ...prev, buffer_minutes: Number(event.target.value) }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[11px] text-gray-500 mb-1">No-show after (minutes)</label>
                        <input
                          type="number"
                          min="5"
                          value={settingsDraft.no_show_minutes}
                          onChange={(event) =>
                            setSettingsDraft((prev) => ({ ...prev, no_show_minutes: Number(event.target.value) }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-gray-500 mb-1">Reminder language</label>
                        <select
                          value={settingsDraft.locale}
                          onChange={(event) => setSettingsDraft((prev) => ({ ...prev, locale: event.target.value }))}
                          className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm bg-white"
                        >
                          <option value="en">English</option>
                          <option value="ar">Arabic</option>
                          <option value="fr">French</option>
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="block text-[11px] text-gray-500 mb-1">Timezone</label>
                      <input
                        value={settingsDraft.timezone}
                        onChange={(event) => setSettingsDraft((prev) => ({ ...prev, timezone: event.target.value }))}
                        className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm"
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
                            <label className="text-xs text-gray-600 flex items-center gap-2">
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
                              className="px-2 py-1 rounded-lg border border-gray-200 text-xs"
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
                              className="px-2 py-1 rounded-lg border border-gray-200 text-xs"
                            />
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  {!settings ? <div className="text-xs text-gray-500 mt-2">Using default hours until saved.</div> : null}
                </section>
              ) : null}
              {isWeekView ? (
                <section className="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-base font-semibold text-gray-900">Week view</h3>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          const next = addDays(new Date(weekStart), -7);
                          setWeekStart(next.toISOString().slice(0, 10));
                        }}
                        className="px-2 py-1 rounded-lg border border-gray-200 text-xs text-gray-600"
                      >
                        Prev
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          const next = addDays(new Date(weekStart), 7);
                          setWeekStart(next.toISOString().slice(0, 10));
                        }}
                        className="px-2 py-1 rounded-lg border border-gray-200 text-xs text-gray-600"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                  {renderWeekViewBody()}
                </section>
              ) : null}
              </aside>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
