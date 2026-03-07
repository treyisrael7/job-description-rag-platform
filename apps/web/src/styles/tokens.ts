/**
 * Zenodrift design tokens
 * Warm, premium aesthetic: orange → coral → peach
 */

export const zenodrift = {
  colors: {
    // Gradient stops (warm: orange → coral → peach)
    gradient: {
      from: "#fb923c",   // orange-400
      via: "#fb7185",    // rose-400 (coral)
      to: "#fed7aa",     // orange-200 (peach)
    },
    // Primary accent for CTAs
    accent: "#ea580c",   // orange-600
    accentHover: "#c2410c", // orange-700
    accentLight: "#ffedd5", // orange-100
    accentMuted: "#f97316", // orange-500 (fallback)
    // Surface
    surface: "#ffffff",
    surfaceMuted: "#f8fafc",   // slate-50
    surfaceRaised: "#ffffff",
    // Text: muted charcoal
    text: "#334155",     // slate-700
    textMuted: "#64748b", // slate-500
    textStrong: "#1e293b", // slate-800
  },
  boxShadow: {
    panel: "0 8px 30px rgb(0 0 0 / 0.06)",
    glow: "0 0 45px rgba(251, 146, 60, 0.25), 0 8px 30px rgb(0 0 0 / 0.06)",
    soft: "0 4px 20px rgb(0 0 0 / 0.04)",
    "soft-lg": "0 8px 40px rgb(0 0 0 / 0.06)",
  },
  radius: {
    md: "0.75rem",   // 12px
    lg: "1rem",      // 16px
    xl: "1.25rem",   // 20px
    "2xl": "1.5rem", // 24px
    "3xl": "1.75rem", // 28px
    panel: "1.5rem", // main panel
  },
} as const;
