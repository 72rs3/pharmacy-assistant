import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Minimize2, Pill, Send, X } from "lucide-react";
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

const shouldOfferPrescriptionUpload = (text) => {
  const normalized = (text ?? "").toLowerCase();
  return normalized.includes("prescription required") || normalized.includes("requires prescription");
};

export default function CustomerChatWidget({ isOpen, onClose, brandName = "Sunr", placement = "viewport" }) {
  const navigate = useNavigate();
  const { addItem } = useCustomerCart();
  const { pharmacy } = useTenant() ?? {};
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
  const [apptError, setApptError] = useState("");
  const [isSubmittingAppt, setIsSubmittingAppt] = useState(false);
  const [messages, setMessages] = useState([
    {
      id: "welcome",
      type: "bot",
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
    if (!isOpen || !chatId) return;
    let isActive = true;

    const loadHistory = async () => {
      try {
        const res = await api.get("/ai/chat/my", {
          headers: { "X-Chat-ID": chatId },
        });
        if (!isActive) return;
        const items = res.data ?? [];
        const history = items.flatMap((item) => {
          const botText = item.ai_response ?? "";
          return [
            {
              id: `user-${item.id}`,
              type: "user",
              text: item.customer_query,
              timestamp: new Date(item.created_at),
            },
            {
              id: `bot-${item.id}`,
              type: "bot",
              text: botText,
              timestamp: new Date(item.created_at),
              allowPrescriptionUpload: shouldOfferPrescriptionUpload(botText),
            },
            item.owner_reply
              ? {
                  id: `owner-${item.id}`,
                  type: "bot",
                  text: `Pharmacist reply: ${item.owner_reply}`,
                  timestamp: new Date(item.owner_replied_at ?? item.created_at),
                  allowPrescriptionUpload: false,
                }
              : null,
          ].filter(Boolean);
        });
        setMessages((prev) => [prev[0], ...history]);
      } catch {
        // Keep existing messages on failure.
      }
    };

    loadHistory();
    return () => {
      isActive = false;
    };
  }, [chatId, isOpen]);

  const handleSend = async () => {
    const trimmed = inputValue.trim();
    if (!trimmed) return;

    const userMessage = {
      id: `user-${Date.now()}`,
      type: "user",
      text: trimmed,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setIsTyping(true);

    try {
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
        type: "bot",
        text: answer,
        timestamp: new Date(res.data?.created_at ?? Date.now()),
        intent,
        allowPrescriptionUpload: shouldOfferPrescriptionUpload(answer),
        freshness: includeFreshness ? { dataLastUpdatedAt, indexedAt } : null,
        actions: Array.isArray(res.data?.actions) ? res.data.actions : [],
        cards,
        quickReplies: Array.isArray(res.data?.quick_replies) ? res.data.quick_replies : [],
      };
      setMessages((prev) => [...prev, botMessage]);

    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `bot-error-${Date.now()}`,
          type: "bot",
          text: "Sorry, I could not reach the assistant right now. Please try again.",
          timestamp: new Date(),
          allowPrescriptionUpload: false,
        },
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleSuggestionClick = (suggestion) => {
    const normalized = (suggestion ?? "").toLowerCase();
    if (normalized.includes("appointment")) {
      setApptForm({
        customer_name: "",
        customer_phone: "",
        customer_email: "",
        type: "Consultation",
        scheduled_time: "",
        vaccine_name: "",
        notes: "",
      });
      setApptError("");
      setMessages((prev) => [
        ...prev.filter((m) => !m.appointmentForm),
        {
          id: `bot-appt-form-${Date.now()}`,
          type: "bot",
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
    setInputValue(suggestion);
  };

  const getAppointmentTrackingCode = () => {
    if (typeof window === "undefined") return "";
    return (localStorage.getItem(APPOINTMENT_TRACKING_CODE_KEY) ?? "").trim();
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
          type: "bot",
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
      setApptError(err?.response?.data?.detail ?? "Couldn't submit the appointment. Please try again.");
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
          type: "bot",
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
          type: "bot",
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
          type: "bot",
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
          type: "bot",
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

  if (!isOpen) return null;

  const containerClassName =
    placement === "frame"
      ? "absolute bottom-10 right-6 w-96 max-w-[calc(100vw-3rem)]"
      : "fixed bottom-6 right-6 w-96 max-w-[calc(100vw-3rem)]";

  return (
    <div
      className={`${containerClassName} bg-white rounded-2xl shadow-2xl overflow-hidden z-50 flex flex-col h-[560px] max-h-[calc(100vh-6rem)]`}
    >
      <div className="bg-gradient-to-r from-[var(--brand-primary)] to-[var(--brand-primary-600)] text-white px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center">
            <Pill className="w-6 h-6 text-[var(--brand-primary)]" />
          </div>
          <div>
            <div>AI Assistant</div>
            <div className="text-xs opacity-90">Always here to help</div>
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
        {messages.map((message) => (
          <div key={message.id}>
            {message.type === "bot" ? (
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 bg-[var(--brand-primary)] rounded-full flex items-center justify-center flex-shrink-0">
                  <Pill className="w-4 h-4 text-white" />
                </div>
                <div className="flex-1">
                  <div className="bg-white text-gray-800 px-4 py-3 rounded-2xl rounded-tl-none shadow-sm max-w-[85%] whitespace-pre-line">
                    {message.text}
                  </div>
                  {message.suggestions && message.suggestions.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {message.suggestions.map((suggestion) => (
                        <button
                          key={suggestion}
                          type="button"
                          onClick={() => handleSuggestionClick(suggestion)}
                          className="px-3 py-1.5 text-sm bg-white/80 border border-[var(--brand-primary)] text-[var(--brand-primary)] rounded-full hover:bg-[var(--brand-primary)] hover:text-white transition-colors"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {message.cards && message.cards.length > 0 ? (
                    <div className="mt-3 space-y-2 max-w-[85%]">
                      {message.cards.map((card) => (
                        <div key={card.medicine_id} className="bg-white/70 border border-slate-200 rounded-xl p-3">
                          <div className="text-sm font-semibold text-gray-900">{card.name}</div>
                          <div className="text-xs text-gray-600 mt-1">
                            {card.dosage ? `Dosage: ${card.dosage} - ` : ""}
                            {card.rx ? "Rx required" : "OTC"} - Stock: {Number(card.stock ?? 0)}
                          </div>
                          <div className="text-xs text-gray-600 mt-1">
                            {card.price != null ? `Price: ${Number(card.price).toFixed(2)}` : "Price: -"} -{" "}
                            {card.updated_at ? `Updated: ${new Date(card.updated_at).toLocaleString()}` : "Updated: -"}
                          </div>
                          {card.indexed_at ? (
                            <div className="text-[11px] text-gray-500 mt-1">
                              Indexed: {new Date(card.indexed_at).toLocaleString()}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {message.actions && message.actions.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {message.actions.map((action, index) => (
                        <button
                          key={`${action.type}-${action.medicine_id ?? "x"}-${index}`}
                          type="button"
                          onClick={() => {
                            if (action.type === "book_appointment") {
                              setApptForm({
                                customer_name: "",
                                customer_phone: "",
                                customer_email: "",
                                type: "Consultation",
                                scheduled_time: "",
                                vaccine_name: "",
                                notes: "",
                              });
                              setApptError("");
                              setMessages((prev) => [
                                ...prev.filter((m) => !m.appointmentForm),
                                {
                                  id: `bot-appt-form-${Date.now()}`,
                                  type: "bot",
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
                                  type: "bot",
                                  text: "Please fill your details to place the Rx order:",
                                  rxOrderForm: { medicineId: Number(action.medicine_id) },
                                  timestamp: new Date(),
                                  allowPrescriptionUpload: false,
                                },
                              ]);
                              return;
                            }
                            if (action.type === "add_to_cart" && action.medicine_id) {
                              const resolvedPharmacyId = Number(pharmacy?.id ?? 0);
                              api
                                .post(`/pharmacies/${resolvedPharmacyId}/cart/items`, {
                                  medicine_id: Number(action.medicine_id),
                                  quantity: Number(action.payload?.quantity ?? 1),
                                })
                                .then((res) => {
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
                                      type: "bot",
                                      text: "Added. Do you want another medicine or any other service?",
                                      timestamp: new Date(),
                                      allowPrescriptionUpload: false,
                                      quickReplies: ["Search another medicine", "Shop OTC products", "Book appointment", "Contact pharmacy"],
                                    },
                                  ]);
                                })
                                .catch(() => {
                                  setMessages((prev) => [
                                    ...prev,
                                    {
                                      id: `bot-action-${Date.now()}`,
                                      type: "bot",
                                      text: "I couldn't add that to the cart. Please try again.",
                                      timestamp: new Date(),
                                      allowPrescriptionUpload: false,
                                    },
                                  ]);
                                });
                              return;
                            }
                            if (action.type === "upload_prescription") {
                              setRxOrderDraft({ medicineId: Number(action.medicine_id ?? 0) || null });
                              setMessages((prev) => [
                                ...prev,
                                {
                                  id: `bot-action-${Date.now()}`,
                                  type: "bot",
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
                  {message.appointmentForm ? (
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
                        type="datetime-local"
                        value={apptForm.scheduled_time}
                        onChange={(event) => setApptForm((prev) => ({ ...prev, scheduled_time: event.target.value }))}
                        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                        required
                      />
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
                  {message.rxOrderForm && message.rxOrderForm.medicineId ? (
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
                  {message.quickReplies && message.quickReplies.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {message.quickReplies.map((reply) => (
                        <button
                          key={reply}
                          type="button"
                          onClick={() => handleSuggestionClick(reply)}
                          className="px-3 py-1.5 text-sm bg-white/80 border border-slate-200 text-gray-700 rounded-full hover:bg-slate-100 transition-colors"
                        >
                          {reply}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {message.freshness && (message.freshness.dataLastUpdatedAt || message.freshness.indexedAt) ? (
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
                  {message.allowPrescriptionUpload ? (
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
            ) : (
              <div className="flex justify-end">
                <div className="bg-[var(--brand-accent)] text-white px-4 py-3 rounded-2xl rounded-tr-none shadow-sm max-w-[85%]">
                  {message.text}
                </div>
              </div>
            )}
          </div>
        ))}

        {isTyping ? (
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 bg-[var(--brand-primary)] rounded-full flex items-center justify-center flex-shrink-0">
              <Pill className="w-4 h-4 text-white" />
            </div>
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
