<script setup>
import { computed, ref, watch } from "vue";
import { getPoiDetail, saveAdminPlace, searchPoi } from "../utils/api";
import { bestPoiCandidate, normalizePlaceName, parseBulkPlaceText } from "../utils/bulk-import";

const props = defineProps({
  places: { type: Array, required: true },
});

const emit = defineEmits(["completed", "status"]);
const rawText = ref("");
const rows = ref([]);
const isRunning = ref(false);
const progress = ref({ current: 0, total: 0, created: 0, duplicate: 0, failed: 0 });
const selectedRows = computed(() => rows.value.filter((row) => row.enabled && row.status !== "invalid"));
const readyCount = computed(() => selectedRows.value.length);

watch(rawText, (value) => {
  if (!isRunning.value) rows.value = parseBulkPlaceText(value);
}, { immediate: true });

function findExisting(candidate, additionalPlaces = []) {
  return [...props.places, ...additionalPlaces].find((place) => {
    if (candidate.provider_poi_id && place.provider_poi_id === candidate.provider_poi_id && (place.map_provider || "amap") === "amap") {
      return true;
    }
    return normalizePlaceName(place.name) === normalizePlaceName(candidate.name)
      && (!candidate.city || `${place.city || ""}${place.district || ""}${place.address || ""}`.includes(candidate.city));
  });
}

function placePayload(detail, row) {
  return {
    map_provider: "amap",
    country_code: "CN",
    coordinate_system: "gcj02",
    provider_poi_id: detail.provider_poi_id || "",
    name: detail.name || row.name,
    address: detail.address || row.address || "",
    lng: Number(detail.lng),
    lat: Number(detail.lat),
    city: detail.city || row.city || "",
    district: detail.district || "",
    provider_category: detail.provider_category || "",
    phone: detail.phone || "",
    business_hours: detail.business_hours || "",
    amap_detail_url: detail.amap_detail_url || "",
    provider_detail_url: detail.provider_detail_url || detail.amap_detail_url || "",
    my_category: "",
    rating: row.rating,
    rating_author: row.rating_author || "吕俊泽",
    recommend_level: row.recommend_level,
    review_url: "",
    review_text: "",
    tags: "",
    note: row.note || "",
    visited_at: "",
    cover_image: detail.cover_image || "",
    image_urls: detail.image_urls || "",
    hide_images: false,
    is_public: true,
  };
}

function resetResults() {
  rows.value.forEach((row) => {
    if (row.status !== "invalid") {
      row.status = "ready";
      row.message = "";
      row.matchedName = "";
    }
  });
  progress.value = { current: 0, total: 0, created: 0, duplicate: 0, failed: 0 };
}

async function importAll() {
  if (!readyCount.value || isRunning.value) return;
  isRunning.value = true;
  resetResults();
  const queue = selectedRows.value;
  const createdPlaces = [];
  progress.value.total = queue.length;
  emit("status", `开始批量匹配并新建 ${queue.length} 家店...`);

  for (const [index, row] of queue.entries()) {
    progress.value.current = index + 1;
    row.status = "searching";
    row.message = "正在搜索高德 POI";
    emit("status", `正在处理 ${index + 1}/${queue.length}：${row.name}`);
    try {
      const query = [row.name, row.address].filter(Boolean).join(" ").slice(0, 80);
      const searchData = await searchPoi(query, row.city.slice(0, 40));
      const match = bestPoiCandidate(row, searchData.items || []);
      if (!match) throw new Error("高德没有返回可用商家");

      let detail = match.candidate;
      row.matchedName = detail.name || "";
      if (detail.provider_poi_id) {
        try {
          const detailData = await getPoiDetail(detail.provider_poi_id);
          detail = { ...detail, ...(detailData.item || {}) };
        } catch (_) {}
      }

      const existing = findExisting(detail, createdPlaces);
      if (existing) {
        row.status = "duplicate";
        row.message = `已存在：${existing.name}`;
        progress.value.duplicate += 1;
        continue;
      }

      const saved = await saveAdminPlace(placePayload(detail, row));
      createdPlaces.push(saved);
      row.status = "created";
      row.message = `已新建：${saved.name}`;
      progress.value.created += 1;
    } catch (error) {
      if (error.status === 409 && error.detail?.existing) {
        row.status = "duplicate";
        row.message = `已存在：${error.detail.existing.name}`;
        progress.value.duplicate += 1;
      } else {
        row.status = "failed";
        row.message = error.message;
        progress.value.failed += 1;
      }
    }
    await new Promise((resolve) => window.setTimeout(resolve, 180));
  }

  isRunning.value = false;
  emit("completed", createdPlaces);
  emit("status", `批量新建完成：成功 ${progress.value.created}，重复 ${progress.value.duplicate}，失败 ${progress.value.failed}。`);
}

function clearInput() {
  if (isRunning.value) return;
  rawText.value = "";
  rows.value = [];
  resetResults();
}
</script>

<template>
  <section class="admin-module bulk-import">
    <div class="section-title">
      <span>批量新建店家</span>
      <span class="pill">{{ readyCount }} 家待处理</span>
    </div>
    <div class="bulk-rule">
      <strong>输入格式</strong>
      <span>编号 店名 城市或详细地址 评分 推荐等级 作者</span>
      <small>推荐等级支持“必去 / 推荐 / 一般 / 避雷”。推荐等级和作者未填写时，按评分规则并默认使用吕俊泽。</small>
    </div>
    <textarea
      v-model="rawText"
      class="bulk-input"
      :disabled="isRunning"
      placeholder="1 喜家德（凯德广场店） 哈尔滨 8.2 推荐 吕俊泽&#10;2 二发烧烤 黑龙江省哈尔滨市香坊区亚麻街副39-1号 9.1 必去 吕俊泽&#10;3 富都美食 哈尔滨 量大便宜 8.6"
    ></textarea>
    <div class="button-row">
      <button class="btn" type="button" :disabled="!readyCount || isRunning" @click="importAll">
        {{ isRunning ? `处理中 ${progress.current}/${progress.total}` : `一键新建 ${readyCount} 家` }}
      </button>
      <button class="btn secondary" type="button" :disabled="isRunning" @click="clearInput">清空</button>
    </div>
    <div v-if="progress.total" class="bulk-summary">
      <span>进度 {{ progress.current }}/{{ progress.total }}</span>
      <span class="is-created">成功 {{ progress.created }}</span>
      <span class="is-duplicate">重复 {{ progress.duplicate }}</span>
      <span class="is-failed">失败 {{ progress.failed }}</span>
    </div>
    <section class="bulk-preview">
      <article v-if="!rows.length" class="search-empty">
        <strong>粘贴店家清单后自动预览</strong>
        <span>系统会逐条搜索高德、补全地址和坐标，然后保存评分与推荐等级。</span>
      </article>
      <article v-for="row in rows" :key="`${row.lineNumber}-${row.original}`" class="bulk-row" :class="`is-${row.status}`">
        <label class="bulk-row-check">
          <input v-model="row.enabled" type="checkbox" :disabled="isRunning || row.status === 'invalid'">
          <span>{{ row.lineNumber }}</span>
        </label>
        <div class="bulk-row-main">
          <strong>{{ row.name || row.original }}</strong>
          <span v-if="row.status === 'invalid'" class="subtle">{{ row.error }}</span>
          <template v-else>
            <span class="subtle">{{ [row.city, row.address, row.note].filter(Boolean).join(" · ") || "未指定城市，将全国搜索" }}</span>
            <span class="pill-row">
              <span class="rating">{{ row.rating }} / 10</span>
              <span class="pill">{{ row.recommend_level }}</span>
              <span class="pill">作者：{{ row.rating_author }}</span>
              <span v-if="row.recommendation_defaulted" class="pill">默认</span>
              <span v-if="row.matchedName" class="pill">匹配：{{ row.matchedName }}</span>
            </span>
            <span v-if="row.message" class="bulk-row-message">{{ row.message }}</span>
          </template>
        </div>
      </article>
    </section>
  </section>
</template>
