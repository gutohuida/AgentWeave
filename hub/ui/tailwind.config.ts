import type { Config } from 'tailwindcss'
import plugin from 'tailwindcss/plugin'

const config: Config = {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        // Was ['Roboto', ...] — a third font declaration for a face that was
        // never loaded, so every `font-sans` utility silently fell back to the
        // system face. Now matches the self-hosted families in index.css.
        sans: ['DM Sans Variable', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI',
               'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      colors: {
        border:      'var(--border)',
        input:       'var(--input)',
        ring:        'var(--ring)',
        background:  'var(--background)',
        foreground:  'var(--foreground)',
        primary: {
          DEFAULT:    'var(--primary)',
          foreground: 'var(--primary-foreground)',
        },
        secondary: {
          DEFAULT:    'var(--secondary)',
          foreground: 'var(--secondary-foreground)',
        },
        destructive: {
          DEFAULT:    'var(--destructive)',
          foreground: 'var(--destructive-foreground)',
        },
        muted: {
          DEFAULT:    'var(--muted)',
          foreground: 'var(--muted-foreground)',
        },
        accent: {
          DEFAULT:    'var(--accent)',
          foreground: 'var(--accent-foreground)',
        },
        popover: {
          DEFAULT:    'var(--background)',
          foreground: 'var(--foreground)',
        },
        card: {
          DEFAULT:    'var(--background)',
          foreground: 'var(--foreground)',
        },
        /* Material 3 extra tokens */
        'p-cont':    'var(--p-cont)',
        'on-p-cont': 'var(--on-p-cont)',
        's-cont':    'var(--s-cont)',
        'on-s-cont': 'var(--on-s-cont)',
        't-cont':    'var(--t-cont)',
        'on-t-cont': 'var(--on-t-cont)',
        'sur-var':   'var(--sur-var)',
        'on-sv':     'var(--on-sv)',
        'm-divider': 'var(--m-divider)',
        /* M3 Surface Containers */
        'surface-lowest':  'var(--surface-lowest)',
        'surface-low':     'var(--surface-low)',
        'surface-high':    'var(--surface-high)',
        'surface-highest': 'var(--surface-highest)',
        /* M3 Outline */
        'outline':         'var(--outline)',
        'outline-variant': 'var(--outline-variant)',
        'scrim':           'var(--scrim)',
        /* M3 Error Container */
        'error-cont':      'var(--error-cont)',
        'on-error-cont':   'var(--on-error-cont)',
      },
      borderRadius: {
        sm:  'var(--radius-sm)',
        md:  'var(--radius-md)',
        lg:  'var(--radius-lg)',
        xl:  'var(--radius-xl)',
        // Self-contained results are markedly softer than chrome.
        content: 'var(--radius-content)',
        '2xl': '1rem',
        '3xl': '1.5rem',
        '4xl': '1.75rem',
      },
      transitionDuration: {
        fast: 'var(--dur-fast)',
        base: 'var(--dur-base)',
        slow: 'var(--dur-slow)',
      },
      transitionTimingFunction: {
        DEFAULT: 'var(--ease)',
        smooth: 'var(--ease)',
      },
    },
  },
  plugins: [
    // `pointer-coarse:` is a Tailwind v4 variant; this project is on v3.4.
    plugin(({ addVariant }) => {
      addVariant('pointer-coarse', '@media (pointer: coarse)')
      addVariant('pointer-fine', '@media (pointer: fine)')
    }),
  ],
}

export default config
