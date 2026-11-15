/** Build: npx tailwindcss@3.4.17 -c tailwind/tailwind.config.js -i tailwind/input.css -o static/css/app.css --minify */
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      fontFamily: { sans: ["Vazirmatn", "Tahoma", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
