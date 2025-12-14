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
        primary: "#FDE047", // Lemon yellow accent
        "primary-hover": "#FACC15",
        "primary-dim": "#EAB308",
        "background-light": "#F3F4F6",
        "background-dark": "#0B0C10", // Very dark background
        "surface-light": "#FFFFFF",
        "surface-dark": "#15171E", // Slightly lighter for cards
        "surface-darker": "#111217", // Sidebar/Header
        "card-dark": "#1E1F26",
        "border-dark": "#2A2D36",
        "text-secondary": "#9CA3AF",
        "text-dim": "#6B7280",
      },
      fontFamily: {
        display: ["Inter", "sans-serif"],
        body: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      borderRadius: {
        DEFAULT: "0.5rem",
      },
      boxShadow: {
        'glow-primary': '0 0 20px rgba(253, 224, 71, 0.3)',
        'glow-primary-lg': '0 0 30px rgba(253, 224, 71, 0.4)',
      },
    },
  },
  plugins: [],
}
