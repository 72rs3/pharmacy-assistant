import { Link } from "react-router-dom";
import { Heart, Mail, MapPin, Phone, ShieldCheck } from "lucide-react";
import { useCustomerUi } from "../../utils/customer-ui";
import { useTenant } from "../../context/TenantContext";

export default function CustomerFooter({
  brandName = "Sunr",
  logoUrl = "",
  address = "123 Health Avenue, Suite 101, Wellness City, WC 12345",
  phone = "(555) 123-4567",
  email = "info@sunrpharmacy.com",
}) {
  const { pharmacy } = useTenant() ?? {};
  const theme = String(pharmacy?.theme_preset ?? "classic").toLowerCase();
  const isGlass = theme === "glass";
  const isNeumorph = theme === "neumorph";
  const isMinimal = theme === "minimal";
  const normalizedBrand = brandName?.trim() || "Sunr";
  const primaryBrand = /pharmacy/i.test(normalizedBrand)
    ? normalizedBrand.replace(/pharmacy/i, "").trim() || normalizedBrand
    : normalizedBrand;
  const { openChat } = useCustomerUi();
  const year = new Date().getFullYear();
  const phoneHref = `tel:${String(phone).replace(/[^\d+]/g, "")}`;
  const hasLogo = Boolean(logoUrl);
  const linkHoverClass = isGlass || isNeumorph ? "hover:text-slate-900" : "hover:text-white";
  return (
    <footer
      className={`mt-12 ${
        isGlass
          ? "bg-white/60 text-slate-700 backdrop-blur border-t border-white/70"
          : isNeumorph
            ? "bg-slate-100 text-slate-700 border-t border-slate-200"
            : "bg-gray-900 text-gray-300"
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid md:grid-cols-4 gap-8">
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div
                className={`w-10 h-10 rounded-lg flex items-center justify-center overflow-hidden border ${
                  isNeumorph ? "bg-slate-100 border-slate-200 shadow-[inset_-4px_-4px_8px_rgba(255,255,255,0.85),inset_4px_4px_8px_rgba(15,23,42,0.12)]" : "bg-white border-gray-800"
                }`}
              >
                {hasLogo ? (
                  <img src={logoUrl} alt={`${primaryBrand} logo`} className="w-full h-full object-contain" />
                ) : (
                  <div className="w-full h-full bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-primary-600)] flex items-center justify-center">
                    <svg width="24" height="24" viewBox="0 0 32 32" fill="none">
                      <path d="M16 8V24M8 16H24" stroke="white" strokeWidth="3" strokeLinecap="round" />
                    </svg>
                  </div>
                )}
              </div>
              <div>
                <div className={`${isGlass || isNeumorph ? "text-slate-900" : "text-white"}`}>{primaryBrand}</div>
                <div className={`${isMinimal ? "text-slate-500" : "text-[var(--brand-primary)]"} text-sm`}>Pharmacy</div>
              </div>
            </div>
            <p className="text-sm">Your trusted partner for wellness and healthcare solutions.</p>
            <div className={`flex items-center gap-2 text-xs ${isGlass || isNeumorph ? "text-slate-500" : "text-gray-400"}`}>
              <ShieldCheck className="w-4 h-4" />
              <span>Private by design - Always confirm with a pharmacist</span>
            </div>
          </div>

          <div>
            <h3 className={`${isGlass || isNeumorph ? "text-slate-900" : "text-white"} mb-4`}>Quick Links</h3>
            <ul className="space-y-2 text-sm">
              <li>
                <Link to="/" className={`${linkHoverClass} transition-colors`}>
                  Home
                </Link>
              </li>
              <li>
                <Link to="/shop" className={`${linkHoverClass} transition-colors`}>
                  Shop
                </Link>
              </li>
              <li>
                <Link to="/contact" className={`${linkHoverClass} transition-colors`}>
                  Contact
                </Link>
              </li>
            </ul>
          </div>

          <div>
            <h3 className={`${isGlass || isNeumorph ? "text-slate-900" : "text-white"} mb-4`}>Services</h3>
            <ul className="space-y-2 text-sm">
              <li>
                <button type="button" onClick={openChat} className={`${linkHoverClass} transition-colors`}>
                  Prescription questions
                </button>
              </li>
              <li>
                <button type="button" onClick={openChat} className={`${linkHoverClass} transition-colors`}>
                  Health consultations
                </button>
              </li>
              <li>
                <button type="button" onClick={openChat} className={`${linkHoverClass} transition-colors`}>
                  Delivery & pickup
                </button>
              </li>
              <li>
                <button type="button" onClick={openChat} className={`${linkHoverClass} transition-colors`}>
                  Vaccinations & appointments
                </button>
              </li>
            </ul>
          </div>

          <div>
            <h3 className={`${isGlass || isNeumorph ? "text-slate-900" : "text-white"} mb-4`}>Contact Us</h3>
            <ul className="space-y-3 text-sm">
              <li className="flex items-start gap-2">
                <MapPin className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span>{address}</span>
              </li>
              <li className="flex items-center gap-2">
                <Phone className="w-4 h-4 flex-shrink-0" />
                <a href={phoneHref} className={`${linkHoverClass} transition-colors`}>
                  {phone}
                </a>
              </li>
              <li className="flex items-center gap-2">
                <Mail className="w-4 h-4 flex-shrink-0" />
                <a href={`mailto:${email}`} className={`${linkHoverClass} transition-colors`}>
                  {email}
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div
          className={`border-t mt-8 pt-8 flex flex-col md:flex-row justify-between items-center gap-4 text-sm ${
            isGlass || isNeumorph ? "border-slate-200" : "border-gray-800"
          }`}
        >
          <p>(c) {year} {primaryBrand} Pharmacy. All rights reserved.</p>
          <div className="flex items-center gap-1">
            <span>Made with</span>
            <Heart className="w-4 h-4 text-red-500 fill-red-500" />
            <span>for your health</span>
          </div>
          <div className="flex gap-6">
            <button type="button" onClick={openChat} className={`${linkHoverClass} transition-colors`}>
              Medical disclaimer
            </button>
            <a href="#" className={`${linkHoverClass} transition-colors`}>
              Privacy Policy
            </a>
            <a href="#" className={`${linkHoverClass} transition-colors`}>
              Terms of Service
            </a>
          </div>
        </div>

        <p className="mt-6 text-xs text-gray-400 leading-relaxed">
          Information on this site is for general education and is not medical advice. For emergencies, call local
          emergency services immediately.
        </p>
      </div>
    </footer>
  );
}
