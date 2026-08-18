// The page matrix. Every route is shot once per theme, so cost is routes x
// themes — keep it to pages exercising distinct component surfaces, not every
// URL in urls.py.
//
// Only real HTML pages belong here. Several `/sys/.../manage/` URLs return
// `application/json` modal payloads (`{"html": "..."}`) that a browser renders
// as raw text in a <pre> — identical under all 12 themes, so they add no theme
// coverage while still producing diffs. shoot.mjs refuses non-HTML responses
// so one can't be added back by accident.
//
// phase 'setup' routes need an UNCONFIGURED database: system_setup_view
// redirects to options_view once SystemSettings.is_configured is true, and the
// middleware redirects everything else TO setup while it is false. The two
// phases therefore cannot share a database.

export const ROUTES = [
  { name: 'login',         path: '/accounts/login/',    auth: false, phase: 'main' },
  { name: 'options',       path: '/sys/options/',       auth: true,  phase: 'main' },
  { name: 'users',         path: '/sys/users/',         auth: true,  phase: 'main' },
  { name: 'profile',       path: '/accounts/profile/',  auth: true,  phase: 'main' },
  { name: 'logs',          path: '/sys/logs/',          auth: true,  phase: 'main' },
  { name: 'reports',       path: '/sys/reports/',       auth: true,  phase: 'main' },
  { name: 'backup',        path: '/sys/backup/',        auth: true,  phase: 'main' },
  { name: 'registrations', path: '/sys/registrations/', auth: true,  phase: 'main' },

  { name: 'setup',         path: '/sys/setup/',         auth: true,  phase: 'setup' },
];

// Mirrors _THEME_REGISTRY in dlux/themes.py. The 7 "full" themes are the
// refactor targets; the 5 palette themes are the reference shape and must not
// regress either.
export const THEMES = [
  'light', 'blue', 'gold', 'green', 'red',
  'mono', 'dark', 'gothic', 'retro', 'neon', 'prism', 'aether',
];

// Tall on purpose. shoot.mjs captures the viewport rather than fullPage,
// because a stitched full-page shot repaints `position: fixed` layers per
// scroll step and neon.css puts two full-viewport fixed overlays on <body> —
// which made neon irreproducible. 2400px clears these pages in one unstitched
// capture (the tallest, backup, renders ~1070px).
export const VIEWPORT = { width: 1440, height: 2400 };
export const BASE_URL = process.env.VISUAL_BASE_URL || 'http://127.0.0.1:8009';
export const CREDENTIALS = { username: 'visual', password: 'visual-harness-pw' };
