/** @type {import('tailwindcss').Config} */

// Every colour resolves to a CSS variable defined in src/index.css, so the
// palette lives in exactly one place. Values are space-separated RGB channels
// so Tailwind's opacity modifiers (bg-primary/10) keep working.
const token = (name) => `rgb(var(--color-${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      colors: {
        navy: {
          950: token("navy-950"),
          900: token("navy-900"),
          800: token("navy-800"),
          700: token("navy-700"),
          300: token("navy-300"),
          100: token("navy-100"),
        },
        canvas: token("canvas"),
        surface: {
          DEFAULT: token("surface"),
          raised: token("surface-raised"),
          sunken: token("surface-sunken"),
        },
        ink: {
          DEFAULT: token("ink"),
          secondary: token("ink-secondary"),
          muted: token("ink-muted"),
        },
        line: {
          DEFAULT: token("line"),
          strong: token("line-strong"),
        },
        primary: {
          DEFAULT: token("primary"),
          hover: token("primary-hover"),
          soft: token("primary-soft"),
        },
        success: { DEFAULT: token("success"), soft: token("success-soft") },
        warning: { DEFAULT: token("warning"), soft: token("warning-soft") },
        danger:  { DEFAULT: token("danger"),  soft: token("danger-soft") },
      },
      spacing: {
        sidebar: "var(--layout-sidebar-width)",
        topbar: "var(--layout-topbar-height)",
      },
      borderRadius: {
        control: "var(--radius-control)",
        card: "var(--radius-card)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        raised: "var(--shadow-raised)",
        overlay: "var(--shadow-overlay)",
      },
      ringColor: {
        focus: "rgb(var(--color-focus) / 0.55)",
      },
      maxWidth: {
        content: "var(--layout-content-max)",
      },
    },
  },
  plugins: [],
};
