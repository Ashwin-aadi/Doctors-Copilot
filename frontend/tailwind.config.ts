import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        "surface-3": "var(--surface-3)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        rail: {
          DEFAULT: "var(--rail)",
          2: "var(--rail-2)",
          fg: "var(--rail-fg)",
          muted: "var(--rail-muted)",
          active: "var(--rail-active)",
          border: "var(--rail-border)",
        },
        fg: "var(--fg)",
        "fg-muted": "var(--fg-muted)",
        "fg-subtle": "var(--fg-subtle)",
        primary: {
          DEFAULT: "var(--primary)",
          hover: "var(--primary-hover)",
          fg: "var(--primary-fg)",
          soft: "var(--primary-soft)",
          "soft-fg": "var(--primary-soft-fg)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
          fg: "var(--accent-fg)",
          soft: "var(--accent-soft)",
          "soft-fg": "var(--accent-soft-fg)",
        },
        // Each semantic colour carries the two foregrounds that are legible on
        // it: `fg` for text on the solid fill, `soft-fg` for text on the tinted
        // one. Both clear 4.5:1 in either theme -- never dim them with opacity.
        critical: {
          DEFAULT: "var(--critical)",
          fg: "var(--critical-fg)",
          soft: "var(--critical-soft)",
          "soft-fg": "var(--critical-soft-fg)",
        },
        high: {
          DEFAULT: "var(--high)",
          fg: "var(--high-fg)",
          soft: "var(--high-soft)",
          "soft-fg": "var(--high-soft-fg)",
        },
        moderate: {
          DEFAULT: "var(--moderate)",
          fg: "var(--moderate-fg)",
          soft: "var(--moderate-soft)",
          "soft-fg": "var(--moderate-soft-fg)",
        },
        normal: {
          DEFAULT: "var(--normal)",
          fg: "var(--normal-fg)",
          soft: "var(--normal-soft)",
          "soft-fg": "var(--normal-soft-fg)",
        },
        info: {
          DEFAULT: "var(--info)",
          fg: "var(--info-fg)",
          soft: "var(--info-soft)",
          "soft-fg": "var(--info-soft-fg)",
        },
        ring: "var(--ring)",
        chart: {
          1: "var(--chart-1)",
          2: "var(--chart-2)",
          3: "var(--chart-3)",
          4: "var(--chart-4)",
          5: "var(--chart-5)",
        },
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
      fontSize: {
        xs: "12px",
        sm: "14px",
        base: "16px",
        lg: "18px",
        xl: "22px",
        "2xl": "28px",
        "3xl": "34px",
      },
      spacing: {
        1: "4px",
        2: "8px",
        3: "12px",
        4: "16px",
        5: "20px",
        6: "24px",
        8: "32px",
        10: "40px",
        12: "48px",
        16: "64px",
        rail: "252px",
        "rail-sm": "68px",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "rise-in": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out both",
        "rise-in": "rise-in 220ms cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
  darkMode: ["selector", '[data-theme="dark"]'],
  plugins: [],
} satisfies Config;
