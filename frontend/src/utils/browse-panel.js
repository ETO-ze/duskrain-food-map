import { nextTick, onBeforeUnmount, onMounted, watch } from "vue";

export function useBrowseResults(panel, list, sources) {
  let disposed = false;
  async function revealFirstResult() {
    await nextTick();
    const element = panel.value;
    const results = list.value;
    if (disposed || !element || !results || element.closest("[inert]") || getComputedStyle(element).display === "none") return;
    const controls = element.querySelector(".browse-controls");
    if (!controls) return;
    const overlap = controls.getBoundingClientRect().bottom + 12 - results.getBoundingClientRect().top;
    if (overlap <= 0) return;
    element.scrollBy({ top: -overlap, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }
  watch(sources, revealFirstResult, { deep: true });
  function stopAutomaticScroll(event) {
    if (event.type === "pointerdown" && !event.target.closest?.(".list")) return;
    const element = panel.value;
    if (element) element.scrollTo({ top: element.scrollTop, behavior: "instant" });
  }
  const events = ["wheel", "touchstart", "pointerdown"];
  onMounted(() => events.forEach(event => panel.value?.addEventListener(event, stopAutomaticScroll, { passive: true })));
  onBeforeUnmount(() => {
    disposed = true;
    events.forEach(event => panel.value?.removeEventListener(event, stopAutomaticScroll));
  });
}
