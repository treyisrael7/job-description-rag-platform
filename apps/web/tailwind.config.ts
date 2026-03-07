import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        zenodrift: {
          accent: "#ea580c",
          "accent-hover": "#c2410c",
          "accent-light": "#ffedd5",
          "accent-muted": "#f97316",
          surface: "#ffffff",
          "surface-muted": "#f8fafc",
          /* Warm ink typography (matches --ink, --muted, --heading) */
          text: "#423f3a",
          "text-muted": "#6b6560",
          "text-strong": "#2d2a26",
        },
      },
      backgroundImage: {
        "zenodrift-gradient":
          "linear-gradient(to bottom right, #fb923c, #fb7185, #fed7aa)",
        "zenodrift-hero":
          "linear-gradient(135deg, #ff8555 0%, #ff9670 20%, #ffa882 40%, #ffb894 60%, #ffc8a8 80%, #ffd9bd 100%)",
      },
      boxShadow: {
        "zenodrift-panel":
          "0 80px 160px -40px rgb(0 0 0 / 0.08), 0 40px 80px -40px rgb(0 0 0 / 0.04)",
        "zenodrift-hero":
          "0 8px 32px rgb(0 0 0 / 0.06), 0 2px 8px rgb(0 0 0 / 0.03)",
        "zenodrift-soft": "0 2px 8px rgb(0 0 0 / 0.03), 0 1px 2px rgb(0 0 0 / 0.02)",
        "zenodrift-soft-lg": "0 8px 30px rgb(0 0 0 / 0.06)",
      },
      borderRadius: {
        "zenodrift": "0.75rem",
        "zenodrift-lg": "1rem",
        "zenodrift-xl": "1.25rem",
        "zenodrift-2xl": "1.5rem",
        "zenodrift-3xl": "1.75rem",
        "zenodrift-panel": "1.5rem",
      },
    },
  },
  plugins: [],
};

export default config;
