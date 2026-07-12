<script setup>
import { nextTick, ref } from "vue";
import { getPoiDetail, searchPoi } from "../utils/api";
import { countryOptions, countrySearchLabel } from "../utils/countries";
import { searchGooglePlaces } from "../utils/google-map";

const props = defineProps({
  places: { type: Array, required: true },
  searchHandler: { type: Function, default: searchPoi },
  detailHandler: { type: Function, default: getPoiDetail },
});

const emit = defineEmits(["select-place", "select-candidate", "status", "provider-change"]);

const provider = ref("amap");
const q = ref("");
const city = ref("");
const countryCode = ref("");
const results = ref([]);
const resultsPanel = ref(null);
const hasSearched = ref(false);
const isSearching = ref(false);
const selectingKey = ref("");
let searchVersion = 0;

function candidateKey(item, index = 0) {
  return [
    item.map_provider || "amap",
    item.provider_poi_id || "",
    item.name || "",
    item.lng || "",
    item.lat || "",
    index,
  ].join(":");
}

function findExistingPlace(candidate) {
  return props.places.find((place) => {
    if (
      candidate.provider_poi_id
      && place.provider_poi_id === candidate.provider_poi_id
      && (place.map_provider || "amap") === (candidate.map_provider || "amap")
    ) return true;
    const sameName = (place.name || "").trim().toLowerCase() === (candidate.name || "").trim().toLowerCase();
    const sameAddress = (place.address || "").trim().toLowerCase() === (candidate.address || "").trim().toLowerCase();
    const sameLng = Math.abs(Number(place.lng) - Number(candidate.lng)) < 0.000001;
    const sameLat = Math.abs(Number(place.lat) - Number(candidate.lat)) < 0.000001;
    return sameName && sameAddress && sameLng && sameLat;
  });
}

async function runSearch() {
  const keyword = q.value.trim();
  if (!keyword) {
    emit("status", "请输入店名或地点");
    return;
  }
  if (isSearching.value) return;

  const currentVersion = ++searchVersion;
  isSearching.value = true;
  hasSearched.value = false;
  results.value = [];
  emit("status", provider.value === "google" ? "正在搜索 Google Places..." : "正在搜索高德餐饮 POI...");
  try {
    let nextResults = [];
    let successMessage = "";
    if (provider.value === "google") {
      const query = [
        keyword,
        city.value.trim(),
        countrySearchLabel(countryCode.value),
      ].filter(Boolean).join(" ");
      nextResults = await searchGooglePlaces(query);
      successMessage = `Google Places 找到 ${nextResults.length} 个候选店铺：${query}。`;
    } else {
      const data = await props.searchHandler(keyword, city.value.trim());
      nextResults = data.items || [];
      const meta = data.query || {};
      const cityLabel = meta.city ? ` / ${meta.city}` : "";
      successMessage = `找到 ${nextResults.length} 个候选店铺：${meta.keyword || keyword}${cityLabel}。`;
    }
    if (currentVersion !== searchVersion) return;
    results.value = nextResults;
    hasSearched.value = true;
    emit("status", successMessage);
    await nextTick();
    if (window.matchMedia("(max-width: 860px)").matches) {
      resultsPanel.value?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  } catch (error) {
    if (currentVersion !== searchVersion) return;
    results.value = [];
    hasSearched.value = true;
    emit("status", `搜索失败：${error.message}`);
  } finally {
    if (currentVersion === searchVersion) isSearching.value = false;
  }
}

async function selectResult(item) {
  if (selectingKey.value) return;
  selectingKey.value = candidateKey(item);
  try {
    const existing = findExistingPlace(item);
    if (existing) {
      emit("select-place", existing);
      emit("status", `已添加过：${existing.name}，已切换为编辑已有店铺。`);
      return;
    }

    let detail = item;
    if (item.provider_poi_id && (item.map_provider || "amap") === "amap") {
      emit("status", `正在补全：${item.name}`);
      try {
        const data = await props.detailHandler(item.provider_poi_id);
        detail = { ...item, ...(data.item || {}) };
      } catch (error) {
        emit("status", `详情补全失败，将使用搜索结果：${error.message}`);
      }
    }

    const existingAfterDetail = findExistingPlace(detail);
    if (existingAfterDetail) {
      emit("select-place", existingAfterDetail);
      emit("status", `已添加过：${existingAfterDetail.name}，已切换为编辑已有店铺。`);
      return;
    }

    emit("select-candidate", detail);
    emit("status", `已选中：${detail.name}，商家详情已自动填入。确认评分和分类后点保存。`);
  } finally {
    selectingKey.value = "";
  }
}

function changeProvider() {
  searchVersion += 1;
  isSearching.value = false;
  hasSearched.value = false;
  results.value = [];
  emit("provider-change", provider.value);
}
</script>

<template>
  <section class="admin-module">
    <div class="section-title">
      <span>搜索导入</span>
    </div>
    <form class="admin-toolbar admin-search-toolbar" @submit.prevent="runSearch">
      <div class="field">
        <label for="searchProvider">地图来源</label>
        <select id="searchProvider" v-model="provider" @change="changeProvider">
          <option value="amap">国内高德</option>
          <option value="google">国外 Google</option>
        </select>
      </div>
      <div class="field search-query-field">
        <label for="searchText">店名 / 地点</label>
        <input
          id="searchText"
          v-model="q"
          name="query"
          enterkeyhint="search"
          autocomplete="off"
          :placeholder="provider === 'google' ? '例如：Le Bernardin' : '例如：上海 福和慧'"
        >
      </div>
      <div v-if="provider === 'google'" class="field">
        <label for="searchCountry">国家 / Country</label>
        <select id="searchCountry" v-model="countryCode">
          <option value="">全部国家 / All countries</option>
          <option v-for="country in countryOptions" :key="country.code" :value="country.code">
            {{ country.zh }} / {{ country.en }} ({{ country.code }})
          </option>
        </select>
      </div>
      <div class="field">
        <label for="searchCity">城市 / City</label>
        <input
          id="searchCity"
          v-model="city"
          name="city"
          enterkeyhint="search"
          autocomplete="address-level2"
          :placeholder="provider === 'google' ? 'New York' : '上海'"
        >
      </div>
      <button class="btn" type="submit" :disabled="isSearching">
        {{ isSearching ? "搜索中..." : "搜索地址" }}
      </button>
    </form>
    <section ref="resultsPanel" class="search-results" aria-live="polite" :aria-busy="isSearching">
      <article v-if="isSearching" class="search-empty">
        <strong>正在搜索商家</strong>
        <span>请稍候，不需要重复点击。</span>
      </article>
      <article v-else-if="!hasSearched" class="search-empty">
        <strong>输入店名开始搜索</strong>
        <span>{{ provider === "google" ? "国外模式建议同时填写城市和国家。" : "国内模式建议同时填写城市，匹配会更准确。" }}</span>
      </article>
      <article v-else-if="!results.length" class="search-empty">
        <strong>没有匹配结果</strong>
        <span>请缩短店名、检查城市，或暂时留空城市后重试。</span>
      </article>
      <template v-for="(item, index) in results" :key="`${item.map_provider}-${item.provider_poi_id}-${index}`">
        <div v-if="index === 0" class="candidate-title">搜索候选店铺</div>
        <button
          class="search-item"
          :class="{ 'is-existing': findExistingPlace(item) }"
          type="button"
          :disabled="Boolean(selectingKey)"
          @click="selectResult(item)"
        >
          <span class="item-title">
            <span>{{ item.name }}</span>
            <span class="pill">{{ findExistingPlace(item) ? "已添加" : [item.city, item.district].filter(Boolean).join(" / ") }}</span>
          </span>
          <span class="subtle">{{ item.address || "无详细地址" }}</span>
          <span class="pill-row">
            <span class="pill">{{ item.map_provider === "google" ? "Google" : "高德" }}</span>
            <span v-if="item.country_code" class="pill">{{ item.country_code }}</span>
            <span class="pill">{{ item.provider_category || "POI" }}</span>
            <span v-if="item.phone" class="pill">{{ item.phone }}</span>
            <span class="candidate-action">
              {{ selectingKey === candidateKey(item) ? "正在读取..." : findExistingPlace(item) ? "编辑已有店家" : "点击加入" }}
            </span>
          </span>
        </button>
      </template>
    </section>
  </section>
</template>
