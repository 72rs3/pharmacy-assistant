import { Navigate, Link } from "react-router-dom";
import { Clock, Heart, Pill, Shield } from "lucide-react";
import { useTenant } from "../context/TenantContext";
import { isPortalHost } from "../utils/tenant";

const features = [
  {
    title: "Quality Medications",
    description: "Wide selection of authentic medicines from trusted brands",
    icon: Pill,
    tone: "blue",
  },
  {
    title: "Expert Care",
    description: "Professional pharmacists ready to assist you",
    icon: Heart,
    tone: "green",
  },
  {
    title: "Safe & Secure",
    description: "Your health data is protected with highest security",
    icon: Shield,
    tone: "purple",
  },
  {
    title: "Fast Service",
    description: "Quick prescription filling and home delivery",
    icon: Clock,
    tone: "orange",
  },
];

const toneStyles = {
  blue: "bg-blue-100 text-blue-600",
  green: "bg-green-100 text-green-600",
  purple: "bg-purple-100 text-purple-600",
  orange: "bg-orange-100 text-orange-600",
};

export default function Home() {
  const portalHost = isPortalHost();

  const { pharmacy } = useTenant() ?? {};
  const brandName = pharmacy?.name ?? "Sunr";
  const theme = String(pharmacy?.theme_preset ?? "classic").toLowerCase();
  const layout = String(pharmacy?.storefront_layout ?? "classic").toLowerCase();
  const heroImage =
    pharmacy?.hero_image_url ||
    "https://images.unsplash.com/photo-1582146804102-b4a01b0a51ae?auto=format&fit=crop&w=1080&q=80";
  const secondaryImage =
    pharmacy?.branding_details
      ? "https://images.unsplash.com/photo-1576669801945-7a346954da5a?auto=format&fit=crop&w=1080&q=80"
      : "https://images.unsplash.com/photo-1576669801945-7a346954da5a?auto=format&fit=crop&w=1080&q=80";

  if (portalHost) {
    return <Navigate to="/portal" replace />;
  }

  if (!pharmacy) {
    return (
      <div className="bg-white rounded-2xl p-8 shadow-md">
        <h1 className="text-3xl text-gray-900 mb-3">Pharmacy not available</h1>
        <p className="text-gray-600">
          This pharmacy could not be found or is not yet approved. Please check the domain.
        </p>
      </div>
    );
  }

  const isGlass = theme === "glass";
  const isNeumorph = theme === "neumorph";
  const isMinimal = theme === "minimal";
  const featureCardClass = isGlass
    ? "bg-white/70 backdrop-blur border border-white/70 shadow-lg"
    : isNeumorph
      ? "bg-slate-100 border border-slate-200 shadow-[inset_-12px_-12px_24px_rgba(255,255,255,0.85),inset_12px_12px_24px_rgba(15,23,42,0.12)]"
      : "bg-white shadow-md";

  const renderClassicHero = () => (
    <section className="relative bg-gradient-to-br from-amber-50 to-sky-50 rounded-3xl overflow-hidden shadow-sm border border-white">
      <div className="grid md:grid-cols-2 gap-8 items-center p-8 md:p-16">
        <div className="space-y-6">
          <h1 className="text-5xl md:text-6xl text-gray-900">
            Your Health,
            <br />
            <span className="text-[var(--brand-accent)]">Our Priority</span>
          </h1>
          <p className="text-xl text-gray-600">
            {brandName} - Your trusted partner for wellness and healthcare solutions.
          </p>
          <div className="flex flex-wrap gap-4">
            <Link
              to="/shop"
              className="px-6 py-3 bg-[var(--brand-accent)] text-white rounded-lg hover:opacity-95 transition-colors shadow-md"
            >
              Shop Now
            </Link>
            <Link
              to="/appointments"
              className="px-6 py-3 border-2 border-[var(--brand-accent)] text-[var(--brand-accent)] rounded-lg hover:bg-[var(--brand-accent)] hover:text-white transition-colors"
            >
              Book Appointment
            </Link>
          </div>

          <div className="inline-flex items-start gap-3 bg-[#e7f6df] border border-[#cdeec0] rounded-xl px-4 py-3 shadow-sm max-w-md">
            <div className="w-9 h-9 rounded-lg bg-[var(--brand-primary)] text-white grid place-items-center shrink-0">
              <Pill className="w-5 h-5" />
            </div>
            <p className="text-sm text-gray-700 leading-relaxed">
              Yes! We have common OTC medicines available. Ask the assistant about price, stock, or prescription
              requirements.
            </p>
          </div>
        </div>

        <div className="relative h-96">
          <img src={heroImage} alt="Pharmacy hero" className="w-full h-full object-cover rounded-2xl shadow-xl" />
        </div>
      </div>
    </section>
  );

  const renderBreezeHero = () => (
    <section className="relative rounded-3xl overflow-hidden shadow-sm border border-white bg-white">
      <div className="grid lg:grid-cols-[1.2fr_1fr] gap-10 items-center p-8 md:p-16">
        <div className="space-y-6">
          <span className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-100 text-emerald-700 text-sm">
            Friendly care, every day
          </span>
          <h1 className="text-5xl md:text-6xl text-gray-900">
            {brandName}
            <br />
            <span className="text-[var(--brand-accent)]">Wellness Hub</span>
          </h1>
          <p className="text-lg text-gray-600">
            Quick advice, trusted products, and personalized pharmacy support in one place.
          </p>
          <div className="flex flex-wrap gap-4">
            <Link
              to="/shop"
              className="px-6 py-3 bg-[var(--brand-accent)] text-white rounded-lg hover:opacity-95 transition-colors shadow-md"
            >
              Explore Shop
            </Link>
            <Link
              to="/contact"
              className="px-6 py-3 border-2 border-[var(--brand-accent)] text-[var(--brand-accent)] rounded-lg hover:bg-[var(--brand-accent)] hover:text-white transition-colors"
            >
              Contact Us
            </Link>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="bg-slate-50 rounded-xl border border-slate-100 p-4">
              <div className="text-sm text-gray-600">Same day support</div>
              <div className="text-lg text-gray-900">Chat with our team</div>
            </div>
            <div className="bg-slate-50 rounded-xl border border-slate-100 p-4">
              <div className="text-sm text-gray-600">Appointments</div>
              <div className="text-lg text-gray-900">Book in minutes</div>
            </div>
          </div>
        </div>
        <div className="relative">
          <img src={heroImage} alt="Pharmacy hero" className="w-full h-[420px] object-cover rounded-2xl shadow-xl" />
        </div>
      </div>
    </section>
  );

  const renderStudioHero = () => (
    <section className="relative rounded-3xl overflow-hidden border border-slate-200 bg-white shadow-sm">
      <div className="grid lg:grid-cols-2 gap-8 items-center p-8 md:p-16">
        <div className="space-y-6">
          <div className="text-sm uppercase tracking-widest text-slate-400">Pharmacy studio</div>
          <h1 className="text-5xl md:text-6xl text-gray-900">
            Precision care
            <br />
            <span className="text-[var(--brand-accent)]">Built around you</span>
          </h1>
          <p className="text-lg text-gray-600">
            Designed for clarity and guidance, with experts ready to help you every step.
          </p>
          <div className="flex flex-wrap gap-4">
            <Link
              to="/appointments"
              className="px-6 py-3 bg-[var(--brand-accent)] text-white rounded-lg hover:opacity-95 transition-colors shadow-md"
            >
              Book a visit
            </Link>
            <Link
              to="/shop"
              className="px-6 py-3 border-2 border-[var(--brand-accent)] text-[var(--brand-accent)] rounded-lg hover:bg-[var(--brand-accent)] hover:text-white transition-colors"
            >
              Browse products
            </Link>
          </div>
        </div>
        <div className="relative h-[420px]">
          <img src={heroImage} alt="Pharmacy hero" className="w-full h-full object-cover rounded-2xl shadow-xl" />
        </div>
      </div>
    </section>
  );

  const renderMarketHero = () => (
    <section className="relative rounded-3xl overflow-hidden border border-slate-200 bg-white shadow-sm">
      <div className="grid lg:grid-cols-[1fr_1.2fr] gap-8 items-center p-8 md:p-16">
        <div className="space-y-6">
          <span className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-100 text-blue-700 text-sm">
            Product first storefront
          </span>
          <h1 className="text-5xl md:text-6xl text-gray-900">
            Stocked for
            <br />
            <span className="text-[var(--brand-accent)]">everyday needs</span>
          </h1>
          <p className="text-lg text-gray-600">
            Discover fast-moving essentials, wellness supplies, and curated product bundles.
          </p>
          <div className="flex flex-wrap gap-4">
            <Link
              to="/shop"
              className="px-6 py-3 bg-[var(--brand-accent)] text-white rounded-lg hover:opacity-95 transition-colors shadow-md"
            >
              Start shopping
            </Link>
            <Link
              to="/orders"
              className="px-6 py-3 border-2 border-[var(--brand-accent)] text-[var(--brand-accent)] rounded-lg hover:bg-[var(--brand-accent)] hover:text-white transition-colors"
            >
              Track order
            </Link>
          </div>
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="rounded-2xl overflow-hidden shadow-md">
            <img src={heroImage} alt="Pharmacy hero" className="w-full h-56 object-cover" />
          </div>
          <div className="rounded-2xl overflow-hidden shadow-md">
            <img src={secondaryImage} alt="Pharmacy interior" className="w-full h-56 object-cover" />
          </div>
        </div>
      </div>
    </section>
  );

  const renderGlassHero = () => (
    <section className="relative rounded-[32px] overflow-hidden border border-white/60 bg-white/70 backdrop-blur shadow-xl">
      <div className="grid lg:grid-cols-[1.1fr_0.9fr] gap-10 items-center p-8 md:p-16">
        <div className="space-y-6">
          <span className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/70 text-slate-700 text-sm border border-white/80">
            Premium pharmacy experience
          </span>
          <h1 className="text-5xl md:text-6xl text-slate-900">
            {brandName}
            <br />
            <span className="text-[var(--brand-accent)]">Glass clinic</span>
          </h1>
          <p className="text-lg text-slate-600">
            A serene, modern storefront with transparent touches and smooth interactions.
          </p>
          <div className="flex flex-wrap gap-4">
            <Link
              to="/shop"
              className="px-6 py-3 bg-[var(--brand-accent)] text-white rounded-full hover:opacity-95 transition-colors shadow-lg"
            >
              Explore products
            </Link>
            <Link
              to="/contact"
              className="px-6 py-3 border border-white/80 text-slate-700 rounded-full hover:bg-white/80 transition-colors"
            >
              Get in touch
            </Link>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="rounded-2xl border border-white/80 bg-white/70 p-4">
              <div className="text-sm text-slate-600">Live assistance</div>
              <div className="text-lg text-slate-900">Chat with a pharmacist</div>
            </div>
            <div className="rounded-2xl border border-white/80 bg-white/70 p-4">
              <div className="text-sm text-slate-600">Delivery</div>
              <div className="text-lg text-slate-900">Fast local dispatch</div>
            </div>
          </div>
        </div>
        <div className="relative">
          <div className="absolute -top-6 -right-6 w-32 h-32 bg-sky-200/40 rounded-full blur-2xl" />
          <img src={heroImage} alt="Pharmacy hero" className="w-full h-[420px] object-cover rounded-3xl shadow-2xl" />
        </div>
      </div>
    </section>
  );

  const renderNeumorphHero = () => (
    <section className="relative rounded-[32px] overflow-hidden bg-slate-100 border border-slate-200 shadow-[20px_20px_40px_rgba(15,23,42,0.12),-20px_-20px_40px_rgba(255,255,255,0.8)]">
      <div className="grid lg:grid-cols-[0.95fr_1.05fr] gap-10 items-center p-8 md:p-16">
        <div className="space-y-6">
          <div className="inline-flex items-center px-4 py-2 rounded-2xl bg-slate-100 shadow-[inset_-6px_-6px_12px_rgba(255,255,255,0.8),inset_6px_6px_12px_rgba(15,23,42,0.12)] text-slate-700 text-sm">
            Soft-touch care
          </div>
          <h1 className="text-5xl md:text-6xl text-slate-900">
            {brandName}
            <br />
            <span className="text-[var(--brand-accent)]">Neumorph Studio</span>
          </h1>
          <p className="text-lg text-slate-600">
            Smooth, tactile UI components with gentle depth and comfort-first navigation.
          </p>
          <div className="flex flex-wrap gap-4">
            <Link
              to="/appointments"
              className="px-6 py-3 bg-[var(--brand-accent)] text-white rounded-2xl hover:opacity-95 transition-colors shadow-[0_14px_30px_rgba(15,23,42,0.18)]"
            >
              Book appointment
            </Link>
            <Link
              to="/shop"
              className="px-6 py-3 bg-slate-100 text-slate-700 rounded-2xl shadow-[inset_-6px_-6px_12px_rgba(255,255,255,0.85),inset_6px_6px_12px_rgba(15,23,42,0.12)]"
            >
              Browse shop
            </Link>
          </div>
        </div>
        <div className="grid gap-4">
          <div className="rounded-3xl overflow-hidden shadow-[12px_12px_24px_rgba(15,23,42,0.15)]">
            <img src={heroImage} alt="Pharmacy hero" className="w-full h-56 object-cover" />
          </div>
          <div className="rounded-3xl overflow-hidden shadow-[12px_12px_24px_rgba(15,23,42,0.15)]">
            <img src={secondaryImage} alt="Pharmacy interior" className="w-full h-56 object-cover" />
          </div>
        </div>
      </div>
    </section>
  );

  const renderHero = () => {
    if (isGlass) return renderGlassHero();
    if (isNeumorph) return renderNeumorphHero();
    if (layout === "breeze") return renderBreezeHero();
    if (layout === "studio") return renderStudioHero();
    if (layout === "market") return renderMarketHero();
    return renderClassicHero();
  };

  return (
    <div className="space-y-16">
      {renderHero()}

      <section className={`grid gap-6 ${isMinimal ? "md:grid-cols-2 lg:grid-cols-4" : "md:grid-cols-4"}`}>
        {features.map((feature) => {
          const Icon = feature.icon;
          const tone = toneStyles[feature.tone] ?? "bg-gray-100 text-gray-600";
          return (
            <div
              key={feature.title}
              className={`${featureCardClass} p-6 rounded-2xl hover:shadow-xl transition-shadow`}
            >
              <div className={`w-12 h-12 ${tone} rounded-lg flex items-center justify-center mb-4`}>
                <Icon className="w-6 h-6" />
              </div>
              <h3 className="text-gray-900 mb-2">{feature.title}</h3>
              <p className="text-gray-600 text-sm">{feature.description}</p>
            </div>
          );
        })}
      </section>

      <section className="bg-white rounded-2xl p-8 md:p-12 shadow-md">
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div>
            <img src={secondaryImage} alt="Healthcare consultation" className="w-full rounded-xl shadow-lg" />
          </div>
          <div className="space-y-4">
            <h2 className="text-4xl text-gray-900">Caring for Your Health Since 1995</h2>
            <p className="text-gray-600">
              At {brandName}, we have been serving our community with dedication and care for decades. Our team is
              committed to providing you with personalized support and access to the medications you need.
            </p>
            <p className="text-gray-600">
              We understand that your health is your most valuable asset. That is why we go above and beyond to ensure
              you receive expert advice and friendly service.
            </p>
            <ul className="space-y-2">
              <li className="flex items-center gap-2 text-gray-700">
                <div className="w-2 h-2 bg-[var(--brand-primary)] rounded-full"></div>
                Licensed and certified pharmacists
              </li>
              <li className="flex items-center gap-2 text-gray-700">
                <div className="w-2 h-2 bg-[var(--brand-primary)] rounded-full"></div>
                Free health consultations
              </li>
              <li className="flex items-center gap-2 text-gray-700">
                <div className="w-2 h-2 bg-[var(--brand-primary)] rounded-full"></div>
                Medication therapy management
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section className="grid md:grid-cols-3 gap-8">
        <div className="text-center p-8 bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-primary-600)] rounded-2xl text-white">
          <div className="text-5xl mb-2">25+</div>
          <div className="text-lg opacity-90">Years of Service</div>
        </div>
        <div className="text-center p-8 bg-gradient-to-br from-blue-500 to-blue-600 rounded-2xl text-white">
          <div className="text-5xl mb-2">50K+</div>
          <div className="text-lg opacity-90">Happy Customers</div>
        </div>
        <div className="text-center p-8 bg-gradient-to-br from-purple-500 to-purple-600 rounded-2xl text-white">
          <div className="text-5xl mb-2">10K+</div>
          <div className="text-lg opacity-90">Products Available</div>
        </div>
      </section>
    </div>
  );
}
