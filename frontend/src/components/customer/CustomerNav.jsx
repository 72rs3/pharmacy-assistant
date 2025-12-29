import { NavLink } from "react-router-dom";
import { MessageCircle, ShoppingCart } from "lucide-react";
import { useCustomerCart } from "../../context/CustomerCartContext";
import { useTenant } from "../../context/TenantContext";

export default function CustomerNav({ activeBrand = "Sunr Pharmacy", logoUrl = "", onChatToggle, onCartToggle }) {
  const { totalItems } = useCustomerCart();
  const { pharmacy } = useTenant() ?? {};
  const theme = String(pharmacy?.theme_preset ?? "classic").toLowerCase();
  const normalizedBrand = activeBrand?.trim() || "Sunr";
  const hasPharmacy = /pharmacy/i.test(normalizedBrand);
  const primaryBrand = hasPharmacy ? normalizedBrand.replace(/pharmacy/i, "").trim() || normalizedBrand : normalizedBrand;
  const hasLogo = Boolean(logoUrl);
  const isGlass = theme === "glass";
  const isNeumorph = theme === "neumorph";
  const isMinimal = theme === "minimal";
  const isFresh = theme === "fresh";

  const getLinkClass = ({ isActive }) =>
    `pb-1 transition-colors ${
      isActive
        ? "text-[var(--brand-accent)] border-b-2 border-[var(--brand-accent)]"
        : "text-gray-600 hover:text-gray-900"
    }`;

  return (
    <header
      className={`sticky top-0 z-40 ${
        isGlass
          ? "bg-white/70 backdrop-blur border-b border-white/60 shadow-lg"
          : isNeumorph
            ? "bg-slate-100 border-b border-slate-200/80 shadow-[0_10px_24px_rgba(15,23,42,0.08)]"
            : isFresh
              ? "bg-gradient-to-r from-emerald-50 to-sky-50 border-b border-emerald-100 shadow-sm"
              : "bg-white shadow-sm"
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-20">
          <div className="flex items-center gap-3">
            <div
              className={`w-12 h-12 rounded-xl flex items-center justify-center overflow-hidden ${
                isNeumorph ? "bg-slate-100 shadow-[inset_-6px_-6px_12px_rgba(255,255,255,0.8),inset_6px_6px_12px_rgba(15,23,42,0.12)]" : "shadow-md bg-white"
              } border border-gray-100`}
            >
              {hasLogo ? (
                <img src={logoUrl} alt={`${primaryBrand} logo`} className="w-full h-full object-contain" />
              ) : (
                <div className="w-full h-full bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-primary-600)] flex items-center justify-center">
                  <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
                    <path d="M16 8V24M8 16H24" stroke="white" strokeWidth="3" strokeLinecap="round" />
                  </svg>
                </div>
              )}
            </div>
            <div className="leading-tight">
              <div className={`text-xl ${isMinimal ? "text-gray-800 font-semibold" : "text-gray-900"}`}>{primaryBrand}</div>
              <div className={`text-sm ${isMinimal ? "text-gray-500" : "text-[var(--brand-accent)]"}`}>Pharmacy</div>
            </div>
          </div>

          <nav className={`hidden md:flex items-center ${isMinimal ? "gap-6 text-sm" : "gap-10"}`}>
            <NavLink to="/" end className={getLinkClass}>
              Home
            </NavLink>
            <NavLink to="/shop" className={getLinkClass}>
              Shop
            </NavLink>
            <NavLink to="/orders" className={getLinkClass}>
              Track order
            </NavLink>
            <NavLink to="/contact" className={getLinkClass}>
              Contact
            </NavLink>
          </nav>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onCartToggle}
              className={`relative flex items-center justify-center w-11 h-11 rounded-lg border text-gray-700 transition-colors ${
                isGlass
                  ? "bg-white/60 border-white/70 hover:bg-white/80"
                  : isNeumorph
                    ? "bg-slate-100 border-slate-200 hover:bg-slate-50 shadow-[inset_-4px_-4px_10px_rgba(255,255,255,0.8),inset_4px_4px_10px_rgba(15,23,42,0.12)]"
                    : "border-gray-200 hover:bg-gray-50"
              }`}
              aria-label="Open cart"
            >
              <ShoppingCart className="w-5 h-5" />
              {totalItems > 0 ? (
                <span className="absolute -top-1.5 -right-1.5 bg-[var(--brand-accent)] text-white text-xs w-5 h-5 rounded-full flex items-center justify-center">
                  {totalItems}
                </span>
              ) : null}
            </button>
            <button
              type="button"
              onClick={onChatToggle}
              className={`flex items-center gap-2 px-4 py-2 text-white transition-colors ${
                isGlass
                  ? "rounded-full bg-[var(--brand-accent)]/90 backdrop-blur shadow-lg hover:opacity-90"
                  : isNeumorph
                    ? "rounded-2xl bg-[var(--brand-accent)] shadow-[0_12px_24px_rgba(15,23,42,0.2)] hover:opacity-90"
                    : isFresh
                      ? "rounded-full bg-[var(--brand-accent)] shadow-[0_12px_24px_rgba(15,23,42,0.14)] hover:opacity-95"
                      : "rounded-lg bg-[var(--brand-accent)] shadow-sm hover:opacity-95"
              }`}
            >
              <MessageCircle className="w-5 h-5" />
              <span className="hidden sm:inline">AI Assistant</span>
            </button>
          </div>
        </div>

        <div className="md:hidden flex gap-4 pb-3">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `flex-1 py-2 text-sm transition-colors ${isActive ? "text-[var(--brand-accent)] border-b-2 border-[var(--brand-accent)]" : "text-gray-600"}`
            }
          >
            Home
          </NavLink>
          <NavLink
            to="/shop"
            className={({ isActive }) =>
              `flex-1 py-2 text-sm transition-colors ${isActive ? "text-[var(--brand-accent)] border-b-2 border-[var(--brand-accent)]" : "text-gray-600"}`
            }
          >
            Shop
          </NavLink>
          <NavLink
            to="/orders"
            className={({ isActive }) =>
              `flex-1 py-2 text-sm transition-colors ${isActive ? "text-[var(--brand-accent)] border-b-2 border-[var(--brand-accent)]" : "text-gray-600"}`
            }
          >
            Track
          </NavLink>
          <NavLink
            to="/contact"
            className={({ isActive }) =>
              `flex-1 py-2 text-sm transition-colors ${isActive ? "text-[var(--brand-accent)] border-b-2 border-[var(--brand-accent)]" : "text-gray-600"}`
            }
          >
            Contact
          </NavLink>
        </div>
      </div>
    </header>
  );
}
