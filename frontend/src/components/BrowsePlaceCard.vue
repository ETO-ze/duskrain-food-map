<script setup>
import { computed, ref, watch } from "vue";
import { ArrowUpRight, Clock3, MapPin, Phone } from "@lucide/vue";

const props = defineProps({
  place: { type: Object, required: true },
  address: String,
  image: String,
  categories: { type: Array, default: () => [] },
  reviewHref: String,
  selected: Boolean,
  showCountry: Boolean,
});
defineEmits(["select"]);
const imageFailed = ref(false);
watch(() => props.image, () => { imageFailed.value = false; });
const showImage = computed(() => props.image && !props.place.hide_images && !imageFailed.value);
const phoneHref = computed(() => `tel:${String(props.place.phone || "").split(/[;；]/)[0]}`);
</script>

<template>
  <article class="place-item browse-place" :class="{ 'is-selected': selected }" tabindex="0" :aria-label="`在地图查看${place.name}`" @click="$emit('select', place)" @keydown.enter.self="$emit('select', place)" @keydown.space.self.prevent="$emit('select', place)">
    <header class="place-heading" :class="{ 'has-image': showImage }">
      <div class="place-identity">
        <h3 class="place-name">{{ place.name }}</h3>
        <div class="place-rating">
          <span class="place-score">{{ place.rating ?? '-' }}<small>/ 10</small></span>
          <span class="place-author">{{ place.rating_author || '吕俊泽' }}</span>
        </div>
      </div>
      <img v-if="showImage" class="place-photo" :src="image" :alt="place.name" width="76" height="76" loading="lazy" decoding="async" @error="imageFailed = true" />
    </header>

    <p v-if="address" class="place-address"><MapPin :size="14" :stroke-width="1.6" aria-hidden="true" /><span>{{ address }}</span></p>
    <div v-if="categories.length || place.recommend_level || (showCountry && place.country_code) || place.distanceKm != null" class="place-tags">
      <span v-if="place.distanceKm != null" class="place-distance">{{ place.distanceKm.toFixed(1) }} 公里</span>
      <span v-if="place.recommend_level" class="place-recommend">{{ place.recommend_level }}</span>
      <span v-for="category in categories" :key="category">{{ category }}</span>
      <span v-if="showCountry && place.country_code">{{ place.country_code }}</span>
    </div>
    <div v-if="place.business_hours || place.phone" class="place-contact">
      <p v-if="place.business_hours"><Clock3 :size="13" :stroke-width="1.6" aria-hidden="true" /><span>{{ place.business_hours }}</span></p>
      <p v-if="place.phone"><Phone :size="13" :stroke-width="1.6" aria-hidden="true" /><a :href="phoneHref" @click.stop>{{ place.phone }}</a></p>
    </div>
    <p v-if="place.note" class="place-note">{{ place.note }}</p>
    <a class="review-link place-review" :href="reviewHref" @click.stop>美食评价<ArrowUpRight :size="15" :stroke-width="1.7" aria-hidden="true" /></a>
  </article>
</template>

<style scoped>
.browse-place { display: grid; gap: 11px; padding: 16px; border-color: var(--line); background: var(--surface-card); cursor: pointer; transition: border-color 180ms ease, background-color 180ms ease, transform 180ms ease; }
.place-heading { display: grid; grid-template-columns: minmax(0, 1fr); align-items: start; min-width: 0; }
.place-heading.has-image { grid-template-columns: minmax(0, 1fr) 76px; gap: 14px; }
.place-identity { min-width: 0; }
.place-name { margin: 0; color: var(--text); font-size: 16px; line-height: 1.55; font-weight: 650; overflow-wrap: anywhere; }
.place-rating { display: flex; align-items: baseline; flex-wrap: wrap; gap: 6px 12px; margin-top: 7px; }
.place-score { display: inline-flex; align-items: baseline; gap: 5px; color: var(--yellow); font-size: 21px; line-height: 1.2; font-weight: 650; font-variant-numeric: tabular-nums; white-space: nowrap; }
.place-score small { font-size: 11px; font-weight: 450; color: var(--muted); }
.place-author { min-width: 0; color: var(--muted); font-size: 13px; line-height: 1.55; overflow-wrap: anywhere; }
.place-photo { display: block; width: 76px; height: 76px; object-fit: cover; border-radius: 5px; background: var(--surface-soft); }
.place-address { display: flex; align-items: flex-start; gap: 7px; margin: 0; color: var(--muted); font-size: 13px; line-height: 1.7; }
.place-address svg { margin-top: 3px; flex-shrink: 0; }
.place-address span { min-width: 0; overflow-wrap: anywhere; }
.place-tags { display: flex; flex-wrap: wrap; align-items: center; gap: 5px 7px; }
.place-tags > span { padding: 3px 7px; border-radius: 4px; background: var(--surface-soft); color: var(--muted); font-size: 11px; line-height: 1.4; overflow-wrap: anywhere; }
.place-tags > .place-recommend, .place-tags > .place-distance { color: var(--cyan); background: var(--accent-soft); }
.place-contact { display: grid; gap: 4px; color: var(--muted); }
.place-contact p { display: flex; align-items: flex-start; gap: 7px; margin: 0; font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
.place-contact svg { flex-shrink: 0; margin-top: 3px; }
.place-contact a { min-width: 0; color: inherit; text-decoration: none; }
.place-contact a:hover { text-decoration: underline; }
.place-note { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }
.place-review { display: inline-flex; align-items: center; gap: 5px; justify-self: start; min-height: 32px; color: var(--cyan); font-size: 12px; text-decoration: none; }
.place-review svg { transition: transform 180ms ease; }
.browse-place:focus-visible { outline: 2px solid var(--cyan); outline-offset: -2px; }
@media (hover: hover) and (pointer: fine) {
  .browse-place:hover { transform: translateX(2px); border-color: var(--accent-line-strong); background: var(--info-bg); }
  .browse-place:hover .place-review svg { transform: translate(2px, -2px); }
}
@media (prefers-reduced-motion: reduce) { .browse-place, .place-review svg { transition: none; } .browse-place:hover, .browse-place:hover .place-review svg { transform: none; } }
</style>
