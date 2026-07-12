<script setup>
import { computed, ref, watch } from "vue";
import { placeCategories } from "../utils/categories";
import { formatAddress } from "../utils/map";

const props = defineProps({
  places: { type: Array, required: true },
  enableCategoryFilter: { type: Boolean, default: false },
});

defineEmits(["edit", "delete", "new"]);

const categoryFilter = ref("");
const uncategorizedValue = "__uncategorized__";
const categoryOptions = computed(() => [...new Set(
  props.places.flatMap(placeCategories),
)].sort((a, b) => a.localeCompare(b, "zh-CN")));
const hasUncategorized = computed(() => props.places.some((place) => !placeCategories(place).length));
const visiblePlaces = computed(() => {
  if (!props.enableCategoryFilter || !categoryFilter.value) return props.places;
  if (categoryFilter.value === uncategorizedValue) {
    return props.places.filter((place) => !placeCategories(place).length);
  }
  return props.places.filter((place) => placeCategories(place).includes(categoryFilter.value));
});

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
      <span class="pill">当前 {{ visiblePlaces.length }} 家</span>
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
