import ReactDOM from "react-dom/client";
import { Component } from "react";
import App from "./App";
import "./index.css";
import "./styles/index.css";
import { AuthProvider } from "./context/AuthContext";
import { TenantProvider } from "./context/TenantContext";

class AppErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("Portal crashed:", error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    const message = this.state.error?.message ?? String(this.state.error ?? "Unknown error");
    return (
      <div style={{ padding: 24, fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif" }}>
        <div style={{ maxWidth: 900, margin: "0 auto", background: "white", border: "1px solid #e2e8f0", borderRadius: 16, padding: 20 }}>
          <h1 style={{ fontSize: 22, margin: 0, color: "#0f172a" }}>Something went wrong</h1>
          <p style={{ marginTop: 8, color: "#475569" }}>
            The portal hit an unexpected error. Open DevTools Console for details, then refresh.
          </p>
          <pre style={{ marginTop: 12, whiteSpace: "pre-wrap", color: "#b91c1c", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 12, padding: 12 }}>
            {message}
          </pre>
          <div style={{ display: "flex", gap: 12, marginTop: 16 }}>
            <button type="button" onClick={() => window.location.reload()} style={{ padding: "10px 14px", borderRadius: 12, border: "1px solid #e2e8f0", background: "#2563eb", color: "white" }}>
              Reload
            </button>
            <button type="button" onClick={() => localStorage.removeItem("token")} style={{ padding: "10px 14px", borderRadius: 12, border: "1px solid #e2e8f0", background: "white", color: "#0f172a" }}>
              Clear token
            </button>
          </div>
        </div>
      </div>
    );
  }
}

const installGlobalErrorOverlay = () => {
  const show = (title, detail) => {
    try {
      const root = document.getElementById("root");
      if (!root) return;
      const msg = String(detail?.message ?? detail ?? "");
      root.innerHTML = `
        <div style="padding:24px;font-family:system-ui,-apple-system,Segoe UI,sans-serif;">
          <div style="max-width:900px;margin:0 auto;background:white;border:1px solid #e2e8f0;border-radius:16px;padding:20px;">
            <h1 style="font-size:22px;margin:0;color:#0f172a;">${title}</h1>
            <p style="margin-top:8px;color:#475569;">Open DevTools Console for details, then refresh.</p>
            <pre style="margin-top:12px;white-space:pre-wrap;color:#b91c1c;background:#fef2f2;border:1px solid #fecaca;border-radius:12px;padding:12px;">${msg}</pre>
          </div>
        </div>
      `;
    } catch {
      // ignore
    }
  };

  window.addEventListener("error", (event) => show("A script error occurred", event?.error ?? event?.message));
  window.addEventListener("unhandledrejection", (event) => show("An async error occurred", event?.reason));
};

installGlobalErrorOverlay();

ReactDOM.createRoot(document.getElementById("root")).render(
  <AuthProvider>
    <TenantProvider>
      <AppErrorBoundary>
        <App />
      </AppErrorBoundary>
    </TenantProvider>
  </AuthProvider>
);
