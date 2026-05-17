/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans:    ["Inter", "system-ui", "sans-serif"],
        display: ["Outfit", "system-ui", "sans-serif"],
      },
      colors: {
        primary: "#7c3aed",
      },
    },
  },
  plugins: [],
};

/*
 * Build the production CSS artifact (replaces tailwind-play-cdn.js):
 *
 *   npx tailwindcss \
 *     -i static/css/tailwind-input.css \
 *     -o static/css/tailwind.css \
 *     --minify
 *
 * Then in each template replace:
 *   <script src="/static/vendor/js/tailwind-play-cdn.js"></script>
 * with:
 *   <link rel="stylesheet" href="/static/css/tailwind.css"/>
 *
 * Estimated payload saving: ~300 KB (play CDN) → ~8–20 KB (purged build).
 */
