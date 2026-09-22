/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0fdf4',
          100: '#dcfce7',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
          800: '#166534',
          900: '#14532d',
        },
        gov: {
          50: '#f0f6fc',
          100: '#e1edf8',
          200: '#c3dbf2',
          600: '#1d63a8',
          700: '#154e89',
          800: '#0f4071',
          900: '#0b2e52',
          950: '#071f38',
        }
      }
    },
  },
  plugins: [],
}
