<script setup>
import { useId } from "vue";

defineProps({ edition: { type: Number, required: true } });

const sealId = useId();
</script>

<template>
  <svg class="lu-edition-seal" viewBox="0 0 220 220" aria-hidden="true" focusable="false">
    <defs>
      <path :id="`${sealId}-top`" d="M45 102a68 68 0 0 1 130 0" />
    </defs>
    <circle cx="110" cy="110" r="91" />
    <circle cx="110" cy="110" r="82" />
    <text class="lu-seal-ring"><textPath :href="`#${sealId}-top`" startOffset="50%" text-anchor="middle">LE GUIDE DE LÜ</textPath></text>
    <g class="lu-seal-rain-mark">
      <path class="lu-seal-drop" d="M110 57c-5.5 10-14 19.5-14 31a14 14 0 0 0 28 0c0-11.5-8.5-21-14-31Z" />
      <path class="lu-seal-vein" d="M110 67c-3.8 8-7 14.5-7 21 0 5 2.4 8.6 7 11" />
      <path class="lu-seal-ripple" d="M102 92c5 3 11 3 16 0M104 97c4 2 8 2 12 0" />
      <circle class="lu-seal-core" cx="110" cy="86" r="1.7" />
    </g>
    <text class="lu-seal-year" x="110" y="133" text-anchor="middle">{{ edition }}</text>
    <text class="lu-seal-edition" x="110" y="151" text-anchor="middle">ÉDITION</text>
    <path class="lu-seal-divider" d="M70 162h24M126 162h24" />
    <circle class="lu-seal-core" cx="110" cy="162" r="1.5" />
    <text class="lu-seal-credit" x="110" y="178" text-anchor="middle">DUSKRAIN FOOD MAP</text>
  </svg>
</template>
