/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        // "navy" token name kept for class stability, but recolored to a warm
        // ink/charcoal so Candidly looks distinct from the blue reference.
        navy: {
          DEFAULT: "#17191f",
          800: "#21242c",
          700: "#2c3038",
        },
        brand: {
          DEFAULT: "#0d9488",
          600: "#0f766e",
          500: "#14b8a6",
        },
        accent: {
          DEFAULT: "#f59e0b",
        },
      },
      borderRadius: {
        "4xl": "1.5rem",
      },
      boxShadow: {
        card: "0 12px 38px -16px rgba(13, 148, 136, 0.22)",
      },
    },
  },
  plugins: [],
};
