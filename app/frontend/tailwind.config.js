/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ['"Inter Variable"', "system-ui", "-apple-system", "Segoe UI", "sans-serif"] },
      colors: {
        page: "#f5f7fa",
        surface: "#ffffff",
        sunken: "#f0f3f7",
        line: "#e3e8ef",
        lineStrong: "#cfd6e0",
        ink: { DEFAULT: "#0f1b2d", 2: "#44516a", 3: "#77839a" },
        brand: { 50: "#eef4fc", 100: "#dbe8f9", 200: "#b7d3f6", 500: "#2a78d6", 600: "#1c5cab", 700: "#184f95", 800: "#0d366b" },
        evidence: { 50: "#ecf7f3", 100: "#d3eee4", 600: "#0f7a5a", 700: "#0b6149" },
        attn: { 50: "#fff6e8", 100: "#fde9c8", 600: "#b25e09", 700: "#8f4a06" },
        crit: { 50: "#fdeeee", 600: "#c13838" },
        synth: { 50: "#f3f0fd", 600: "#5b46c9" },
      },
      boxShadow: {
        card: "0 1px 2px rgba(15,27,45,0.04), 0 1px 1px rgba(15,27,45,0.03)",
        pop: "0 12px 32px -8px rgba(15,27,45,0.18), 0 2px 6px rgba(15,27,45,0.06)",
      },
      borderRadius: { xl2: "14px" },
    },
  },
  plugins: [],
};
