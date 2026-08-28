import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
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
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
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
        6: "24px",
        8: "32px",
        12: "48px",
      },
    },
  },
  darkMode: ["selector", '[data-theme="dark"]'],
  plugins: [],
} satisfies Config;
