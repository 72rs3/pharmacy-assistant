import { useMemo, useState } from "react";
import { MessageCircle } from "lucide-react";
import CustomerNav from "./CustomerNav";
import CustomerChatWidget from "./CustomerChatWidget";
import { useTenant } from "../../context/TenantContext";
import { CustomerUiContext } from "../../utils/customer-ui";
import CustomerFooter from "./CustomerFooter";
import { CustomerCartProvider } from "../../context/CustomerCartContext";
import CustomerCartDrawer from "./CustomerCartDrawer";

export default function CustomerLayout({ children }) {
  const { pharmacy } = useTenant() ?? {};
  const brandName = pharmacy?.name ?? "Sunr";
  const logoUrl = pharmacy?.logo_url ?? "";
  const contactEmail = pharmacy?.contact_email ?? "";
  const contactPhone = pharmacy?.contact_phone ?? "";
  const contactAddress = pharmacy?.contact_address ?? "";
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isCartOpen, setIsCartOpen] = useState(false);
  const contextValue = useMemo(
    () => ({
      openChat: () => setIsChatOpen(true),
    }),
    [setIsChatOpen]
  );

  return (
    <CustomerCartProvider>
      <CustomerUiContext.Provider value={contextValue}>
        <div
          className="min-h-screen bg-gradient-to-br from-slate-50 to-sky-50/40"
          style={{ fontFamily: "var(--brand-font-family)" }}
        >
          <CustomerNav
            activeBrand={brandName}
            logoUrl={logoUrl}
            onChatToggle={() => setIsChatOpen(true)}
            onCartToggle={() => setIsCartOpen(true)}
          />
          <a
            href="#customer-main"
            className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:text-gray-900 focus:shadow-md"
          >
            Skip to content
          </a>
          <main id="customer-main" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            {children}
          </main>
          <CustomerFooter
            brandName={brandName}
            logoUrl={logoUrl}
            email={contactEmail || undefined}
            phone={contactPhone || undefined}
            address={contactAddress || undefined}
          />

          {!isChatOpen ? (
            <button
              type="button"
              onClick={() => setIsChatOpen(true)}
              className="fixed bottom-6 right-6 w-16 h-16 bg-[var(--brand-accent)] hover:opacity-95 text-white rounded-full shadow-2xl flex items-center justify-center transition-all hover:scale-110 z-40"
              aria-label="Open AI chat"
            >
              <MessageCircle className="w-8 h-8" />
            </button>
          ) : null}

          <CustomerChatWidget
            isOpen={isChatOpen}
            onClose={() => setIsChatOpen(false)}
            brandName={brandName}
            placement="viewport"
          />

          <CustomerCartDrawer isOpen={isCartOpen} onClose={() => setIsCartOpen(false)} />
        </div>
      </CustomerUiContext.Provider>
    </CustomerCartProvider>
  );
}
