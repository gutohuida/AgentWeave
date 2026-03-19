import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Roboto', 'system-ui', 'sans-serif'],
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
        lg:  'var(--radius)',
        md:  'calc(var(--radius) - 2px)',
        sm:  'calc(var(--radius) - 4px)',
        '2xl': '1rem',
        '3xl': '1.5rem',
        '4xl': '1.75rem',
      },
    },
  },
  plugins: [],
}

export default config
