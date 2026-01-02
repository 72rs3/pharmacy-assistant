import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Minimize2, Pill, Send, UserRound, X } from "lucide-react";
import api from "../../api/axios";
import { useCustomerCart } from "../../context/CustomerCartContext";
import { useTenant } from "../../context/TenantContext";
import { isValidE164 } from "../../utils/validation";
import PhoneInput from "../ui/PhoneInput";

const CHAT_ID_KEY = "customer_chat_id";
const SESSION_ID_KEY = "customer_session_id";
const APPOINTMENT_TRACKING_CODE_KEY = "customer_appointment_tracking_code";

const defaultSuggestions = [
  "Check medication availability",
  "Store hours",
  "Delivery information",
  "Book an appointment",
];

const GLOBAL_ACTION_LABELS = new Set([
  "Search another medicine",
  "Shop OTC products",
  "Book appointment",
  "Contact pharmacy",
]);

const normalizeReplyKey = (value) =>
  String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/^search\s+(for\s+)?/, "")
    .replace(/\s+/g, " ");

const dedupeReplies = (values) => {
  const out = [];
  const seen = new Map();
  (values ?? []).forEach((raw) => {
    const text = String(raw ?? "").trim();
    if (!text) return;
    const key = normalizeReplyKey(text);
    const prevIndex = seen.get(key);
    if (prevIndex == null) {
      seen.set(key, out.length);
      out.push(text);
      return;
    }
    const prev = out[prevIndex] ?? "";
    const prefersSearch = /^search\s+/i.test(text) && !/^search\s+/i.test(prev);
    if (prefersSearch) out[prevIndex] = text;
  });
  return out;
};

const splitReplies = (values, { excludeKeys = new Set() } = {}) => {
  const deduped = dedupeReplies(values).filter((reply) => !excludeKeys.has(normalizeReplyKey(reply)));
  const context = [];
  const global = [];
  deduped.forEach((reply) => {
    if (GLOBAL_ACTION_LABELS.has(reply)) global.push(reply);
    else context.push(reply);
  });
  return { context, global };
};

const dedupeAcross = (primary, secondary) => {
  const seen = new Set(primary.map((item) => normalizeReplyKey(item)));
  return secondary.filter((item) => !seen.has(normalizeReplyKey(item)));
};

const shouldOfferPrescriptionUpload = (text) => {
  const normalized = (text ?? "").toLowerCase();
  return normalized.includes("prescription required") || normalized.includes("requires prescription");
};

const parseBackendDate = (value) => {
  if (!value) return null;
  if (value instanceof Date) return value;
  if (typeof value === "string") {
    const hasTimezone = /([zZ]|[+-]\d{2}:\d{2})$/.test(value);
    return new Date(hasTimezone ? value : `${value}Z`);
  }
  return new Date(value);
};

export default function CustomerChatWidget({ isOpen, onClose, brandName = "Sunr", placement = "viewport" }) {
  const navigate = useNavigate();
  const { addItem } = useCustomerCart();
  const { pharmacy } = useTenant() ?? {};
  const [isEscalated, setIsEscalated] = useState(false);
  const [showGlobalActions, setShowGlobalActions] = useState(false);
  const [intakeDraft, setIntakeDraft] = useState({
    customer_name: "",
    customer_phone: "",
    age_range: "18-24",
    main_concern: "",
    how_long: "1-3 days",
    current_medications: "",
    allergies: "",
  });
  const [intakeError, setIntakeError] = useState("");
  const [isSubmittingIntake, setIsSubmittingIntake] = useState(false);
  const [rxOrderDraft, setRxOrderDraft] = useState({ medicineId: null, showForm: false });
  const [rxForm, setRxForm] = useState({
    customer_name: "",
    customer_phone: "",
    customer_address: "",
    customer_notes: "",
  });
  const [rxFormError, setRxFormError] = useState("");
  const [isPlacingRxOrder, setIsPlacingRxOrder] = useState(false);
  const [apptForm, setApptForm] = useState({
    customer_name: "",
    customer_phone: "",
    customer_email: "",
    type: "Consultation",
    scheduled_time: "",
    vaccine_name: "",
    notes: "",
  });
  const [apptDate, setApptDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [apptSlots, setApptSlots] = useState([]);
  const [isLoadingApptSlots, setIsLoadingApptSlots] = useState(false);
  const [apptSlotsError, setApptSlotsError] = useState("");
  const [apptError, setApptError] = useState("");
  const [isSubmittingAppt, setIsSubmittingAppt] = useState(false);
  const [messages, setMessages] = useState([
    {
      id: "welcome",
      senderType: "AI",
      text: `Hello! I am your ${brandName} Pharmacy AI assistant. How can I help you today?`,
      timestamp: new Date(),
      suggestions: defaultSuggestions,
      allowPrescriptionUpload: false,
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [chatId, setChatId] = useState(() =>
    typeof window !== "undefined" ? localStorage.getItem(CHAT_ID_KEY) ?? "" : ""
  );
  const [sessionId, setSessionId] = useState(() =>
    typeof window !== "undefined" ? localStorage.getItem(SESSION_ID_KEY) ?? "" : ""
  );
  const [uploadState, setUploadState] = useState({
    files: [],
    status: "",
    error: "",
    tokens: [],
  });
  const messagesEndRef = useRef(null);

  const resetChatSession = () => {
    setIsEscalated(false);
    setShowGlobalActions(false);
    setSessionId("");
    if (typeof window !== "undefined") {
      localStorage.removeItem(SESSION_ID_KEY);
    }
    setMessages((prev) => [
      ...prev,
      {
        id: `system-new-session-${Date.now()}`,
        senderType: "SYSTEM",
        text: "You can continue with the AI assistant now. A new consultation will start if needed.",
        timestamp: new Date(),
      },
    ]);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    setMessages((prev) => {
      if (!prev.length || prev[0]?.id !== "welcome") return prev;
      return [
        {
          ...prev[0],
          text: `Hello! I am your ${brandName} Pharmacy AI assistant. How can I help you today?`,
        },
        ...prev.slice(1),
      ];
    });
  }, [brandName]);

  useEffect(() => {
    if (!isOpen) return;
    setShowGlobalActions(false);
  }, [isEscalated, isOpen]);

  useEffect(() => {
    if (!isOpen || !chatId || !sessionId) return;
    let isActive = true;

    const loadHistory = async () => {
      try {
        const res = await api.get(`/chat/sessions/${sessionId}/messages`, {
          headers: { "X-Chat-ID": chatId },
        });
        if (!isActive) return;
        const items = res.data ?? [];
        let escalated = false;
        const history = items.map((item) => {
          const meta = item.metadata ?? {};
          const actions = Array.isArray(meta.actions) ? meta.actions : [];
          const cards = Array.isArray(meta.cards) ? meta.cards : [];
          const quickReplies = Array.isArray(meta.quick_replies) ? meta.quick_replies : [];
          const dataLastUpdatedAt = meta.data_last_updated_at ?? null;
          const indexedAt = meta.indexed_at ?? null;
          const intent = meta.intent ?? "";
          const text = item.text ?? "";
          if ((item.sender_type ?? "") === "SYSTEM") {
            if (text === "Escalated to pharmacist") escalated = true;
            if (text === "Consultation closed") escalated = false;
            if (text === "Session expired due to inactivity") escalated = false;
          }
          return {
            id: `msg-${item.id}`,
            senderType: item.sender_type ?? "SYSTEM",
            text,
            timestamp: parseBackendDate(item.created_at) ?? new Date(),
            intent,
            meta,
            actions,
            cards,
            quickReplies,
            allowPrescriptionUpload: shouldOfferPrescriptionUpload(text),
            freshness:
              dataLastUpdatedAt || indexedAt
                ? { dataLastUpdatedAt, indexedAt }
                : null,
          };
        });
        setMessages((prev) => [prev[0], ...history]);
        setIsEscalated(escalated);
      } catch {
        // Keep existing messages on failure.
      }
    };

    loadHistory();
    return () => {
      isActive = false;
    };
  }, [chatId, isOpen, sessionId]);

  useEffect(() => {
    if (!isOpen || !chatId || !sessionId || !isEscalated) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await api.get(`/chat/sessions/${sessionId}/messages`, {
          headers: { "X-Chat-ID": chatId },
        });
        if (cancelled) return;
        const items = res.data ?? [];
        let escalated = false;
        const history = items.map((item) => {
          const meta = item.metadata ?? {};
          const text = item.text ?? "";
          if ((item.sender_type ?? "") === "SYSTEM") {
            if (text === "Escalated to pharmacist") escalated = true;
            if (text === "Consultation closed") escalated = false;
            if (text === "Session expired due to inactivity") escalated = false;
          }
          return {
            id: `msg-${item.id}`,
            senderType: item.sender_type ?? "SYSTEM",
            text,
            timestamp: parseBackendDate(item.created_at) ?? new Date(),
            meta,
          };
        });
        setMessages((prev) => [prev[0], ...history]);
        setIsEscalated(escalated);
      } catch {
        // ignore
      }
    };
    tick();
    const handle = setInterval(tick, 5000);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [chatId, isEscalated, isOpen, sessionId]);

  const handleSend = async (overrideText) => {
    const trimmed = String(overrideText ?? inputValue).trim();
    if (!trimmed) return;

    const userMessage = {
      id: `user-${Date.now()}`,
      senderType: "USER",
      text: trimmed,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    if (overrideText == null) setInputValue("");
    setIsTyping(true);

    try {
      if (isEscalated && sessionId) {
        try {
          await api.post(
            `/chat/sessions/${sessionId}/messages`,
            { text: trimmed },
            { headers: chatId ? { "X-Chat-ID": chatId } : {} }
          );
        } catch (err) {
          const detail = err?.response?.data?.detail ?? "";
          if (String(detail).toLowerCase().includes("expired") || err?.response?.status === 410) {
            setIsEscalated(false);
            setMessages((prev) => [
              ...prev,
              {
                id: `system-expired-${Date.now()}`,
                senderType: "SYSTEM",
                text: "Session expired due to inactivity. Start a new consultation if you still need help.",
                timestamp: new Date(),
              },
            ]);
            return;
          }
          throw err;
        }
        return;
      }
      const res = await api.post(
        "/ai/chat",
        { message: trimmed, session_id: sessionId || undefined },
        { headers: chatId ? { "X-Chat-ID": chatId } : {} }
      );
      const nextChatId = res.data?.customer_id ?? chatId;
      if (nextChatId && nextChatId !== chatId) {
        setChatId(nextChatId);
        if (typeof window !== "undefined") {
          localStorage.setItem(CHAT_ID_KEY, nextChatId);
        }
      }
      const nextSessionId = res.data?.session_id ?? sessionId;
      if (nextSessionId && nextSessionId !== sessionId) {
        setSessionId(nextSessionId);
        if (typeof window !== "undefined") {
          localStorage.setItem(SESSION_ID_KEY, nextSessionId);
        }
      }

      const answer = res.data?.answer ?? "";
      const intent = res.data?.intent ?? "";
      const dataLastUpdatedAt = res.data?.data_last_updated_at ?? null;
      const indexedAt = res.data?.indexed_at ?? null;
      const cards = Array.isArray(res.data?.cards) ? res.data.cards : [];
      const includeFreshness = intent === "MEDICINE_SEARCH" || (cards && cards.length > 0);
      const botMessage = {
        id: `bot-${res.data?.interaction_id ?? Date.now()}`,
        senderType: "AI",
        text: answer,
        timestamp: parseBackendDate(res.data?.created_at) ?? new Date(),
        intent,
        allowPrescriptionUpload: shouldOfferPrescriptionUpload(answer),
        freshness: includeFreshness ? { dataLastUpdatedAt, indexedAt } : null,
        actions: Array.isArray(res.data?.actions) ? res.data.actions : [],
        cards,
        quickReplies: Array.isArray(res.data?.quick_replies) ? res.data.quick_replies : [],
      };
      const systemMessage = res.data?.system_message
        ? {
            id: `system-${Date.now()}`,
            senderType: "SYSTEM",
            text: res.data.system_message,
            timestamp: new Date(),
          }
        : null;
      if (res.data?.system_message === "Escalated to pharmacist") {
        setIsEscalated(true);
      }
      setMessages((prev) => [...prev, ...(systemMessage ? [systemMessage] : []), botMessage]);

    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `bot-error-${Date.now()}`,
          senderType: "SYSTEM",
          text: "Sorry, I could not reach the assistant right now. Please try again.",
          timestamp: new Date(),
          allowPrescriptionUpload: false,
        },
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  const submitIntake = async () => {
    if (!sessionId) return;
    setIntakeError("");
    const customerName = (intakeDraft.customer_name ?? "").trim();
    const customerPhone = (intakeDraft.customer_phone ?? "").trim();
    const main = (intakeDraft.main_concern ?? "").trim();
    if (!customerName) {
      setIntakeError("Name is required.");
      return;
    }
    if (!customerPhone || !isValidE164(customerPhone)) {
      setIntakeError("Phone number must be in international format (E.164), e.g. +15551234567.");
      return;
    }
    if (!main || main.length > 200) {
      setIntakeError("Main concern must be 1-200 characters.");
      return;
    }
    setIsSubmittingIntake(true);
    try {
      const res = await api.post(
        `/chat/sessions/${sessionId}/escalate`,
        {
          customer_name: customerName,
          customer_phone: customerPhone,
          age_range: intakeDraft.age_range,
          main_concern: main,
          how_long: intakeDraft.how_long,
          current_medications: intakeDraft.current_medications || null,
          allergies: intakeDraft.allergies || null,
        },
        { headers: chatId ? { "X-Chat-ID": chatId } : {} }
      );
      setMessages((prev) => [
        ...prev.filter((m) => !m.intakeForm),
        {
          id: `system-${Date.now()}`,
          senderType: "SYSTEM",
          text: res.data?.system_message ?? "Escalated to pharmacist",
          timestamp: new Date(),
        },
      ]);
      setIsEscalated(true);
    } catch (err) {
      setIntakeError(err?.response?.data?.detail ?? "Failed to start consultation.");
    } finally {
      setIsSubmittingIntake(false);
    }
  };

  const handleSuggestionClick = (suggestion, context = {}) => {
    const normalized = (suggestion ?? "").toLowerCase();
    const searchMatch = String(suggestion ?? "").trim().match(/^search\s+(?:for\s+)?(.+)$/i);
    if (searchMatch && searchMatch[1]) {
      handleSend(searchMatch[1].trim());
      return;
    }
    if (normalized.includes("appointment")) {
      const today = new Date().toISOString().slice(0, 10);
      setApptForm({
        customer_name: "",
        customer_phone: "",
        customer_email: "",
        type: "Consultation",
        scheduled_time: "",
        vaccine_name: "",
        notes: "",
      });
      setApptDate(today);
      setApptSlots([]);
      fetchApptSlots(today);
      setApptError("");
      setMessages((prev) => [
        ...prev.filter((m) => !m.appointmentForm),
        {
          id: `bot-appt-form-${Date.now()}`,
          senderType: "AI",
          text: "Please fill your details to book an appointment:",
          appointmentForm: true,
          timestamp: new Date(),
          allowPrescriptionUpload: false,
        },
      ]);
      return;
    }
    if (normalized.includes("contact")) {
      navigate("/contact");
      return;
    }
    if (normalized.includes("shop")) {
      navigate("/shop");
      return;
    }

    const intent = String(context.intent ?? "");
    const sourceText = String(context.messageText ?? "");
    const looksLikeMedicineToken =
      /^[a-z][a-z\s-]{2,40}$/i.test(String(suggestion ?? "").trim()) &&
      !/(\bday\b|<|>|\bgetting worse\b|\bmild\b|\bmoderate\b|\bsevere\b|\byes\b|\bno\b)/i.test(
        String(suggestion ?? "")
      );
    const shouldForceSearch =
      /^MEDICINE/i.test(intent) ||
      /did you mean/i.test(sourceText) ||
      /(medicine|product)\s+card/i.test(sourceText);

    if (shouldForceSearch && looksLikeMedicineToken) {
      handleSend(`Search ${String(suggestion ?? "").trim()}`);
      return;
    }

    handleSend(suggestion);
  };

  const getAppointmentTrackingCode = () => {
    if (typeof window === "undefined") return "";
    return (localStorage.getItem(APPOINTMENT_TRACKING_CODE_KEY) ?? "").trim();
  };

  const openApptSlots = useMemo(() => apptSlots.filter((slot) => !slot.booked), [apptSlots]);

  const fetchApptSlots = async (dateValue) => {
    if (!dateValue) return;
    setIsLoadingApptSlots(true);
    setApptSlotsError("");
    try {
      const res = await api.get("/appointments/availability/public", { params: { date: dateValue } });
      const slots = Array.isArray(res.data?.slots) ? res.data.slots : [];
      setApptSlots(slots);
    } catch (err) {
      setApptSlots([]);
      setApptSlotsError(err?.response?.data?.detail ?? "Unable to load available slots.");
    } finally {
      setIsLoadingApptSlots(false);
    }
  };

  const resolvePharmacyId = async () => {
    const knownId = Number(pharmacy?.id ?? 0);
    if (knownId > 0) return knownId;
    try {
      const res = await api.get("/pharmacies/current");
      return Number(res.data?.id ?? 0);
    } catch {
      return 0;
    }
  };

  const handleApptDateChange = (event) => {
    const next = event.target.value;
    setApptDate(next);
    setApptForm((prev) => ({ ...prev, scheduled_time: "" }));
    fetchApptSlots(next);
  };

  const handleAppointmentSubmit = async (event) => {
    event.preventDefault();
    if (isSubmittingAppt) return;
    const name = apptForm.customer_name.trim();
    const phone = apptForm.customer_phone.trim();
    const email = apptForm.customer_email.trim();
    const type = apptForm.type.trim();
    const scheduled = apptForm.scheduled_time;
    const vaccineName = type === "Vaccination" ? apptForm.vaccine_name.trim() : "";

    if (!name || !phone || !type || !scheduled) {
      setApptError("Please fill name, phone, type, and date/time.");
      return;
    }
    if (!isValidE164(phone)) {
      setApptError("Phone must be in E.164 format, e.g. +15551234567.");
      return;
    }
    if (type === "Vaccination" && !vaccineName) {
      setApptError("Please enter the vaccine name.");
      return;
    }

    setApptError("");
    setIsSubmittingAppt(true);
    try {
      const payload = {
        customer_name: name,
        customer_phone: phone,
        customer_email: email || null,
        type,
        scheduled_time: scheduled,
        vaccine_name: type === "Vaccination" ? vaccineName : null,
      };
      const trackingCode = getAppointmentTrackingCode();
      const res = await api.post("/appointments", payload, {
        headers: trackingCode ? { "X-Customer-ID": trackingCode } : {},
      });
      const nextTracking = (res.data?.tracking_code ?? "").trim();
      if (typeof window !== "undefined" && nextTracking) {
        localStorage.setItem(APPOINTMENT_TRACKING_CODE_KEY, nextTracking);
      }
      setMessages((prev) => [
        ...prev.filter((m) => !m.appointmentForm),
        {
          id: `bot-appt-${Date.now()}`,
          senderType: "AI",
          text: `Appointment request submitted (#${res.data?.id ?? "?"}). A pharmacist will confirm it. You can review it in the appointments page.`,
          timestamp: new Date(),
          allowPrescriptionUpload: false,
          quickReplies: ["Book appointment", "Contact pharmacy"],
        },
      ]);
      setApptForm({
        customer_name: "",
        customer_phone: "",
        customer_email: "",
        type: "Consultation",
        scheduled_time: "",
        vaccine_name: "",
        notes: "",
      });
    } catch (err) {
      if (err?.response?.status === 409) {
        setApptError("That slot was just taken. Please pick another time.");
        setApptForm((prev) => ({ ...prev, scheduled_time: "" }));
        fetchApptSlots(apptDate);
      } else {
        setApptError(err?.response?.data?.detail ?? "Couldn't submit the appointment. Please try again.");
      }
    } finally {
      setIsSubmittingAppt(false);
    }
  };

  const handleRxOrderSubmit = async (event, medicineId) => {
    event.preventDefault();
    if (isPlacingRxOrder) return;
    const name = rxForm.customer_name.trim();
    const phone = rxForm.customer_phone.trim();
    const address = rxForm.customer_address.trim();
    const notes = rxForm.customer_notes.trim() ? rxForm.customer_notes.trim() : null;

    if (!name || !phone || !address) {
      setRxFormError("Please fill name, phone, and address.");
      return;
    }
    if (!isValidE164(phone)) {
      setRxFormError("Phone must be in E.164 format, e.g. +15551234567.");
      return;
    }
    setRxFormError("");

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
    if (!draftPrescriptionTokens.length) {
      setMessages((prev) => [
        ...prev,
        {
          id: `bot-action-${Date.now()}`,
          senderType: "AI",
          text: "Please upload your prescription first.",
          timestamp: new Date(),
          allowPrescriptionUpload: true,
        },
      ]);
      return;
    }

    setIsPlacingRxOrder(true);
    try {
      const res = await api.post("/orders/rx", {
        customer_name: name,
        customer_phone: phone,
        customer_address: address,
        customer_notes: notes,
        medicine_id: Number(medicineId),
        quantity: 1,
        draft_prescription_tokens: draftPrescriptionTokens,
      });
      setRxOrderDraft({ medicineId: null, showForm: false });
      setRxForm({ customer_name: "", customer_phone: "", customer_address: "", customer_notes: "" });
      setMessages((prev) => [
        ...prev.filter((m) => !m.rxOrderForm),
        {
          id: `bot-action-${Date.now()}`,
          senderType: "AI",
          text: `Rx order placed (Order #${res.data?.order_id ?? "?"}). A pharmacist can now review and approve your prescription.`,
          timestamp: new Date(),
          allowPrescriptionUpload: false,
          quickReplies: ["Contact pharmacy"],
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `bot-action-${Date.now()}`,
          senderType: "AI",
          text: err?.response?.data?.detail ?? "Couldn't place the Rx order. Please try again.",
          timestamp: new Date(),
          allowPrescriptionUpload: false,
        },
      ]);
    } finally {
      setIsPlacingRxOrder(false);
    }
  };

  const handleUpload = async (event) => {
    event.preventDefault();
    setUploadState((prev) => ({ ...prev, status: "", error: "" }));
    if (!uploadState.files || uploadState.files.length === 0) {
      setUploadState((prev) => ({ ...prev, error: "Select one or more files (images or PDF)." }));
      return;
    }

    const formData = new FormData();
    uploadState.files.forEach((file) => {
      formData.append("files", file);
    });

    try {
      const res = await api.post("/prescriptions/draft", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const items = Array.isArray(res.data) ? res.data : [];
      const tokens = items.map((item) => item?.draft_token).filter(Boolean);
      if (typeof window !== "undefined" && tokens.length > 0) {
        localStorage.setItem("customer_prescription_draft_tokens", JSON.stringify(tokens));
      }
      setUploadState((prev) => ({
        ...prev,
        status: `Uploaded ${items.length || uploadState.files.length} file(s).`,
        error: "",
        tokens,
      }));
      setMessages((prev) => [
        ...prev,
        {
          id: `bot-prescription-${Date.now()}`,
          senderType: "AI",
          text:
            "Prescription received. Rx medicines are not added to cart. If you'd like, I can place the Rx order now so the pharmacist can approve it.",
          actions: rxOrderDraft.medicineId
            ? [
                {
                  type: "place_rx_order",
                  label: "Place Rx order",
                  medicine_id: rxOrderDraft.medicineId,
                },
              ]
            : [],
          timestamp: new Date(),
          allowPrescriptionUpload: false,
          quickReplies: ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
        },
      ]);
    } catch (err) {
      setUploadState((prev) => ({
        ...prev,
        error: err?.response?.data?.detail ?? "Upload failed.",
      }));
    }
  };

  const formatTime = (value) => {
    if (!value) return "";
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  if (!isOpen) return null;

  const containerClassName =
    placement === "frame"
      ? "absolute bottom-10 right-4 w-[92vw] sm:right-6 sm:w-96 max-w-[calc(100vw-2rem)]"
      : "fixed bottom-4 right-4 w-[92vw] sm:bottom-6 sm:right-6 sm:w-96 max-w-[calc(100vw-2rem)]";

  return (
    <div
      className={`${containerClassName} bg-white rounded-2xl shadow-2xl overflow-hidden z-50 flex flex-col h-[80vh] sm:h-[560px] max-h-[calc(100vh-6rem)]`}
    >
      <div className="bg-gradient-to-r from-[var(--brand-primary)] to-[var(--brand-primary-600)] text-white px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center">
            <Pill className="w-6 h-6 text-[var(--brand-primary)]" />
          </div>
          <div>
            <div>{isEscalated ? "Pharmacist Consultation" : "AI Assistant"}</div>
            <div className="text-xs opacity-90">
              {isEscalated ? "A pharmacist will reply here" : "Always here to help"}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={onClose} className="p-1 hover:bg-white/20 rounded-lg transition-colors">
            <Minimize2 className="w-5 h-5" />
          </button>
          <button type="button" onClick={onClose} className="p-1 hover:bg-white/20 rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-gray-50">
        {messages.map((message) => {
          const senderType = message.senderType ?? "AI";
          const isUser = senderType === "USER";
          const isSystem = senderType === "SYSTEM";
          const isPharmacist = senderType === "PHARMACIST";
          const isAi = senderType === "AI";
          const label = isUser ? "You" : isPharmacist ? "Pharmacist" : isAi ? "AI Assistant" : "System";
          const timeLabel = formatTime(message.timestamp);
          const actionLabels = Array.isArray(message.actions)
            ? message.actions.map((action) => String(action?.label ?? "")).filter(Boolean)
            : [];
          const excludeKeys = new Set(actionLabels.map((labelValue) => normalizeReplyKey(labelValue)));

          const suggestions = dedupeReplies(message.suggestions);
          const { context: quickRepliesRaw, global: globalReplies } = splitReplies(message.quickReplies, { excludeKeys });
          const quickReplies = dedupeAcross(suggestions, quickRepliesRaw);

          if (isSystem) {
            const systemText = String(message.text ?? "");
            const isClosed = systemText === "Consultation closed" || systemText === "Session expired due to inactivity";
            return (
              <div key={message.id} className="flex justify-center">
                <div className="max-w-[85%] text-center text-xs text-gray-600 bg-white border border-gray-200 px-3 py-2 rounded-xl shadow-sm">
                  <div className="text-[10px] uppercase tracking-wide text-gray-400">
                    {label}
                    {timeLabel ? ` - ${timeLabel}` : ""}
                  </div>
                  <div className="mt-1 whitespace-pre-line">{message.text}</div>
                  {isClosed ? (
                    <div className="mt-2 flex justify-center">
                      <button
                        type="button"
                        onClick={resetChatSession}
                        className="px-3 py-1.5 text-xs bg-white border border-slate-200 text-slate-700 rounded-lg hover:bg-slate-50"
                      >
                        Continue with AI
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            );
          }

          if (isUser) {
            return (
              <div key={message.id} className="flex justify-end">
                <div className="max-w-[85%] flex flex-col items-end">
                  <div className="text-[11px] text-gray-500 mb-1">
                    {label}
                    {timeLabel ? ` - ${timeLabel}` : ""}
                  </div>
                  <div className="bg-[var(--brand-accent)] text-white px-4 py-3 rounded-2xl rounded-tr-none shadow-sm whitespace-pre-line">
                    {message.text}
                  </div>
                </div>
              </div>
            );
          }

          const AvatarIcon = isPharmacist ? UserRound : Pill;
          const avatarClass = isPharmacist ? "bg-emerald-500" : "bg-[var(--brand-primary)]";

          return (
            <div key={message.id} className="flex items-start gap-3">
              <div className={`w-8 h-8 ${avatarClass} rounded-full flex items-center justify-center flex-shrink-0`}>
                <AvatarIcon className="w-4 h-4 text-white" />
              </div>
              <div className="flex-1">
                <div className="text-[11px] text-gray-500 mb-1">
                  {label}
                  {timeLabel ? ` - ${timeLabel}` : ""}
                </div>
                <div className="bg-white text-gray-800 px-4 py-3 rounded-2xl rounded-tl-none shadow-sm max-w-[85%] whitespace-pre-line">
                  {message.text}
                </div>
                {message.intakeForm ? (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      submitIntake();
                    }}
                    className="mt-3 space-y-2 max-w-[85%]"
                  >
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[11px] text-gray-600 mb-1">Full name</label>
                        <input
                          value={intakeDraft.customer_name}
                          onChange={(event) => setIntakeDraft((prev) => ({ ...prev, customer_name: event.target.value }))}
                          className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                          required
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-gray-600 mb-1">Phone</label>
                        <PhoneInput
                          value={intakeDraft.customer_phone}
                          onChange={(next) => setIntakeDraft((prev) => ({ ...prev, customer_phone: next }))}
                          className="bg-white"
                          placeholder="e.g. +15551234567"
                          required
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[11px] text-gray-600 mb-1">Age range</label>
                        <select
                          value={intakeDraft.age_range}
                          onChange={(event) => setIntakeDraft((prev) => ({ ...prev, age_range: event.target.value }))}
                          className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                        >
                          <option value="0-12">0-12</option>
                          <option value="13-17">13-17</option>
                          <option value="18-24">18-24</option>
                          <option value="25-34">25-34</option>
                          <option value="35-44">35-44</option>
                          <option value="45-54">45-54</option>
                          <option value="55-64">55-64</option>
                          <option value="65+">65+</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] text-gray-600 mb-1">How long</label>
                        <select
                          value={intakeDraft.how_long}
                          onChange={(event) => setIntakeDraft((prev) => ({ ...prev, how_long: event.target.value }))}
                          className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                        >
                          <option value="<1 day">&lt;1 day</option>
                          <option value="1-3 days">1-3 days</option>
                          <option value=">3 days">&gt;3 days</option>
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="block text-[11px] text-gray-600 mb-1">Main concern</label>
                      <input
                        value={intakeDraft.main_concern}
                        onChange={(event) =>
                          setIntakeDraft((prev) => ({ ...prev, main_concern: event.target.value.slice(0, 200) }))
                        }
                        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                        placeholder="Short summary (max 200 chars)"
                        required
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[11px] text-gray-600 mb-1">Current medications (optional)</label>
                        <input
                          value={intakeDraft.current_medications}
                          onChange={(event) =>
                            setIntakeDraft((prev) => ({ ...prev, current_medications: event.target.value }))
                          }
                          className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] text-gray-600 mb-1">Allergies (optional)</label>
                        <input
                          value={intakeDraft.allergies}
                          onChange={(event) => setIntakeDraft((prev) => ({ ...prev, allergies: event.target.value }))}
                          className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                        />
                      </div>
                    </div>
                    {intakeError ? <div className="text-xs text-red-600">{intakeError}</div> : null}
                    <div className="flex items-center gap-2">
                      <button
                        type="submit"
                        disabled={isSubmittingIntake}
                        className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm disabled:opacity-60"
                      >
                        {isSubmittingIntake ? "Starting..." : "Start consultation"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setMessages((prev) => prev.filter((m) => !m.intakeForm))}
                        className="px-4 py-2 rounded-lg border border-slate-200 text-sm text-gray-700 hover:bg-slate-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : null}
                {!isEscalated && isAi && suggestions && suggestions.length > 0 ? (
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    {suggestions.map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        onClick={() => handleSuggestionClick(suggestion, { intent: message.intent, messageText: message.text })}
                        className="px-3 py-2 text-xs sm:text-sm bg-white/80 border border-[var(--brand-primary)] text-[var(--brand-primary)] rounded-xl hover:bg-[var(--brand-primary)] hover:text-white transition-colors text-left"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                ) : null}
                {!isEscalated && isAi && message.actions && message.actions.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {message.actions.map((action, index) => (
                      <button
                        key={`${action.type}-${action.medicine_id ?? "x"}-${index}`}
                        type="button"
                        onClick={async () => {
                          if (action.type === "search_medicine") {
                            const query = String(action.payload?.query ?? "").trim() || String(action.label ?? "").trim();
                            if (query) {
                              const cleaned = query.replace(/^search\s+/i, "").trim();
                              handleSend(`Search ${cleaned}`);
                            }
                            return;
                          }
                          if (action.type === "escalate_to_pharmacist") {
                            setIntakeError("");
                            setMessages((prev) => [
                              ...prev.filter((m) => !m.intakeForm),
                              {
                                id: `intake-${Date.now()}`,
                                senderType: "AI",
                                text: "Before I connect you, please fill this quick form:",
                                timestamp: new Date(),
                                intakeForm: true,
                              },
                            ]);
                            return;
                          }
                          if (action.type === "book_appointment") {
                            const today = new Date().toISOString().slice(0, 10);
                            setApptForm({
                              customer_name: "",
                              customer_phone: "",
                              customer_email: "",
                              type: "Consultation",
                              scheduled_time: "",
                              vaccine_name: "",
                              notes: "",
                            });
                            setApptDate(today);
                            setApptSlots([]);
                            fetchApptSlots(today);
                            setApptError("");
                            setMessages((prev) => [
                              ...prev.filter((m) => !m.appointmentForm),
                              {
                                id: `bot-appt-form-${Date.now()}`,
                                senderType: "AI",
                                text: "Please fill your details to book an appointment:",
                                appointmentForm: true,
                                timestamp: new Date(),
                                allowPrescriptionUpload: false,
                              },
                            ]);
                            return;
                          }
                          if (action.type === "open_booking") {
                            navigate("/appointments");
                            return;
                          }
                          if (action.type === "place_rx_order" && action.medicine_id) {
                            setRxOrderDraft({ medicineId: Number(action.medicine_id), showForm: true });
                            setRxForm({ customer_name: "", customer_phone: "", customer_address: "", customer_notes: "" });
                            setRxFormError("");
                            setMessages((prev) => [
                              ...prev.filter((m) => !m.rxOrderForm),
                              {
                                id: `bot-action-${Date.now()}`,
                                senderType: "AI",
                                text: "Please fill your details to place the Rx order:",
                                rxOrderForm: { medicineId: Number(action.medicine_id) },
                                timestamp: new Date(),
                                allowPrescriptionUpload: false,
                              },
                            ]);
                            return;
                          }
                          if (action.type === "add_to_cart") {
                            const medicineId = Number(action.medicine_id ?? action.payload?.medicine_id ?? 0);
                            if (!medicineId) {
                              setMessages((prev) => [
                                ...prev,
                                {
                                  id: `bot-action-${Date.now()}`,
                                  senderType: "AI",
                                  text: "I couldn't identify the medicine to add. Please try again.",
                                  timestamp: new Date(),
                                  allowPrescriptionUpload: false,
                                },
                              ]);
                              return;
                            }
                            const resolvedPharmacyId = await resolvePharmacyId();
                            if (!resolvedPharmacyId) {
                              setMessages((prev) => [
                                ...prev,
                                {
                                  id: `bot-action-${Date.now()}`,
                                  senderType: "AI",
                                  text: "I couldn't load the pharmacy yet. Please refresh and try again.",
                                  timestamp: new Date(),
                                  allowPrescriptionUpload: false,
                                },
                              ]);
                              return;
                            }
                            try {
                              const res = await api.post(`/pharmacies/${resolvedPharmacyId}/cart/items`, {
                                medicine_id: medicineId,
                                quantity: Number(action.payload?.quantity ?? 1),
                              });
                              const item = res.data ?? {};
                              addItem({
                                item_type: "medicine",
                                item_id: item.medicine_id,
                                name: item.name,
                                price: item.price,
                              });
                              setMessages((prev) => [
                                ...prev,
                                {
                                  id: `bot-action-${Date.now()}`,
                                  senderType: "AI",
                                  text: "Added. Do you want another medicine or any other service?",
                                  timestamp: new Date(),
                                  allowPrescriptionUpload: false,
                                  quickReplies: ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                                },
                              ]);
                            } catch (err) {
                              setMessages((prev) => [
                                ...prev,
                                {
                                  id: `bot-action-${Date.now()}`,
                                  senderType: "AI",
                                  text: err?.response?.data?.detail ?? "I couldn't add that to the cart. Please try again.",
                                  timestamp: new Date(),
                                  allowPrescriptionUpload: false,
                                },
                              ]);
                            }
                            return;
                          }
                          if (action.type === "upload_prescription") {
                            setRxOrderDraft({ medicineId: Number(action.medicine_id ?? 0) || null });
                            setMessages((prev) => [
                              ...prev,
                              {
                                id: `bot-action-${Date.now()}`,
                                senderType: "AI",
                                text: "Please upload your prescription below.",
                                timestamp: new Date(),
                                allowPrescriptionUpload: true,
                              },
                            ]);
                            return;
                          }
                        }}
                        className="px-3 py-1.5 text-sm bg-white/80 border border-[var(--brand-primary)] text-[var(--brand-primary)] rounded-full hover:bg-[var(--brand-primary)] hover:text-white transition-colors"
                      >
                        {action.label ?? action.type}
                      </button>
                    ))}
                  </div>
                ) : null}
                {isAi && message.appointmentForm ? (
                  <form onSubmit={handleAppointmentSubmit} className="mt-3 space-y-2 max-w-[85%]">
                    <input
                      value={apptForm.customer_name}
                      onChange={(event) => setApptForm((prev) => ({ ...prev, customer_name: event.target.value }))}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                      placeholder="Full name"
                      required
                    />
                    <PhoneInput
                      value={apptForm.customer_phone}
                      onChange={(next) => setApptForm((prev) => ({ ...prev, customer_phone: next }))}
                      className="bg-white"
                      placeholder="Phone number"
                      required
                    />
                    <input
                      type="email"
                      value={apptForm.customer_email}
                      onChange={(event) => setApptForm((prev) => ({ ...prev, customer_email: event.target.value }))}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                      placeholder="Email for reminders (optional)"
                    />
                    <select
                      value={apptForm.type}
                      onChange={(event) => setApptForm((prev) => ({ ...prev, type: event.target.value }))}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                    >
                      <option value="Consultation">Consultation</option>
                      <option value="Medication Review">Medication review</option>
                      <option value="Vaccination">Vaccination</option>
                    </select>
                    <input
                      type="date"
                      value={apptDate}
                      onChange={handleApptDateChange}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                      required
                    />
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-xs text-slate-600">
                        <span>Available slots</span>
                        {isLoadingApptSlots ? <span>Loading...</span> : null}
                      </div>
                      {apptSlotsError ? <div className="text-xs text-red-600">{apptSlotsError}</div> : null}
                      {openApptSlots.length === 0 && !isLoadingApptSlots ? (
                        <div className="text-xs text-slate-500">No open slots for this day.</div>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {openApptSlots.map((slot) => {
                            const start = new Date(slot.start);
                            const label = start.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
                            const isSelected = apptForm.scheduled_time === slot.start;
                            return (
                              <button
                                key={slot.start}
                                type="button"
                                onClick={() => setApptForm((prev) => ({ ...prev, scheduled_time: slot.start }))}
                                className={`px-3 py-1.5 rounded-lg border text-xs transition ${
                                  isSelected
                                    ? "border-blue-600 bg-blue-600 text-white"
                                    : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                                }`}
                              >
                                {label}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                    {apptForm.type === "Vaccination" ? (
                      <input
                        value={apptForm.vaccine_name}
                        onChange={(event) => setApptForm((prev) => ({ ...prev, vaccine_name: event.target.value }))}
                        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                        placeholder="Vaccine name (Flu, COVID-19, etc.)"
                        required
                      />
                    ) : null}
                    {apptError ? <div className="text-xs text-red-600">{apptError}</div> : null}
                    <button
                      type="submit"
                      disabled={isSubmittingAppt}
                      className="w-full py-2.5 bg-[var(--brand-accent)] text-white rounded-xl hover:opacity-95 disabled:bg-gray-300 disabled:cursor-not-allowed"
                    >
                      {isSubmittingAppt ? "Submitting..." : "Reserve appointment"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setMessages((prev) => prev.filter((m) => !m.appointmentForm))}
                      className="w-full py-2.5 border border-slate-200 rounded-xl text-gray-700 hover:bg-slate-50"
                    >
                      Cancel
                    </button>
                  </form>
                ) : null}
                {isAi && message.rxOrderForm && message.rxOrderForm.medicineId ? (
                  <form
                    onSubmit={(event) => handleRxOrderSubmit(event, message.rxOrderForm.medicineId)}
                    className="mt-3 space-y-2 max-w-[85%]"
                  >
                    <input
                      value={rxForm.customer_name}
                      onChange={(event) => setRxForm((prev) => ({ ...prev, customer_name: event.target.value }))}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                      placeholder="Full name"
                      required
                    />
                    <PhoneInput
                      value={rxForm.customer_phone}
                      onChange={(next) => setRxForm((prev) => ({ ...prev, customer_phone: next }))}
                      className="bg-white"
                      placeholder="Phone number"
                      required
                    />
                    <textarea
                      value={rxForm.customer_address}
                      onChange={(event) => setRxForm((prev) => ({ ...prev, customer_address: event.target.value }))}
                      rows="2"
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                      placeholder="Delivery address"
                      required
                    />
                    <textarea
                      value={rxForm.customer_notes}
                      onChange={(event) => setRxForm((prev) => ({ ...prev, customer_notes: event.target.value }))}
                      rows="2"
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                      placeholder="Notes (optional)"
                    />
                    {rxFormError ? <div className="text-xs text-red-600">{rxFormError}</div> : null}
                    <button
                      type="submit"
                      disabled={isPlacingRxOrder}
                      className="w-full py-2.5 bg-[var(--brand-accent)] text-white rounded-xl hover:opacity-95 disabled:bg-gray-300 disabled:cursor-not-allowed"
                    >
                      {isPlacingRxOrder ? "Placing Rx order..." : "Place Rx order"}
                    </button>
                  </form>
                ) : null}
                {!isEscalated && isAi && quickReplies && quickReplies.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {quickReplies.map((reply) => {
                      const isSearch = /^search\\s+/i.test(reply);
                      return (
                        <button
                          key={reply}
                          type="button"
                          onClick={() => handleSuggestionClick(reply, { intent: message.intent, messageText: message.text })}
                          className={`px-3 py-2 text-xs sm:text-sm rounded-xl transition-colors text-left ${
                            isSearch
                              ? "bg-white border border-[var(--brand-primary)] text-[var(--brand-primary)] hover:bg-[var(--brand-primary)] hover:text-white"
                              : "bg-white/80 border border-slate-200 text-gray-700 hover:bg-slate-100"
                          }`}
                        >
                          {reply}
                        </button>
                      );
                    })}
                  </div>
                ) : null}
                {!isEscalated && isAi && globalReplies && globalReplies.length > 0 ? (
                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={() => setShowGlobalActions((prev) => !prev)}
                      className="text-xs sm:text-sm text-slate-600 hover:text-slate-900 underline underline-offset-4"
                    >
                      {showGlobalActions ? "Hide options" : "More options"}
                    </button>
                    {showGlobalActions ? (
                      <div className="mt-2 grid grid-cols-2 gap-2">
                        {globalReplies.map((reply) => (
                          <button
                            key={reply}
                            type="button"
                            onClick={() => handleSuggestionClick(reply, { intent: message.intent, messageText: message.text })}
                            className="px-3 py-2 text-xs sm:text-sm bg-white/80 border border-slate-200 text-gray-700 rounded-xl hover:bg-slate-100 transition-colors text-left"
                          >
                            {reply}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {!isEscalated && isAi && message.freshness && (message.freshness.dataLastUpdatedAt || message.freshness.indexedAt) ? (
                  <div className="mt-2 text-[11px] text-gray-500">
                    {message.freshness.dataLastUpdatedAt
                      ? `Data last updated: ${new Date(message.freshness.dataLastUpdatedAt).toLocaleString()}`
                      : "Data last updated: -"}
                    {" - "}
                    {message.freshness.indexedAt
                      ? `Indexed at: ${new Date(message.freshness.indexedAt).toLocaleString()}`
                      : "Indexed at: -"}
                  </div>
                ) : null}
                {isAi && message.allowPrescriptionUpload ? (
                  <form onSubmit={handleUpload} className="mt-3 space-y-2">
                    <input
                      type="file"
                      accept="image/*,application/pdf"
                      multiple
                      onChange={(event) =>
                        setUploadState((prev) => ({ ...prev, files: Array.from(event.target.files ?? []) }))
                      }
                      className="w-full text-sm"
                    />
                    {uploadState.error ? <p className="text-xs text-red-600">{uploadState.error}</p> : null}
                    {uploadState.status ? <p className="text-xs text-green-600">{uploadState.status}</p> : null}
                    {uploadState.tokens && uploadState.tokens.length > 0 ? (
                      <p className="text-[11px] text-gray-600">
                        Saved on this device. You can also keep this reference: {uploadState.tokens[0]}
                      </p>
                    ) : null}
                    <button
                      type="submit"
                      className="px-3 py-2 text-sm bg-[var(--brand-primary)] text-white rounded-lg hover:bg-[var(--brand-primary-600)] transition-colors"
                    >
                      Upload prescription
                    </button>
                  </form>
                ) : null}
              </div>
            </div>
          );
        })}

        {isTyping ? (
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 bg-[var(--brand-primary)] rounded-full flex items-center justify-center flex-shrink-0">
              <Pill className="w-4 h-4 text-white" />
            </div>
            <div>
              <div className="text-[11px] text-gray-500 mb-1">AI Assistant</div>
              <div className="bg-white px-4 py-3 rounded-2xl shadow-sm">
                <div className="flex gap-1">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                  <div
                    className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                    style={{ animationDelay: "0.1s" }}
                  ></div>
                  <div
                    className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                    style={{ animationDelay: "0.2s" }}
                  ></div>
                </div>
              </div>
            </div>
          </div>
        ) : null}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t bg-white p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            onKeyDown={(event) => (event.key === "Enter" ? handleSend() : null)}
            placeholder="Type your message..."
            className="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)] text-sm"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!inputValue.trim()}
            className="p-3 bg-[var(--brand-primary)] text-white rounded-xl hover:bg-[var(--brand-primary-600)] disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-2 text-center">Powered by AI - Available 24/7</p>
        <p className="text-[11px] text-gray-500 mt-1 text-center">
          Not medical advice. For emergencies, call local emergency services.
        </p>
      </div>
    </div>
  );
}
