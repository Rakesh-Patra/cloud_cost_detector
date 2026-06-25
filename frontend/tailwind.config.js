/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class', // Support toggling dark mode via class if needed, default is dark anyway
  theme: {
    extend: {
      colors: {
        darkBg: '#090a0f',
        darkCard: '#121420',
        brandPurple: '#8b5cf6',
        brandIndigo: '#6366f1',
      }
    },
  },
  plugins: [],
}
