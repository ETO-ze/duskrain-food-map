<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { placeCategories } from "../utils/categories";
import { formatAddress } from "../utils/map";

const props = defineProps({
  places: { type: Array, required: true },
  enableCategoryFilter: { type: Boolean, default: false },
  enableSort: { type: Boolean, default: false },
});

defineEmits(["edit", "delete", "new"]);

const categoryFilter = ref("");
const sortMode = ref("created_desc");
const sortMenu = ref(null);
const uncategorizedValue = "__uncategorized__";
const categoryOptions = computed(() => [...new Set(
  props.places.flatMap(placeCategories),
)].sort((a, b) => a.localeCompare(b, "zh-CN")));
const hasUncategorized = computed(() => props.places.some((place) => !placeCategories(place).length));
const visiblePlaces = computed(() => {
  let items = props.places;
  if (props.enableCategoryFilter && categoryFilter.value === uncategorizedValue) {
    items = props.places.filter((place) => !placeCategories(place).length);
  } else if (props.enableCategoryFilter && categoryFilter.value) {
    items = props.places.filter((place) => placeCategories(place).includes(categoryFilter.value));
  }
  if (!props.enableSort) return items;
  return [...items].sort((left, right) => {
    if (sortMode.value === "rating_desc") {
      const leftRating = Number(left.rating);
      const rightRating = Number(right.rating);
      const leftHasRating = left.rating !== null && left.rating !== "" && Number.isFinite(leftRating);
      const rightHasRating = right.rating !== null && right.rating !== "" && Number.isFinite(rightRating);
      if (leftHasRating !== rightHasRating) return leftHasRating ? -1 : 1;
      if (leftHasRating && leftRating !== rightRating) return rightRating - leftRating;
    }
    return String(right.created_at || "").localeCompare(String(left.created_at || ""));
  });
});

function selectSort(mode) {
  sortMode.value = mode;
  if (sortMenu.value) sortMenu.value.open = false;
}

function closeSortMenu(event) {
  if (sortMenu.value?.open && !sortMenu.value.contains(event.target)) sortMenu.value.open = false;
}

onMounted(() => document.addEventListener("click", closeSortMenu));
onUnmounted(() => document.removeEventListener("click", closeSortMenu));

watch(categoryOptions, (options) => {
  if (
    categoryFilter.value
    && categoryFilter.value !== uncategorizedValue
    && !options.includes(categoryFilter.value)
  ) {
    categoryFilter.value = "";
  }
});
</script>

<template>
  <section class="admin-module admin-saved">
    <div class="section-title">
      <span>已添加店家</span>
      <button class="btn secondary compact" type="button" @click="$emit('new')">新建店家</button>
    </div>
    <div v-if="enableCategoryFilter" class="admin-list-filter">
      <div class="field">
        <label for="savedPlaceCategory">菜系筛选</label>
        <select id="savedPlaceCategory" v-model="categoryFilter">
          <option value="">全部菜系（{{ places.length }}）</option>
          <option v-for="category in categoryOptions" :key="category" :value="category">
            {{ category }}
          </option>
          <option v-if="hasUncategorized" :value="uncategorizedValue">未分类</option>
        </select>
      </div>
      <div class="admin-list-filter-actions">
        <span class="pill">当前 {{ visiblePlaces.length }} 家</span>
        <details v-if="enableSort" ref="sortMenu" class="place-sort-menu" @keydown.esc="sortMenu.open = false">
          <summary class="place-sort-trigger" title="调整店家排序" aria-label="调整店家排序">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M3.5 5h11l-4.2 5.1v6.2l-2.7 1.8v-8z" />
              <path d="M15.5 10.5h5M15.5 14.5h4M15.5 18.5h3" />
            </svg>
          </summary>
          <div class="place-sort-popover" role="menu" aria-label="排序方式">
            <button type="button" role="menuitemradio" :aria-checked="sortMode === 'created_desc'" @click="selectSort('created_desc')">
              <span>最近添加</span><span aria-hidden="true">{{ sortMode === "created_desc" ? "✓" : "" }}</span>
            </button>
            <button type="button" role="menuitemradio" :aria-checked="sortMode === 'rating_desc'" @click="selectSort('rating_desc')">
              <span>评分最高</span><span aria-hidden="true">{{ sortMode === "rating_desc" ? "✓" : "" }}</span>
            </button>
          </div>
        </details>
      </div>
    </div>
    <section class="list admin-list">
      <article v-if="!places.length" class="place-item">
        <p class="subtle">还没有保存店铺。先搜索一家店。</p>
      </article>
      <article v-else-if="!visiblePlaces.length" class="place-item">
        <p class="subtle">当前菜系下没有店家。</p>
      </article>
      <article v-for="place in visiblePlaces" :key="place.id" class="place-item" @click="$emit('edit', place)">
        <div class="item-title">
          <span>{{ place.name }}</span>
          <span class="rating">{{ place.rating ?? "-" }} / 10 · {{ place.rating_author || "吕俊泽" }}</span>
        </div>
        <div class="subtle">{{ formatAddress(place) }}</div>
        <div class="pill-row">
          <span class="pill">{{ place.map_provider === "google" ? "Google" : "高德" }}</span>
          <span v-if="place.country_code" class="pill">{{ place.country_code }}</span>
          <span v-for="category in placeCategories(place)" :key="category" class="pill">{{ category }}</span>
          <span v-if="place.recommend_level" class="pill">{{ place.recommend_level }}</span>
          <span v-if="place.review_url" class="pill">有评价链接</span>
          <span v-if="place.review_text" class="pill">有评论</span>
          <span class="pill">{{ place.is_public ? "公开" : "隐藏" }}</span>
        </div>
        <div class="item-actions">
          <button class="btn secondary compact" type="button" @click.stop="$emit('edit', place)">编辑</button>
          <button class="btn danger compact" type="button" @click.stop="$emit('delete', place)">删除</button>
        </div>
      </article>
    </section>
  </section>
</template>
