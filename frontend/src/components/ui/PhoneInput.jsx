import { useEffect, useMemo, useState } from "react";
import { COUNTRIES } from "../../utils/countries";

const DEFAULT_COUNTRY_CODE = "LB";

const getDefaultCountry = () => COUNTRIES.find((c) => c.code === DEFAULT_COUNTRY_CODE) ?? COUNTRIES[0];

const getDialCodeOrder = () =>
  [...new Set(COUNTRIES.map((c) => c.dialCode))].sort((a, b) => b.length - a.length);

const parseE164 = (value) => {
  if (!value || typeof value !== "string") return null;
  const digits = value.replace(/\D/g, "");
  if (!digits) return null;
  const dialCodes = getDialCodeOrder();
  for (const code of dialCodes) {
    if (digits.startsWith(code)) {
      const country = COUNTRIES.find((c) => c.dialCode === code) ?? getDefaultCountry();
      return { country, national: digits.slice(code.length) };
    }
  }
  return null;
};

export default function PhoneInput({ value, onChange, required = false, id, name, placeholder = "Phone number", className = "" }) {
  const [country, setCountry] = useState(getDefaultCountry());
  const [national, setNational] = useState("");
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!value) {
      setNational("");
      setCountry(getDefaultCountry());
      return;
    }
    const parsed = parseE164(value);
    if (parsed) {
      setCountry(parsed.country);
      setNational(parsed.national);
    }
  }, [value]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return COUNTRIES;
    return COUNTRIES.filter((c) => {
      return (
        c.name.toLowerCase().includes(q) ||
        c.code.toLowerCase().includes(q) ||
        c.dialCode.includes(q.replace("+", ""))
      );
    });
  }, [query]);

  const updatePhone = (nextCountry, nextNational) => {
    const digits = nextNational.replace(/\D/g, "");
    const nextValue = digits ? `+${nextCountry.dialCode}${digits}` : "";
    onChange(nextValue);
  };

  const handleNationalChange = (event) => {
    const digits = event.target.value.replace(/\D/g, "");
    setNational(digits);
    updatePhone(country, digits);
  };

  const handleCountrySelect = (selected) => {
    setCountry(selected);
    setIsOpen(false);
    setQuery("");
    updatePhone(selected, national);
  };

  return (
    <div className="relative">
      <div className="flex items-center gap-2">
        <div className="relative">
          <button
            type="button"
            onClick={() => setIsOpen((prev) => !prev)}
            className="h-11 px-3 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 hover:bg-slate-50"
            aria-haspopup="listbox"
            aria-expanded={isOpen}
          >
            {country.code} +{country.dialCode}
          </button>
          {isOpen ? (
            <div className="absolute z-30 mt-2 w-64 rounded-lg border border-slate-200 bg-white shadow-lg p-2">
              <input
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search country"
                className="w-full px-3 py-2 mb-2 border border-slate-200 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
              />
              <div className="max-h-56 overflow-y-auto">
                {filtered.map((option) => (
                  <button
                    key={`${option.code}-${option.dialCode}`}
                    type="button"
                    onClick={() => handleCountrySelect(option)}
                    className="w-full text-left px-3 py-2 rounded-md text-sm text-slate-700 hover:bg-slate-50"
                  >
                    {option.name} ({option.code}) +{option.dialCode}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        <input
          id={id}
          name={name}
          type="tel"
          inputMode="tel"
          value={national}
          onChange={handleNationalChange}
          placeholder={placeholder}
          required={required}
          className={`h-11 flex-1 px-3 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)] ${className}`}
        />
      </div>
    </div>
  );
}
