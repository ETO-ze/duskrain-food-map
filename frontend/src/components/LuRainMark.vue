<script setup>
defineProps({
  count: { type: Number, default: 1 },
  variant: { type: String, default: "drops" },
});
</script>

<template>
  <div v-if="variant === 'rain-pick'" class="lu-pick-mark" aria-hidden="true">
    <svg viewBox="0 0 104 104" focusable="false">
      <circle cx="52" cy="52" r="44" />
      <circle class="lu-pick-dashes" cx="52" cy="52" r="36" />
      <path d="M52 27C46 37 39 43 39 55a13 13 0 0 0 26 0c0-12-7-18-13-28Z" />
      <path d="M47 58c3 2 7 2 10 0M48 63c3 1 5 1 8 0" />
      <circle cx="52" cy="49" r="1.8" class="lu-rain-core" />
    </svg>
  </div>
  <div v-else-if="variant === 'selected'" class="lu-selected-mark" aria-hidden="true">
    <span></span>
    <svg viewBox="0 0 42 56" focusable="false">
      <path d="M21 4C16 13 7 22 7 34a14 14 0 0 0 28 0C35 22 26 13 21 4Z" />
      <path d="M14 38c4 3 10 3 14 0M16 43c3 1 7 1 10 0" />
      <circle cx="21" cy="30" r="1.8" class="lu-rain-core" />
    </svg>
    <span></span>
  </div>
  <div v-else class="lu-drop-group" :class="`lu-drop-count-${count}`" aria-hidden="true">
    <svg v-for="index in count" :key="index" viewBox="0 0 72 96" focusable="false">
      <path class="lu-drop-outline" d="M36 5C28 20 12 36 12 58a24 24 0 0 0 48 0C60 36 44 20 36 5Z" />
      <path class="lu-rain-vein" d="M36 20c-4 11-10 20-10 33 0 7 3 12 10 17" />
      <path v-if="count > 1" class="lu-rain-vein" d="M42 29c5 9 7 17 5 26-1 5-4 9-8 13" />
      <path v-if="count > 2" class="lu-rain-vein" d="M30 34c-4 7-5 14-3 20 1 4 3 7 7 10" />
      <path class="lu-ripple" d="M23 69c8 5 18 5 26 0M26 76c7 3 13 3 20 0" />
      <path v-if="count > 2" class="lu-ripple" d="M30 82c4 1 8 1 12 0" />
      <circle class="lu-rain-core" cx="36" cy="58" r="2.2" />
    </svg>
  </div>
</template>
