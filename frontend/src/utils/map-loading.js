import { computed, onUnmounted, ref } from "vue";

export function useMapLoading(contentPending = null) {
  const phase = ref("sdk");
  const message = ref("");
  const dismissed = ref(false);
  const screenPhase = computed(() => phase.value === "ready" && contentPending?.value ? "data" : phase.value);
  const screenVisible = computed(() => screenPhase.value !== "ready" && !dismissed.value);
  let timer;
  let generation = 0;
  let disposed = false;
  function begin() {
    const id = ++generation;
    clearTimeout(timer);
    phase.value = "sdk";
    message.value = "";
    dismissed.value = false;
    timer = setTimeout(() => fail("地图连接较慢，请重试。店家列表仍可浏览。"), 35000);
    return id;
  }
  function current(id) { return !disposed && id === generation; }
  function rendering() {
    clearTimeout(timer);
    phase.value = "tiles";
    timer = setTimeout(() => fail("底图加载超时，请检查网络后重试。店家列表仍可浏览。"), 25000);
  }
  function ready() {
    if (disposed) return;
    clearTimeout(timer);
    phase.value = "ready";
    message.value = "";
  }
  function fail(text) {
    if (disposed) return;
    clearTimeout(timer);
    phase.value = "error";
    message.value = text;
  }
  onUnmounted(() => { disposed = true; generation++; clearTimeout(timer); });
  function dismiss() { dismissed.value = true; }
  function reveal() { dismissed.value = false; }
  return { phase, message, screenPhase, screenVisible, dismiss, reveal, begin, current, rendering, ready, fail };
}
