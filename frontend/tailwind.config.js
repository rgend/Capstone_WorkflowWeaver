/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f2f0ff",
          100: "#e6e1ff",
          200: "#cabdff",
          300: "#ac95ff",
          400: "#8d6bff",
          500: "#6c4cff",
          600: "#5638e0",
          700: "#412bb0",
          800: "#2f2080",
          900: "#1e1554",
        },
      },
    },
  },
  plugins: [],
}
