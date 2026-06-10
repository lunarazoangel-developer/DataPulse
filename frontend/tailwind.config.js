/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0a0a0a',
          secondary: '#171717',
          tertiary: '#262626',
        },
        border: {
          DEFAULT: '#262626',
          light: '#404040',
        },
        text: {
          primary: '#e5e5e5',
          secondary: '#a3a3a3',
          muted: '#737373',
        },
        accent: {
          DEFAULT: '#ffffff',
          secondary: '#d4d4d4',
        },
        status: {
          red: '#ef4444',
          yellow: '#eab308',
          green: '#22c55e',
        }
      },
    },
  },
  plugins: [],
}
