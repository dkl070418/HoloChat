/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        // Telegram Desktop dark palette
        tg: {
          // window chrome / panels
          bg: '#0e1621',          // app background (deepest)
          panel: '#17212b',       // left list panel
          chatbg: '#0e1621',      // chat area base (pattern drawn over it)
          bubbleIn: '#182533',    // incoming bubble
          bubbleOut: '#2b5278',   // outgoing bubble
          bubbleOutHover: '#31608f',
          // text
          text: '#ffffff',
          textSec: '#7f91a4',     // secondary text (timestamps, subtitles)
          textLink: '#5eb5f7',
          // accents
          accent: '#5288c1',      // primary accent (buttons, selection)
          accentHover: '#3d6a9e',
          selected: '#2b5278',    // selected row in lists
          hover: '#202b36',       // hover row in lists
          active: '#2b5278',
          // inputs
          input: '#242f3d',
          inputFocus: '#2b5278',
          // status colors
          green: '#4dcd5e',       // online dot
          yellow: '#ffb02e',
          red: '#ec3942',
          // borders & separators
          border: '#101921',
          divider: '#101921',
        },
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      // Telegram-style motion: fast, springy but subtle
      transitionTimingFunction: {
        'tg-spring': 'cubic-bezier(0.34, 1.3, 0.64, 1)',
        'tg-out': 'cubic-bezier(0.25, 0.8, 0.25, 1)',
      },
      keyframes: {
        'tg-pop': {
          '0%': { opacity: '0', transform: 'scale(0.92) translateY(6px)' },
          '100%': { opacity: '1', transform: 'scale(1) translateY(0)' },
        },
        'tg-slide-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'tg-fade': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        'tg-pop': 'tg-pop 0.18s cubic-bezier(0.34, 1.3, 0.64, 1)',
        'tg-slide-up': 'tg-slide-up 0.22s cubic-bezier(0.25, 0.8, 0.25, 1)',
        'tg-fade': 'tg-fade 0.15s ease-out',
      },
    },
  },
  plugins: [],
}
