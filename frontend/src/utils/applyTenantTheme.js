const THEME_PRESETS = {
  classic: {
    primary_color: "#7CB342",
    primary_color_600: "#689F38",
    accent_color: "#3B82F6",
    font_family: 'system-ui, -apple-system, "Segoe UI", sans-serif',
  },
  fresh: {
    primary_color: "#22C55E",
    primary_color_600: "#16A34A",
    accent_color: "#0EA5E9",
    font_family: '"Nunito", "Segoe UI", system-ui, sans-serif',
  },
  minimal: {
    primary_color: "#111827",
    primary_color_600: "#0F172A",
    accent_color: "#334155",
    font_family: '"Space Grotesk", "Segoe UI", system-ui, sans-serif',
  },
};

export function applyTenantTheme(pharmacy) {
  if (typeof document === "undefined") return;

  const root = document.documentElement;
  const layout = String(pharmacy?.storefront_layout ?? "classic").toLowerCase();
  const presetKey = String(pharmacy?.theme_preset ?? "classic").toLowerCase();
  const preset = THEME_PRESETS[presetKey] ?? THEME_PRESETS.classic;
  const theme = {
    primary_color: pharmacy?.primary_color || preset.primary_color,
    primary_color_600: pharmacy?.primary_color_600 || preset.primary_color_600,
    accent_color: pharmacy?.accent_color || preset.accent_color,
    font_family: pharmacy?.font_family || preset.font_family,
  };

  document.body.dataset.theme = presetKey;
  document.body.dataset.layout = layout;

  root.style.setProperty("--brand-primary", theme.primary_color);
  root.style.setProperty("--brand-primary-600", theme.primary_color_600);
  root.style.setProperty("--brand-accent", theme.accent_color);
  root.style.setProperty("--brand-font-family", theme.font_family);
}
