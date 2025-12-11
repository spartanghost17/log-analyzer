/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: {
          dark: "#101c22",   // Deep River Bed (Main Bg)
          light: "#f6f7f8",
        },
        panel: {
          dark: "#16232b",   // Component Bg
          light: "#2d2b15",  // Alternative
        },
        border: {
          dark: "#233c48",   // Subtle Borders
        },
        primary: {
          DEFAULT: "#facc15", // Lemon Yellow
          alt: "#2badee",     // Electric Blue
        },
        text: {
          muted: "#92b7c9",   // Blue-Gray
        },
        // Semantic
        success: "#22c55e",
        warning: "#f97316",
        error: "#facc15", // High contrast yellow for error in dark mode
      },
      fontFamily: {
        display: ["Manrope", "sans-serif"],
        body: ["Noto Sans", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
}
