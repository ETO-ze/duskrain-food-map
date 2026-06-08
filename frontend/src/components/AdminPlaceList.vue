<script setup>
import { formatAddress } from "../utils/map";

defineProps({
  places: { type: Array, required: true },
});

defineEmits(["edit", "delete", "new"]);
</script>

<template>
  <section class="admin-module admin-saved">
    <div class="section-title">
      <span>已添加店家</span>
      <button class="btn secondary compact" type="button" @click="$emit('new')">新建店家</button>
    </div>
    <section class="list admin-list">
      <article v-if="!places.length" class="place-item">
        <p class="subtle">还没有保存店铺。先搜索一家店。</p>
      </article>
      <article v-for="place in places" :key="place.id" class="place-item" @click="$emit('edit', place)">
        <div class="item-title">
          <span>{{ place.name }}</span>
          <span class="rating">{{ place.rating ?? "-" }} / 10 · {{ place.rating_author || "吕俊泽" }}</span>
        </div>
        <div class="subtle">{{ formatAddress(place) }}</div>
        <div class="pill-row">
          <span class="pill">{{ place.map_provider === "google" ? "Google" : "高德" }}</span>
          <span v-if="place.country_code" class="pill">{{ place.country_code }}</span>
          <span v-if="place.my_category" class="pill">{{ place.my_category }}</span>
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
