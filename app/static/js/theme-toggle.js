(function () {
  const updateButtons = (mode) => {
    document.body.dataset.theme = mode;
    const label = mode === "dark" ? "Light mode" : "Dark mode";
    document.querySelectorAll(".theme-toggle").forEach((btn) => {
      btn.dataset.mode = mode;
      btn.setAttribute("aria-pressed", mode === "dark");
      btn.setAttribute("title", label);
      btn.innerHTML = `<span class="theme-toggle-label">${label}</span>`;
    });
  };

  const persistTheme = (mode) => {
    fetch("/theme", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    }).catch((err) => console.error("Theme update failed", err));
  };

  document.addEventListener("click", (event) => {
    const button = event.target.closest(".theme-toggle");
    if (!button) {
      return;
    }
    event.preventDefault();
    const next = document.body.dataset.theme === "dark" ? "light" : "dark";
    updateButtons(next);
    persistTheme(next);
  });

  document.addEventListener("DOMContentLoaded", () => {
    const initial = document.body.dataset.theme || "light";
    updateButtons(initial);
  });
})();
