import { useEffect, useMemo, useState } from "react";
import { Baby, Droplet, Heart, MessageCircle, Search, Shield, Sparkles, Sun } from "lucide-react";
import api from "../api/axios";
import EmptyState from "../components/ui/EmptyState";
import { useCustomerUi } from "../utils/customer-ui";
import { useCustomerCart } from "../context/CustomerCartContext";
import { useTenant } from "../context/TenantContext";

const formatMoney = (value) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(value);

const FALLBACK_PRODUCTS = [
  {
    id: "fallback-1",
    name: "Toothpaste",
    category: "Oral Care",
    price: 4.99,
    stock_level: 25,
    icon: Sparkles,
    color: "sky",
    image: "https://images.unsplash.com/photo-1622786041118-8fc46a90c45e?w=900&q=80",
  },
  {
    id: "fallback-2",
    name: "Toothbrush",
    category: "Oral Care",
    price: 3.49,
    stock_level: 40,
    icon: Sparkles,
    color: "sky",
    image: "https://images.unsplash.com/photo-1607613009820-a29f7bb81c04?w=900&q=80",
  },
  {
    id: "fallback-3",
    name: "Sunscreen SPF 50",
    category: "Sun Protection",
    price: 12.99,
    stock_level: 18,
    icon: Sun,
    color: "amber",
    image: "https://images.unsplash.com/photo-1556228453-efd6c1ff04f6?w=900&q=80",
  },
  {
    id: "fallback-4",
    name: "Vitamin C",
    category: "Vitamins",
    price: 15.99,
    stock_level: 30,
    icon: Heart,
    color: "rose",
    image: "https://images.unsplash.com/photo-1550572017-4592e6e79da8?w=900&q=80",
  },
  {
    id: "fallback-5",
    name: "Multivitamin",
    category: "Vitamins",
    price: 18.99,
    stock_level: 22,
    icon: Heart,
    color: "rose",
    image: "https://images.unsplash.com/photo-1607619056574-7b8d3ee536b2?w=900&q=80",
  },
  {
    id: "fallback-6",
    name: "Baby Lotion",
    category: "Baby Care",
    price: 8.99,
    stock_level: 16,
    icon: Baby,
    color: "pink",
    image: "https://images.unsplash.com/photo-1620331311520-246422fd82f9?w=900&q=80",
  },
  {
    id: "fallback-7",
    name: "Baby Wipes",
    category: "Baby Care",
    price: 6.99,
    stock_level: 35,
    icon: Baby,
    color: "pink",
    image: "https://images.unsplash.com/photo-1584769257991-0d12f9be71c0?w=900&q=80",
  },
  {
    id: "fallback-8",
    name: "Hand Sanitizer",
    category: "Personal Care",
    price: 5.99,
    stock_level: 60,
    icon: Shield,
    color: "emerald",
    image: "https://images.unsplash.com/photo-1584744982491-665f46a78f48?w=900&q=80",
  },
  {
    id: "fallback-9",
    name: "Face Moisturizer",
    category: "Skincare",
    price: 14.99,
    stock_level: 14,
    icon: Droplet,
    color: "blue",
    image: "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=900&q=80",
  },
];

const colorClasses = {
  sky: "bg-sky-100 text-sky-600",
  amber: "bg-amber-100 text-amber-600",
  rose: "bg-rose-100 text-rose-600",
  pink: "bg-pink-100 text-pink-600",
  emerald: "bg-emerald-100 text-emerald-600",
  blue: "bg-blue-100 text-blue-600",
};

const heroBadgeClasses = "inline-block px-4 py-2 bg-emerald-100 text-emerald-700 rounded-full text-sm mb-4";

const getProductPresentation = (item) => {
  if (item && typeof item === "object" && "icon" in item && "color" in item && "image" in item) {
    return {
      Icon: item.icon ?? Sparkles,
      color: item.color ?? "sky",
      image: item.image,
    };
  }

  const name = String(item?.name ?? "").toLowerCase();
  const category = String(item?.category ?? "").toLowerCase();
  const text = `${name} ${category}`;
  const match = (words) => words.some((word) => text.includes(word));

  if (match(["sunblock", "sunscreen", "sun", "spf"])) {
    return {
      Icon: Sun,
      color: "amber",
      image: "https://images.unsplash.com/photo-1556228453-efd6c1ff04f6?w=900&q=80",
    };
  }

  if (match(["baby", "wipes", "diaper"])) {
    return {
      Icon: Baby,
      color: "pink",
      image: "https://images.unsplash.com/photo-1620331311520-246422fd82f9?w=900&q=80",
    };
  }

  if (match(["vitamin", "multivitamin", "supplement"])) {
    return {
      Icon: Heart,
      color: "rose",
      image: "https://images.unsplash.com/photo-1550572017-4592e6e79da8?w=900&q=80",
    };
  }

  if (match(["sanitizer", "soap", "hygiene"])) {
    return {
      Icon: Shield,
      color: "emerald",
      image: "https://images.unsplash.com/photo-1584744982491-665f46a78f48?w=900&q=80",
    };
  }

  if (match(["skin", "skincare", "moisturizer", "lotion", "cleanser"])) {
    return {
      Icon: Droplet,
      color: "blue",
      image: "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=900&q=80",
    };
  }

  if (match(["toothbrush", "toothpaste", "oral", "tooth"])) {
    return {
      Icon: Sparkles,
      color: "sky",
      image: "https://images.unsplash.com/photo-1622786041118-8fc46a90c45e?w=900&q=80",
    };
  }

  return {
    Icon: Sparkles,
    color: "sky",
    image: "https://images.unsplash.com/photo-1646392206581-2527b1cae5cb?auto=format&fit=crop&w=900&q=80",
  };
};

export default function Shop() {
  const { openChat } = useCustomerUi();
  const { addItem } = useCustomerCart();
  const { pharmacy } = useTenant() ?? {};
  const theme = String(pharmacy?.theme_preset ?? "classic").toLowerCase();
  const isGlass = theme === "glass";
  const isNeumorph = theme === "neumorph";
  const isMinimal = theme === "minimal";
  const isFresh = theme === "fresh";
  const [products, setProducts] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [inStockOnly, setInStockOnly] = useState(false);

  const isUsingFallback = products.length === 0;

  const availableProducts = useMemo(() => {
    if (products.length > 0) return products;
    return FALLBACK_PRODUCTS;
  }, [products]);

  const categories = useMemo(() => {
    const unique = new Set();
    for (const product of availableProducts ?? []) {
      const raw = product?.category?.trim();
      if (raw) unique.add(raw);
    }
    const preferred = ["Oral Care", "Sun Protection", "Vitamins", "Baby Care", "Skincare", "Personal Care"];
    const merged = new Set(preferred);
    for (const cat of unique) merged.add(cat);
    return ["all", ...Array.from(merged).sort((a, b) => a.localeCompare(b))];
  }, [availableProducts]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const selectedCategory = category.trim().toLowerCase();
    return (availableProducts ?? []).filter((product) => {
      const productCategory = String(product.category ?? "").trim().toLowerCase();
      if (category !== "all" && productCategory !== selectedCategory) return false;
      if (inStockOnly && Number(product.stock_level ?? 0) <= 0) return false;
      if (!q) return true;
      const haystack = `${product.name ?? ""} ${product.category ?? ""}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [availableProducts, category, inStockOnly, query]);

  const loadProducts = async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await api.get("/products");
      setProducts(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setProducts([]);
      setError(e?.response?.data?.detail ?? "Unable to load products for this pharmacy.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadProducts();
  }, []);

  return (
    <div className="space-y-12">
      <section className="text-center space-y-4">
        <div className={heroBadgeClasses}>Non-medicine products</div>
        <h1 className="text-5xl text-gray-900">Shop Products</h1>
        <p className="text-xl text-gray-600 max-w-3xl mx-auto">
          Browse non-medical items like oral care, skincare, baby care, and wellness essentials.
        </p>
        <p className="text-sm text-gray-500 italic">For medicines, please ask the AI assistant.</p>
      </section>

      <section className="space-y-6" id="medicines">
        {isUsingFallback ? (
          <div className="max-w-3xl mx-auto bg-amber-50 border border-amber-200 text-amber-900 rounded-xl px-4 py-3 text-sm text-center">
            Demo products are shown right now. Live products are not available, so checkout is disabled.
          </div>
        ) : null}
        <div className="flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
          <div className="relative flex-1">
            <Search className="w-5 h-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search products..."
              className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)] bg-white"
            />
          </div>
          <div className="flex gap-2 justify-center md:justify-end">
            <button
              type="button"
              onClick={loadProducts}
              className="px-4 py-3 border border-gray-300 rounded-xl hover:bg-gray-50 transition-colors bg-white"
            >
              Refresh
            </button>
            <label className="inline-flex items-center gap-2 px-4 py-3 border border-gray-300 rounded-xl bg-white text-sm text-gray-700">
              <input
                type="checkbox"
                checked={inStockOnly}
                onChange={(e) => setInStockOnly(e.target.checked)}
                className="accent-[var(--brand-primary)]"
              />
              In stock
            </label>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 justify-center">
          {categories.map((c) => {
            const isActive = c === category;
            return (
              <button
                key={c}
                type="button"
                onClick={() => setCategory(c)}
                className={
                  isActive
                    ? "px-6 py-2 bg-[var(--brand-accent)] text-white rounded-full transition-colors"
                    : "px-6 py-2 bg-white text-gray-700 rounded-full hover:bg-gray-100 transition-colors border border-gray-200"
                }
              >
                {c === "all" ? "All Products" : c}
              </button>
            );
          })}
        </div>

        {error ? <div className="text-sm text-red-600 text-center">{error}</div> : null}

        {isLoading ? (
          <div className="text-gray-600 text-center">Loading products...</div>
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No products found"
            description="Try a different search or category. Medicines are handled via the AI chat."
            actions={
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setCategory("all");
                  setInStockOnly(false);
                }}
                className="px-4 py-2 bg-[var(--brand-accent)] text-white rounded-lg hover:opacity-95 transition-colors"
              >
                Clear filters
              </button>
            }
          />
        ) : (
          <section
            className={`grid gap-6 ${
              isMinimal ? "md:grid-cols-2 lg:grid-cols-3" : "md:grid-cols-3 lg:grid-cols-4"
            }`}
          >
            {filtered.map((product) => {
              const stock = Number(product.stock_level ?? 0);
              const presentation = getProductPresentation(product);
              const Icon = presentation.Icon;
              const tone = colorClasses[presentation.color] ?? colorClasses.sky;
              const cardClass = isGlass
                ? "bg-white/70 backdrop-blur border border-white/70 shadow-lg"
                : isNeumorph
                  ? "bg-slate-100 border border-slate-200 shadow-[inset_-12px_-12px_24px_rgba(255,255,255,0.85),inset_12px_12px_24px_rgba(15,23,42,0.12)]"
                  : isFresh
                    ? "bg-white/95 border border-emerald-100 shadow-[0_18px_34px_rgba(16,185,129,0.16)]"
                    : "bg-white shadow-md";
              return (
                <div
                  key={product.id}
                  className={`${cardClass} rounded-2xl transition-all hover:-translate-y-1 overflow-hidden group`}
                >
                  <div className={`relative h-48 ${isNeumorph ? "bg-slate-100" : "bg-gray-100"} overflow-hidden`}>
                    <img
                      src={product.image_url || presentation.image}
                      alt={product.name}
                      className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-300"
                    />
                    <div className={`absolute top-3 right-3 w-10 h-10 ${tone} rounded-full flex items-center justify-center`}>
                      <Icon className="w-5 h-5" />
                    </div>
                  </div>
                  <div className="p-4">
                    <div className="text-xs text-gray-500 mb-1">
                      {product.category ? product.category : "Product"}
                      {stock > 0 ? ` - ${stock} in stock` : " - Out of stock"}
                    </div>
                    <h3 className="text-lg text-gray-900 mb-2 line-clamp-2">{product.name}</h3>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-2xl text-[var(--brand-accent)]">{formatMoney(Number(product.price ?? 0))}</span>
                      <button
                        type="button"
                        onClick={() => {
                          if (isUsingFallback) return;
                          addItem({
                            id: product.id,
                            name: product.name,
                            price: product.price,
                            image: product.image_url || presentation.image,
                          });
                        }}
                        disabled={isUsingFallback}
                        className={`px-4 py-2 text-white disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors text-sm ${
                          isNeumorph
                            ? "rounded-2xl bg-[var(--brand-accent)] shadow-[0_12px_24px_rgba(15,23,42,0.18)]"
                            : isFresh
                              ? "rounded-full bg-[var(--brand-accent)] shadow-[0_12px_22px_rgba(16,185,129,0.2)] hover:opacity-95"
                              : "rounded-lg bg-[var(--brand-accent)] hover:opacity-95"
                        }`}
                      >
                        {isUsingFallback ? "Unavailable" : "Add to Cart"}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </section>
        )}
      </section>

      <section className="bg-gradient-to-r from-[var(--brand-primary)] to-[var(--brand-primary-600)] rounded-3xl p-12 text-white text-center" id="assistant">
        <h2 className="text-4xl mb-4">Need medicines?</h2>
        <p className="text-xl mb-8 opacity-90">Use the AI assistant to ask about medicines and availability.</p>
        <button
          type="button"
          onClick={openChat}
          className="inline-flex items-center justify-center gap-2 px-8 py-4 bg-white text-[var(--brand-primary)] rounded-lg hover:bg-gray-100 transition-colors"
        >
          <MessageCircle className="w-5 h-5" />
          Chat with AI Assistant
        </button>
      </section>

      <section className="bg-white rounded-2xl p-8 md:p-10 shadow-md">
        <h2 className="text-3xl text-gray-900 mb-3">Medicines & safety</h2>
        <p className="text-gray-600">
          Always follow label instructions. For medicines, use the AI assistant so we can guide you to the correct workflow.
        </p>
      </section>
    </div>
  );
}
