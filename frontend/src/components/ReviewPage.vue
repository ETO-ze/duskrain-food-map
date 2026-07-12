<script setup>
import { computed, onMounted, ref } from "vue";
import { getPublicPlace } from "../utils/api";
import { categoryText } from "../utils/categories";
import { formatAddress, imageList } from "../utils/map";
import { renderReviewHtml } from "../utils/review";

const props = defineProps({
  placeId: { type: String, required: true },
});

const place = ref(null);
const error = ref("");
const loading = ref(true);

const ratingAuthor = computed(() => place.value?.rating_author || "吕俊泽");
const categoryLabel = computed(() => categoryText(place.value) || place.value?.provider_category || "");
const externalReviewUrl = computed(() => {
  const url = String(place.value?.review_url || "").trim();
  return /^https?:\/\//i.test(url) ? url : "";
});
const reviewMarkdown = computed(() => {
  const text = String(place.value?.review_text || "").trim();
  return text || "这家店还没有写详细评价。可以在管理页的“评论编写”里补充。";
});
const reviewHtml = computed(() => renderReviewHtml(reviewMarkdown.value));

onMounted(async () => {
  document.body.classList.add("map-day");
  try {
    place.value = await getPublicPlace(props.placeId);
  } catch (err) {
    error.value = err.message || "评价不存在";
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <main class="review-shell">
    <nav class="review-nav">
      <a class="btn secondary" href="/food-map/">返回地图</a>
      <a v-if="place" class="btn secondary" :href="`/food-map/?place=${place.id}`">查看位置</a>
    </nav>

    <section v-if="loading" class="review-empty">加载中...</section>
    <section v-else-if="error" class="review-empty">{{ error }}</section>

    <article v-else class="review-page">
      <header class="review-header">
        <p class="eyebrow">DUSKRAIN TASTE REVIEW</p>
        <h1>{{ place.name }}</h1>
        <p class="subtle">{{ formatAddress(place) }}</p>
      </header>

      <div v-if="imageList(place).length && !place.hide_images" class="review-images">
        <img v-for="url in imageList(place).slice(0, 6)" :key="url" :src="url" :alt="place.name" loading="lazy" decoding="async">
      </div>

      <section class="review-meta">
        <div>
          <span class="meta-label">评分</span>
          <strong>{{ place.rating ?? "-" }} / 10</strong>
        </div>
        <div>
          <span class="meta-label">作者</span>
          <strong>{{ ratingAuthor }}</strong>
        </div>
        <div v-if="place.recommend_level">
          <span class="meta-label">推荐</span>
          <strong>{{ place.recommend_level }}</strong>
        </div>
        <div v-if="categoryLabel">
          <span class="meta-label">分类</span>
          <strong>{{ categoryLabel }}</strong>
        </div>
      </section>

      <section class="review-content">
        <h2>美食评价</h2>
        <div class="review-article" v-html="reviewHtml"></div>
      </section>

      <section class="review-details">
        <p v-if="place.phone">电话：{{ place.phone }}</p>
        <p v-if="place.business_hours">营业：{{ place.business_hours }}</p>
        <p v-if="place.note">备注：{{ place.note }}</p>
        <div class="info-actions">
          <a v-if="externalReviewUrl" class="info-link primary" :href="externalReviewUrl" target="_blank" rel="noopener noreferrer">打开外部评价</a>
          <a
            v-if="place.provider_detail_url || place.amap_detail_url"
            class="info-link"
            :href="place.provider_detail_url || place.amap_detail_url"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ place.map_provider === "google" ? "打开 Google Maps" : "打开高德详情" }}
          </a>
        </div>
      </section>
    </article>
  </main>
</template>
