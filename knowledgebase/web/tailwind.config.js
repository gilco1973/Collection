/** @type {import('tailwindcss').Config} */
// Design tokens follow the platform's AI Hub: cool grey ground, white surfaces, navy accent,
// Instrument Sans + Geist Mono. Light and dark palettes live in CSS variables injected here so the
// entry stylesheet keeps only the Tailwind directives.
const light = {
  "--bg": "#f3f5f8", "--surface": "#ffffff", "--surface-2": "#f8fafc", "--surface-3": "#eef2f6",
  "--ink": "#0f172a", "--ink-2": "#344054", "--muted": "#5b6779", "--faint": "#5c6b82",
  "--rule": "#e4e9f0", "--rule-2": "#d0d7e2",
  "--accent": "#2757a8", "--accent-2": "#1f4a91", "--accent-soft": "#e9effa", "--accent-ink": "#1d4a8a",
  "--ok": "#1f7a4d", "--ok-soft": "#e5f4ec", "--warn": "#8f4c0a", "--warn-soft": "#fdf1e2",
  "--crit": "#b42318", "--crit-soft": "#fbeae9", "--w2": "#9e350a", "--w2-soft": "#fdeadf",
  "--money": "#6941c6", "--money-soft": "#efe9fa", "--model": "#0e7490", "--model-soft": "#e0f2f7",
  "--r": "#475467", "--r-soft": "#f2f4f7",
  // Theme-invariant "spotlight" panel (matches the source design's single dark-emphasis band) and its
  // paired text colors, so it always reads as a dark accent surface in both themes, never flipping.
  "--emphasis": "#1e3a6e", "--on-emphasis": "#ffffff", "--on-emphasis-muted": "#c7d3e8",
  // Text/icon color for content sitting ON a solid --warn or --crit background (buttons, filled badges) —
  // separate from --warn/--crit's own role as TEXT on a *-soft background, because those two roles need
  // opposite values once --warn/--crit flip in dark mode.
  "--on-warn": "#ffffff", "--on-crit": "#ffffff",
  "--shadow-1": "0 1px 2px #1018280f", "--shadow-2": "0 8px 24px -8px #1018282e, 0 2px 6px #1018280f",
  "--shadow-3": "0 24px 64px -16px #10182859, 0 6px 18px #1018281a",
};
const dark = {
  "--bg": "#0b1220", "--surface": "#121a2b", "--surface-2": "#16203a", "--surface-3": "#1c2740",
  "--ink": "#e6ebf3", "--ink-2": "#c3cbd8", "--muted": "#8e9ab0", "--faint": "#9ba7bb",
  "--rule": "#243149", "--rule-2": "#33425f",
  "--accent": "#7fa6e6", "--accent-2": "#9ab8ec", "--accent-soft": "#18305a", "--accent-ink": "#bcd0f2",
  "--ok": "#5fc38f", "--ok-soft": "#123626", "--warn": "#e8a34a", "--warn-soft": "#3a2a10",
  "--crit": "#f08a80", "--crit-soft": "#42201d", "--w2": "#f0a070", "--w2-soft": "#40261a",
  "--money": "#b9a3f2", "--money-soft": "#2b2246", "--model": "#6fc7dc", "--model-soft": "#123640",
  "--r": "#b8c2d0", "--r-soft": "#1f2a3f",
  // Same theme-invariant panel as light: identical values, declared explicitly so this token is never
  // left to fall back to an undefined state (see artifact design rule: declare every token in :root).
  "--emphasis": "#1e3a6e", "--on-emphasis": "#ffffff", "--on-emphasis-muted": "#c7d3e8",
  // In dark mode --warn/--crit themselves become light (for their *-soft chip-text role), so text sitting
  // on a *solid* warn/crit background needs a dark color here instead of white.
  "--on-warn": "#2a1608", "--on-crit": "#2a1210",
  "--shadow-1": "0 1px 2px #00000066", "--shadow-2": "0 8px 24px -8px #00000099, 0 2px 6px #00000066",
  "--shadow-3": "0 24px 64px -16px #000000cc, 0 6px 18px #00000080",
};
const v = (name) => `var(${name})`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        bg: v("--bg"), surface: v("--surface"), "surface-2": v("--surface-2"), "surface-3": v("--surface-3"),
        ink: v("--ink"), "ink-2": v("--ink-2"), muted: v("--muted"), faint: v("--faint"),
        rule: v("--rule"), "rule-2": v("--rule-2"),
        accent: v("--accent"), "accent-2": v("--accent-2"), "accent-soft": v("--accent-soft"), "accent-ink": v("--accent-ink"),
        ok: v("--ok"), "ok-soft": v("--ok-soft"), warn: v("--warn"), "warn-soft": v("--warn-soft"),
        crit: v("--crit"), "crit-soft": v("--crit-soft"), w2: v("--w2"), "w2-soft": v("--w2-soft"),
        money: v("--money"), "money-soft": v("--money-soft"), model: v("--model"), "model-soft": v("--model-soft"),
        r: v("--r"), "r-soft": v("--r-soft"),
        emphasis: v("--emphasis"), "on-emphasis": v("--on-emphasis"), "on-emphasis-muted": v("--on-emphasis-muted"),
        "on-warn": v("--on-warn"), "on-crit": v("--on-crit"),
      },
      fontFamily: {
        ui: ['"Instrument Sans"', '"Segoe UI"', "system-ui", "Helvetica", "Arial", "sans-serif"],
        mono: ['"Geist Mono"', "ui-monospace", '"SF Mono"', "Menlo", "Consolas", "monospace"],
      },
      borderRadius: { s: "6px", DEFAULT: "8px", l: "12px" },
      // Matches the source design's own hub-rise keyframe and its two durations (tiles vs. wraps).
      keyframes: {
        rise: { "0%": { opacity: "0", transform: "translateY(6px)" }, "100%": { opacity: "1", transform: "none" } },
        "fade-in": { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        "scale-in": { "0%": { opacity: "0", transform: "scale(0.96)" }, "100%": { opacity: "1", transform: "scale(1)" } },
        "caret-blink": { "0%, 49%": { opacity: "1" }, "50%, 100%": { opacity: "0" } },
      },
      animation: {
        rise: "rise 220ms ease-out both",
        "rise-slow": "rise 260ms ease-out both",
        "fade-in": "fade-in 150ms ease-out both",
        "scale-in": "scale-in 150ms ease-out both",
        "caret-blink": "caret-blink 1s step-end infinite",
      },
      boxShadow: { 1: v("--shadow-1"), 2: v("--shadow-2"), 3: v("--shadow-3") },
      maxWidth: { wrap: "1200px" },
    },
  },
  plugins: [
    function tokens({ addBase }) {
      // Self-hosted, open-licensed faces (SIL OFL); no request leaves the bank. Latin subsets; other
      // scripts fall back to the system stack declared in fontFamily.
      const face = (family, weight, file) => ({
        fontFamily: family, fontStyle: "normal", fontWeight: weight, fontDisplay: "swap", src: `url("../fonts/${file}") format("woff2")`,
      });
      addBase([
        { "@font-face": face("Instrument Sans", "400 700", "InstrumentSans.woff2") }, // variable font
        { "@font-face": face("Geist Mono", "400 500", "GeistMono.woff2") },
      ]);
      addBase({
        ":root": light,
        "@media (prefers-color-scheme: dark)": { ":root": dark },
        // Explicit background/color on html+body: the console's own React root also paints bg-bg
        // (belt and braces — Layout.tsx's root element is what actually guarantees this on every
        // page), but an artifact host wraps this file in its own <body>, whose reset otherwise
        // shows through beneath anything that forgets to paint its own background (see artifact
        // design rule: "a transparent body silently borrows the host's ground").
        "html, body": { background: v("--bg"), color: v("--ink") },
        body: { fontFeatureSettings: '"tnum"', WebkitFontSmoothing: "antialiased" },
        // Matches the source design's own reduced-motion rule (there scoped to `.hub *`); global here
        // since nothing guarantees a single wrapper class in every embedding context (a platform
        // shell may mount the console straight into #root).
        "@media (prefers-reduced-motion: reduce)": {
          "*, *::before, *::after": { animationDuration: "0.01ms !important", animationIterationCount: "1 !important", transitionDuration: "0.01ms !important", scrollBehavior: "auto !important" },
        },
      });
    },
  ],
};
