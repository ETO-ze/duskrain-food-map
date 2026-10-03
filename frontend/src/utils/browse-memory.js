import { onBeforeUnmount, onMounted } from "vue";

export function useBrowseMemory(key, fields, panel) {
  let restored = null;
  try {
    restored = JSON.parse(sessionStorage.getItem(key) || "null");
    if (restored?.version === 1) {
      Object.entries(fields).forEach(([name, field]) => {
        const value = restored[name];
        if (name === "filters" && value && typeof value === "object") {
          Object.keys(field.value).forEach((filter) => {
            if (typeof value[filter] === "string") field.value[filter] = value[filter];
          });
        } else if (name === "mapTheme") {
          if (["day", "night"].includes(value)) field.value = value;
        } else if (typeof value === typeof field.value) field.value = value;
      });
    }
  } catch { /* Browsing remains available without session storage. */ }
  function save() {
    try {
      sessionStorage.setItem(key, JSON.stringify({ version: 1, ...Object.fromEntries(Object.entries(fields).map(([name, field]) => [name, field.value])), scrollTop: panel.value?.scrollTop || 0 }));
    } catch { /* Optional navigation memory. */ }
  }
  function restoreScroll() {
    if (!restored || !panel.value) return;
    panel.value.scrollTop = Math.max(0, Number(restored.scrollTop) || 0);
    restored = null;
  }
  onMounted(() => window.addEventListener("pagehide", save));
  onBeforeUnmount(() => { save(); window.removeEventListener("pagehide", save); });
  return { restoreScroll };
}
