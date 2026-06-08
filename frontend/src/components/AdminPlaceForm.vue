<script setup>
import { computed, nextTick, ref } from "vue";
import { countryOptions } from "../utils/countries";
import { renderReviewHtml } from "../utils/review";

const props = defineProps({
  form: { type: Object, required: true },
  authorOptions: { type: Array, default: () => [] },
  authorLocked: { type: Boolean, default: false },
});

defineEmits(["save", "new", "delete"]);

const reviewInput = ref(null);
const reviewPreviewOpen = ref(true);
const reviewPreviewHtml = computed(() => renderReviewHtml(props.form.review_text || ""));

function insertReviewText(before, after = "", placeholder = "内容") {
  const input = reviewInput.value;
  const text = String(props.form.review_text || "");
  const start = input?.selectionStart ?? text.length;
  const end = input?.selectionEnd ?? text.length;
  const selected = text.slice(start, end) || placeholder;
  const nextText = `${text.slice(0, start)}${before}${selected}${after}${text.slice(end)}`;
  props.form.review_text = nextText;
  nextTick(() => {
    const cursorStart = start + before.length;
    const cursorEnd = cursorStart + selected.length;
    reviewInput.value?.focus();
    reviewInput.value?.setSelectionRange(cursorStart, cursorEnd);
  });
}

function insertReviewLine(prefix, placeholder = "内容") {
  const input = reviewInput.value;
  const text = String(props.form.review_text || "");
  const start = input?.selectionStart ?? text.length;
  const lineStart = text.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
  props.form.review_text = `${text.slice(0, lineStart)}${prefix}${text.slice(lineStart) || placeholder}`;
  nextTick(() => {
    const position = lineStart + prefix.length + placeholder.length;
    reviewInput.value?.focus();
    reviewInput.value?.setSelectionRange(position, position);
  });
}

function insertReviewImage() {
  const url = window.prompt("图片 URL");
  if (!url) return;
  const alt = window.prompt("图片说明", "菜品图片") || "菜品图片";
  insertReviewText(`\n![${alt}](${url.trim()})\n`, "", "");
}
</script>

<template>
  <form class="form-grid admin-module" @submit.prevent="$emit('save')">
    <div class="form-section-label wide">基础信息</div>
    <div class="field">
      <label for="mapProvider">地图来源</label>
      <select id="mapProvider" v-model="form.map_provider">
        <option value="amap">国内高德</option>
        <option value="google">国外 Google</option>
      </select>
    </div>
    <div class="field">
      <label for="countryCode">国家 / Country</label>
      <select id="countryCode" v-model="form.country_code">
        <option value="">请选择国家 / Select country</option>
        <option v-for="country in countryOptions" :key="country.code" :value="country.code">
          {{ country.zh }} / {{ country.en }} ({{ country.code }})
        </option>
      </select>
    </div>
    <div class="field wide">
      <label for="name">店名</label>
      <input id="name" v-model="form.name" required>
    </div>
    <div class="field wide">
      <label for="address">地址</label>
      <input id="address" v-model="form.address">
    </div>
    <div class="field">
      <label for="lng">经度</label>
      <input id="lng" v-model.number="form.lng" required type="number" step="0.000001">
    </div>
    <div class="field">
      <label for="lat">纬度</label>
      <input id="lat" v-model.number="form.lat" required type="number" step="0.000001">
    </div>
    <div class="field">
      <label for="city">城市</label>
      <input id="city" v-model="form.city">
    </div>
    <div class="field">
      <label for="district">区域</label>
      <input id="district" v-model="form.district">
    </div>

    <div class="form-section-label wide">我的评价</div>
    <div class="field">
      <label for="myCategory">我的分类</label>
      <input id="myCategory" v-model="form.my_category" placeholder="火锅 / 咖啡 / 日料">
    </div>
    <div class="field">
      <label for="rating">评分</label>
      <input id="rating" v-model.number="form.rating" type="number" min="0" max="10" step="0.1" placeholder="8.8">
    </div>
    <div class="field">
      <label for="ratingAuthor">评分作者</label>
      <select v-if="authorOptions.length" id="ratingAuthor" v-model="form.rating_author" :disabled="authorLocked">
        <option v-for="author in authorOptions" :key="author" :value="author">{{ author }}</option>
      </select>
      <input v-else id="ratingAuthor" v-model="form.rating_author" :readonly="authorLocked" placeholder="吕俊泽 / DuskRain">
    </div>
    <div class="field">
      <label for="recommendLevel">推荐等级</label>
      <select id="recommendLevel" v-model="form.recommend_level">
        <option value="">未标记</option>
        <option value="必去">必去</option>
        <option value="推荐">推荐</option>
        <option value="一般">一般</option>
        <option value="避雷">避雷</option>
      </select>
    </div>
    <div class="field">
      <label for="visitedAt">探店日期</label>
      <input id="visitedAt" v-model="form.visited_at" type="date">
    </div>
    <div class="field wide">
      <label for="tags">标签</label>
      <input id="tags" v-model="form.tags" placeholder="适合约会，排队久，性价比高">
    </div>
    <div class="field wide">
      <label for="reviewUrl">美食评价链接</label>
      <input id="reviewUrl" v-model="form.review_url" type="url" placeholder="可选：外部评价链接 https://...">
    </div>
    <div class="field wide review-editor">
      <div class="review-editor-head">
        <label for="reviewText">评论编写</label>
        <button class="btn secondary compact" type="button" @click="reviewPreviewOpen = !reviewPreviewOpen">
          {{ reviewPreviewOpen ? "隐藏预览" : "显示预览" }}
        </button>
      </div>
      <div class="review-tools" aria-label="评论编辑工具">
        <button class="btn secondary compact" type="button" @click="insertReviewLine('## ', '小标题')">标题</button>
        <button class="btn secondary compact" type="button" @click="insertReviewText('**', '**', '重点内容')">加粗</button>
        <button class="btn secondary compact" type="button" @click="insertReviewLine('- ', '列表项')">列表</button>
        <button class="btn secondary compact" type="button" @click="insertReviewLine('> ', '引用内容')">引用</button>
        <button class="btn secondary compact" type="button" @click="insertReviewImage">插入图片</button>
      </div>
      <textarea
        id="reviewText"
        ref="reviewInput"
        v-model="form.review_text"
        class="review-textarea"
        placeholder="像写博客一样记录体验。支持 Markdown：## 标题、**加粗**、- 列表、![图片说明](图片URL)"
      ></textarea>
      <section v-if="reviewPreviewOpen" class="review-preview">
        <div v-if="form.review_text" class="review-article" v-html="reviewPreviewHtml"></div>
        <p v-else class="subtle">预览会显示在这里。</p>
      </section>
    </div>
    <div class="field wide">
      <label for="note">备注</label>
      <textarea id="note" v-model="form.note" placeholder="招牌菜、避坑点、适合什么场景"></textarea>
    </div>

    <div class="form-section-label wide">地图商家信息</div>
    <div class="field wide">
      <label for="providerCategory">平台分类</label>
      <input id="providerCategory" v-model="form.provider_category">
    </div>
    <div class="field">
      <label for="phone">电话</label>
      <input id="phone" v-model="form.phone">
    </div>
    <div class="field">
      <label for="businessHours">营业时间</label>
      <input id="businessHours" v-model="form.business_hours">
    </div>
    <div class="field wide">
      <label for="providerDetailUrl">平台详情链接</label>
      <input id="providerDetailUrl" v-model="form.provider_detail_url">
    </div>

    <div class="form-section-label wide">图片与展示</div>
    <details class="image-details wide">
      <summary>图片列表</summary>
      <div class="field">
        <label for="coverImage">封面图片 URL</label>
        <input id="coverImage" v-model="form.cover_image">
      </div>
      <div class="field">
        <label for="imageUrls">图片 URL 列表</label>
        <textarea id="imageUrls" v-model="form.image_urls" placeholder="一行一个图片 URL"></textarea>
      </div>
    </details>
    <div class="field">
      <label for="hideImages">图片显示</label>
      <select id="hideImages" v-model="form.hide_images">
        <option :value="false">显示图片</option>
        <option :value="true">隐藏图片</option>
      </select>
    </div>
    <div class="field">
      <label for="isPublic">展示状态</label>
      <select id="isPublic" v-model="form.is_public">
        <option :value="true">公开</option>
        <option :value="false">隐藏</option>
      </select>
    </div>
    <div class="button-row wide">
      <button class="btn" type="submit">保存</button>
      <button class="btn secondary" type="button" @click="$emit('new')">新建</button>
      <button class="btn danger" type="button" @click="$emit('delete')" :disabled="!form.id">删除</button>
      <a class="btn secondary" href="/food-map/">查看地图</a>
    </div>
  </form>
</template>
