/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bittensor: {
          dark: "#0a0a0f",
          card: "#12121a",
          border: "#1e1e2e",
          accent: "#00d4aa",
          warning: "#f59e0b",
          danger: "#ef4444",
        },
      },
    },
  },
  plugins: [],
};
