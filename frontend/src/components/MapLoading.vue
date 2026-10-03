<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { ArrowRight, List, MapPin, Moon, RotateCcw, Sun, WifiOff } from "@lucide/vue";
import LuRainMark from "./LuRainMark.vue";

const props = defineProps({ phase: String, message: String, provider: String, theme: String, visible: { type: Boolean, default: true } });
const emit = defineEmits(["retry", "list", "theme"]);
const loadingElement = ref(null);
let previousFocus = null;

const isError = computed(() => props.phase === "error");
const providerLabel = computed(() => props.provider === "AMAP" ? "高德地图" : "Google Maps");
const status = computed(() => isError.value
  ? props.message || "暂时无法连接地图服务，请稍后重试。"
  : props.phase === "sdk" ? "正在连接地图服务" : props.phase === "data" ? "正在准备店家指南" : "正在展开地图与店家位置");

watch(() => props.visible && props.phase !== "ready", async (visible) => {
  if (visible) previousFocus = document.activeElement;
  await nextTick();
  if (visible) loadingElement.value?.focus({ preventScroll: true });
  else if (previousFocus?.isConnected && !previousFocus.closest("[inert]")) previousFocus.focus({ preventScroll: true });
}, { immediate: true });

function handleKeydown(event) {
  if (event.key === "Escape") { emit("list"); return; }
  if (event.key !== "Tab") return;
  const controls = loadingElement.value?.querySelectorAll("button:not([disabled])");
  if (!controls?.length) return;
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && (document.activeElement === first || document.activeElement === loadingElement.value)) {
    event.preventDefault(); last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault(); first.focus();
  }
}
</script>

<template>
  <Teleport to="body">
  <Transition name="map-reveal">
    <section v-if="visible && phase !== 'ready'" ref="loadingElement" class="map-loading" :class="{ 'is-error': isError }" role="dialog" aria-modal="true" aria-label="DuskRain 美食地图加载" tabindex="-1" @keydown="handleKeydown">
      <header class="loading-header">
      <div class="loading-masthead" aria-hidden="true">
        <MapPin :size="18" :stroke-width="1.4" />
        <span>TASTE MAP</span>
      </div>
      <button class="loading-theme" type="button" :aria-label="theme === 'night' ? '切换到日间地图' : '切换到夜间地图'" :title="theme === 'night' ? '日间地图' : '夜间地图'" @click="$emit('theme')">
        <Sun v-if="theme === 'night'" :size="20" :stroke-width="1.6" /><Moon v-else :size="20" :stroke-width="1.6" />
      </button>
      </header>

      <div class="map-loading-content">
        <div class="loading-emblem">
          <span class="emblem-track" />
          <span v-if="!isError" class="emblem-orbit" role="progressbar" :aria-label="status" />
          <div class="emblem-core" aria-hidden="true">
            <WifiOff v-if="isError" :size="38" :stroke-width="1.3" />
            <LuRainMark v-else variant="selected" />
          </div>
        </div>

        <div class="loading-identity">
          <p class="loading-wordmark">DuskRain<span>.</span></p>
          <h2>{{ isError ? '地图暂未连接' : '美食地图' }}</h2>
        </div>

        <div class="loading-status" role="status" aria-live="polite" aria-atomic="true">
          <p class="loading-caption">{{ status }}</p>
        </div>

        <div class="loading-actions">
          <button v-if="isError" type="button" class="loading-retry" @click="$emit('retry')"><RotateCcw :size="16" />重新连接</button>
          <button type="button" class="loading-list-link" @click="$emit('list')"><List :size="17" /><span>先看店家列表</span><ArrowRight class="list-arrow" :size="16" /></button>
        </div>
      </div>

      <footer class="loading-footer"><span>个人评分 · 真实探店</span><span class="loading-provider"><i aria-hidden="true" />{{ providerLabel }}</span></footer>
    </section>
  </Transition>
  </Teleport>
</template>

<style scoped>
.map-loading {
  --loading-surface: #17191b;
  --loading-ink: #eceeec;
  --loading-secondary: #a0a6a5;
  --loading-hairline: #323837;
  --loading-accent: #86bdb5;
  --loading-core: #202624;
  --loading-coral: #d78a75;
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  padding: 28px 36px 24px;
  overflow-y: auto;
  background: var(--loading-surface);
  color: var(--loading-ink);
  letter-spacing: 0;
  outline: none;
}
body.map-day .map-loading {
  --loading-surface: #fbfcfa;
  --loading-ink: #242a29;
  --loading-secondary: #6b7672;
  --loading-hairline: #e0e7e3;
  --loading-accent: #457c70;
  --loading-core: #f0f4f0;
  --loading-coral: #b56550;
}
.loading-header { display: flex; justify-content: space-between; align-items: center; gap: 20px; flex-shrink: 0; }
.loading-masthead { display: flex; align-items: center; gap: 10px; min-height: 26px; color: var(--loading-secondary); font-size: 10px; white-space: nowrap; }
.loading-theme { display: grid; place-items: center; width: 44px; height: 44px; padding: 0; background: transparent; color: var(--loading-secondary); border: 1px solid var(--loading-hairline); border-radius: 6px; }
.loading-theme:hover { color: var(--loading-ink); background: var(--loading-core); }
.loading-theme:focus-visible { outline: 2px solid var(--loading-accent); outline-offset: 3px; }
.loading-masthead svg { flex-shrink: 0; color: var(--loading-accent); }
.map-loading-content { width: min(100%, 360px); margin: auto; padding: 42px 0; text-align: center; flex-shrink: 0; }
.loading-emblem { position: relative; width: 142px; height: 142px; margin: 0 auto 34px; }
.emblem-track, .emblem-orbit { position: absolute; inset: 0; border: 1px solid var(--loading-hairline); border-radius: 50%; }
.emblem-orbit { border-color: transparent; border-top-color: var(--loading-accent); animation: orbit 3.2s linear infinite; }
.emblem-core { position: absolute; inset: 17px; display: grid; place-items: center; border-radius: 50%; background: var(--loading-core); color: var(--loading-accent); }
.emblem-core :deep(.lu-selected-mark) { display: block; width: 47px; height: 63px; }
.emblem-core :deep(.lu-selected-mark > span) { display: none; }
.emblem-core :deep(svg) { width: 100%; height: 100%; fill: none; stroke: currentColor; stroke-width: 1.05; stroke-linecap: round; stroke-linejoin: round; }
.emblem-core :deep(.lu-rain-core) { fill: var(--loading-coral); stroke: none; }
.loading-wordmark { margin: 0; font-size: 34px; line-height: 1.2; font-weight: 600; }
.loading-wordmark > span { color: var(--loading-coral); }
h2 { margin: 10px 0 0; font-size: 18px; line-height: 1.5; font-weight: 450; }
.loading-status { margin-top: 32px; }
.loading-caption { margin: 0; min-height: 22px; color: var(--loading-secondary); font-size: 12px; line-height: 1.8; overflow-wrap: anywhere; }
.loading-actions { display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 28px; }
.loading-list-link, .loading-retry { display: inline-flex; justify-content: center; align-items: center; gap: 9px; min-height: 44px; max-width: 100%; padding: 0 15px; border: 1px solid var(--loading-hairline); border-radius: 6px; background: transparent; color: var(--loading-ink); font-size: 12px; transition: background-color 160ms ease, border-color 160ms ease; }
.loading-list-link:hover { background: var(--loading-core); border-color: var(--loading-accent); }
.loading-list-link:focus-visible, .loading-retry:focus-visible { outline: 2px solid var(--loading-accent); outline-offset: 4px; }
.list-arrow { margin-left: 10px; color: var(--loading-secondary); }
.loading-retry { background: var(--loading-ink); color: var(--loading-surface); border-color: var(--loading-ink); }
.loading-retry:hover { background: var(--loading-accent); border-color: var(--loading-accent); }
.loading-footer { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; padding-top: 17px; border-top: 1px solid var(--loading-hairline); color: var(--loading-secondary); font-size: 10px; flex-shrink: 0; }
.loading-provider { display: inline-flex; align-items: center; gap: 6px; }
.loading-provider i { width: 4px; height: 4px; border-radius: 50%; background: var(--loading-accent); }
.is-error .emblem-core { color: var(--loading-secondary); }
.is-error .emblem-core > svg { width: 38px; height: 38px; }
.is-error .loading-caption { max-width: 310px; margin: 0 auto; }
.map-reveal-leave-active { transition: opacity 240ms ease; pointer-events: none; }
.map-reveal-leave-to { opacity: 0; }
@keyframes orbit { to { transform: rotate(360deg); } }
@media (max-width: 860px) {
  .map-loading { padding: max(24px, env(safe-area-inset-top)) 24px max(22px, env(safe-area-inset-bottom)); }
  .map-loading-content { padding: 38px 0; }
}
@media (max-height: 650px) {
  .map-loading-content { padding: 24px 0; }
  .loading-emblem { width: 110px; height: 110px; margin-bottom: 22px; }
  .emblem-core { inset: 13px; }
  .emblem-core :deep(.lu-selected-mark) { width: 35px; height: 47px; }
  .loading-status { margin-top: 24px; }
  .loading-actions { margin-top: 20px; }
}
@media (max-height: 500px) and (min-width: 480px) {
  .map-loading-content { display: grid; grid-template-columns: 96px minmax(0, 280px); column-gap: 30px; width: min(100%, 406px); padding: 18px 0; text-align: left; }
  .loading-emblem { grid-row: 1 / 4; align-self: center; width: 96px; height: 96px; margin: 0; }
  .loading-status { margin-top: 14px; }
  .loading-actions { justify-content: flex-start; margin-top: 16px; }
  .loading-footer { padding-top: 10px; }
}
@media (prefers-reduced-motion: reduce) {
  .emblem-orbit { animation: none; }
  .map-reveal-leave-active, .loading-list-link, .loading-retry { transition: none; }
}
</style>
