// Run before styles paint so saved preferences and the system theme agree from the first frame.
(() => {
  const key = "ara-theme";
  const modes = ["system", "light", "dark"];
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  const normalize = (value) => (modes.includes(value) ? value : "system");
  let preference = "system";
  try {
    preference = normalize(localStorage.getItem(key));
  } catch {
    // The appearance still works when browser storage is unavailable.
  }
  function apply() {
    const theme = preference === "system"
      ? (system.matches ? "dark" : "light")
      : preference;
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.themePreference = preference;
    document.dispatchEvent(new Event("ara-theme-change"));
  }
  window.ARATheme = {
    get preference() {
      return preference;
    },
    set(value) {
      preference = normalize(value);
      try {
        localStorage.setItem(key, preference);
      } catch {
        // Keep the choice for this page even if it cannot be persisted.
      }
      apply();
    },
  };
  system.addEventListener("change", () => {
    if (preference === "system") apply();
  });
  window.addEventListener("storage", (event) => {
    if (event.key === key || event.key === null) {
      preference = normalize(event.newValue);
      apply();
    }
  });
  apply();
})();
