(function () {
  const toggleBtn = document.getElementById("theme-toggle");
  if (!toggleBtn) return;

  function currentTheme() {
    const attr = document.documentElement.getAttribute("data-theme");
    if (attr === "light" || attr === "dark") return attr;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function updateLabel(theme) {
    toggleBtn.textContent = theme === "dark" ? "☀️ 라이트모드" : "🌙 다크모드";
  }

  updateLabel(currentTheme());

  toggleBtn.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    updateLabel(next);
  });
})();
