import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Colours come through as `rgb(var(--token) / <alpha-value>)` so every
      // utility accepts an opacity modifier: `bg-surface/80`, `ring-primary/20`.
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        "surface-2": "rgb(var(--surface-2) / <alpha-value>)",
        "surface-3": "rgb(var(--surface-3) / <alpha-value>)",
        border: "rgb(var(--border) / <alpha-value>)",
        "border-strong": "rgb(var(--border-strong) / <alpha-value>)",
        rail: {
          DEFAULT: "rgb(var(--rail) / <alpha-value>)",
          2: "rgb(var(--rail-2) / <alpha-value>)",
          fg: "rgb(var(--rail-fg) / <alpha-value>)",
          muted: "rgb(var(--rail-muted) / <alpha-value>)",
          active: "rgb(var(--rail-active) / <alpha-value>)",
          border: "rgb(var(--rail-border) / <alpha-value>)",
        },
        fg: "rgb(var(--fg) / <alpha-value>)",
        "fg-muted": "rgb(var(--fg-muted) / <alpha-value>)",
        "fg-subtle": "rgb(var(--fg-subtle) / <alpha-value>)",
        primary: {
          DEFAULT: "rgb(var(--primary) / <alpha-value>)",
          hover: "rgb(var(--primary-hover) / <alpha-value>)",
          fg: "rgb(var(--primary-fg) / <alpha-value>)",
          soft: "rgb(var(--primary-soft) / <alpha-value>)",
          "soft-fg": "rgb(var(--primary-soft-fg) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          hover: "rgb(var(--accent-hover) / <alpha-value>)",
          fg: "rgb(var(--accent-fg) / <alpha-value>)",
          soft: "rgb(var(--accent-soft) / <alpha-value>)",
          "soft-fg": "rgb(var(--accent-soft-fg) / <alpha-value>)",
        },
        // Each semantic colour carries the two foregrounds that are legible on
        // it: `fg` for text on the solid fill, `soft-fg` for text on the tinted
        // one. Both clear 4.5:1 in either theme -- never dim them with opacity.
        critical: {
          DEFAULT: "rgb(var(--critical) / <alpha-value>)",
          fg: "rgb(var(--critical-fg) / <alpha-value>)",
          soft: "rgb(var(--critical-soft) / <alpha-value>)",
          "soft-fg": "rgb(var(--critical-soft-fg) / <alpha-value>)",
        },
        high: {
          DEFAULT: "rgb(var(--high) / <alpha-value>)",
          fg: "rgb(var(--high-fg) / <alpha-value>)",
          soft: "rgb(var(--high-soft) / <alpha-value>)",
          "soft-fg": "rgb(var(--high-soft-fg) / <alpha-value>)",
        },
        moderate: {
          DEFAULT: "rgb(var(--moderate) / <alpha-value>)",
          fg: "rgb(var(--moderate-fg) / <alpha-value>)",
          soft: "rgb(var(--moderate-soft) / <alpha-value>)",
          "soft-fg": "rgb(var(--moderate-soft-fg) / <alpha-value>)",
        },
        normal: {
          DEFAULT: "rgb(var(--normal) / <alpha-value>)",
          fg: "rgb(var(--normal-fg) / <alpha-value>)",
          soft: "rgb(var(--normal-soft) / <alpha-value>)",
          "soft-fg": "rgb(var(--normal-soft-fg) / <alpha-value>)",
        },
        info: {
          DEFAULT: "rgb(var(--info) / <alpha-value>)",
          fg: "rgb(var(--info-fg) / <alpha-value>)",
          soft: "rgb(var(--info-soft) / <alpha-value>)",
          "soft-fg": "rgb(var(--info-soft-fg) / <alpha-value>)",
        },
        ring: "rgb(var(--ring) / <alpha-value>)",
        chart: {
          1: "rgb(var(--chart-1) / <alpha-value>)",
          2: "rgb(var(--chart-2) / <alpha-value>)",
          3: "rgb(var(--chart-3) / <alpha-value>)",
          4: "rgb(var(--chart-4) / <alpha-value>)",
          5: "rgb(var(--chart-5) / <alpha-value>)",
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
        xs: "var(--shadow-xs)",
        hover: "var(--shadow-hover)",
        primary: "var(--shadow-primary)",
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
      backgroundImage: {
        rail: "var(--rail-gradient)",
        hero: "var(--hero-gradient)",
      },
      transitionTimingFunction: {
        out: "var(--ease-out)",
        smooth: "var(--ease-in-out)",
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
        /* A panel arriving on screen: a little further than `rise-in`, used
           once per region rather than per row. */
        "slide-up": {
          from: { opacity: "0", transform: "translateY(12px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-left": {
          from: { opacity: "0", transform: "translateX(-14px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        "slide-in-right": {
          from: { opacity: "0", transform: "translateX(14px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.96)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        /* An expanding ring behind a live indicator -- the queue socket, an
           unread badge -- so "this is updating" reads without a spinner. */
        "pulse-ring": {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "70%": { transform: "scale(2.2)", opacity: "0" },
          "100%": { transform: "scale(2.2)", opacity: "0" },
        },
        /* The accent bar down the edge of a stat tile, growing from its base. */
        "bar-grow": {
          from: { transform: "scaleY(0)" },
          to: { transform: "scaleY(1)" },
        },
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out both",
        "rise-in": "rise-in 220ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "slide-up": "slide-up 320ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "slide-in-left": "slide-in-left 260ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "slide-in-right": "slide-in-right 260ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "scale-in": "scale-in 160ms cubic-bezier(0.22, 1, 0.36, 1) both",
        shimmer: "shimmer 1.6s infinite",
        "pulse-ring": "pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "bar-grow": "bar-grow 600ms cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
  darkMode: ["selector", '[data-theme="dark"]'],
  plugins: [],
} satisfies Config;
