/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#05070d",
        panel: "#11141f",
        panel2: "#161b29",
        line: "#222a3d",
        txt: "#c7d2e0",
        dim: "#7c8aa3",
        accent: "#39ff14",
        accent2: "#22d3ee",
        warn: "#ffb020",
        bad: "#ff5470",
        good: "#39ff14",
      },
    },
  },
  plugins: [],
};
