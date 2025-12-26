import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Minimize2, Pill, Send, X } from "lucide-react";
import api from "../../api/axios";

const CHAT_ID_KEY = "customer_chat_id";

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
        { message: trimmed },
        { headers: chatId ? { "X-Chat-ID": chatId } : {} }
      );
      const nextChatId = res.data?.customer_id ?? chatId;
      if (nextChatId && nextChatId !== chatId) {
        setChatId(nextChatId);
        if (typeof window !== "undefined") {
          localStorage.setItem(CHAT_ID_KEY, nextChatId);
        }
      }

      const answer = res.data?.answer ?? "";
      const botMessage = {
        id: `bot-${res.data?.interaction_id ?? Date.now()}`,
        type: "bot",
        text: answer,
        timestamp: new Date(res.data?.created_at ?? Date.now()),
        allowPrescriptionUpload: shouldOfferPrescriptionUpload(answer),
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
      navigate("/appointments");
      return;
    }
    setInputValue(suggestion);
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
          text: "Prescription received. A pharmacist can review it once you place your medicine order.",
          timestamp: new Date(),
          allowPrescriptionUpload: false,
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
    <div className={`${containerClassName} bg-white rounded-2xl shadow-2xl overflow-hidden z-50 flex flex-col h-[560px] max-h-[calc(100vh-6rem)]`}>
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
                      {uploadState.error ? (
                        <p className="text-xs text-red-600">{uploadState.error}</p>
                      ) : null}
                      {uploadState.status ? (
                        <p className="text-xs text-green-600">{uploadState.status}</p>
                      ) : null}
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
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0.1s" }}></div>
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0.2s" }}></div>
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
