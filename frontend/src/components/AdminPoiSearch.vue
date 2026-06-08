<script setup>
import { ref } from "vue";
import { getPoiDetail, searchPoi } from "../utils/api";
import { countryOptions, countrySearchLabel } from "../utils/countries";
import { searchGooglePlaces } from "../utils/google-map";

const props = defineProps({
  places: { type: Array, required: true },
});

const emit = defineEmits(["select-place", "select-candidate", "status", "provider-change"]);

const provider = ref("amap");
const q = ref("");
const city = ref("");
const countryCode = ref("");
const results = ref([]);

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
  if (!q.value.trim()) {
    emit("status", "请输入店名或地点");
    return;
  }
  emit("status", provider.value === "google" ? "正在搜索 Google Places..." : "正在搜索高德餐饮 POI...");
  try {
    if (provider.value === "google") {
      const query = [
        q.value.trim(),
        city.value.trim(),
        countrySearchLabel(countryCode.value),
      ].filter(Boolean).join(" ");
      results.value = await searchGooglePlaces(query);
      emit("status", `Google Places 找到 ${results.value.length} 个候选店铺：${query}。`);
    } else {
      const data = await searchPoi(q.value.trim(), city.value.trim());
      results.value = data.items || [];
      const meta = data.query || {};
      const cityLabel = meta.city ? ` / ${meta.city}` : "";
      emit("status", `找到 ${results.value.length} 个候选店铺：${meta.keyword || q.value}${cityLabel}。`);
    }
  } catch (error) {
    emit("status", `搜索失败：${error.message}`);
  }
}

async function selectResult(item) {
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
      const data = await getPoiDetail(item.provider_poi_id);
      detail = { ...item, ...(data.item || {}) };
    } catch (_) {}
  }

  const existingAfterDetail = findExistingPlace(detail);
  if (existingAfterDetail) {
    emit("select-place", existingAfterDetail);
    emit("status", `已添加过：${existingAfterDetail.name}，已切换为编辑已有店铺。`);
    return;
  }

  emit("select-candidate", detail);
  emit("status", `已选中：${detail.name}，商家详情已自动填入。确认评分和分类后点保存。`);
}

function changeProvider() {
  results.value = [];
  emit("provider-change", provider.value);
}
</script>

<template>
  <section class="admin-module">
    <div class="section-title">
      <span>搜索导入</span>
    </div>
    <section class="admin-toolbar">
      <div class="field">
        <label for="searchProvider">地图来源</label>
        <select id="searchProvider" v-model="provider" @change="changeProvider">
          <option value="amap">国内高德</option>
          <option value="google">国外 Google</option>
        </select>
      </div>
      <div class="field">
        <label for="searchText">店名 / 地点</label>
        <input id="searchText" v-model="q" :placeholder="provider === 'google' ? '例如：Le Bernardin' : '例如：上海 福和慧'" @keydown.enter.prevent="runSearch">
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
        <input id="searchCity" v-model="city" :placeholder="provider === 'google' ? 'New York' : '上海'" @keydown.enter.prevent="runSearch">
      </div>
      <button class="btn" type="button" @click="runSearch">搜索地址</button>
    </section>
    <section class="search-results">
      <article v-if="!results.length" class="search-empty">
        <strong>没有候选结果</strong>
        <span>{{ provider === "google" ? "输入国外城市和店名，例如“Tokyo Narisawa”。" : "输入“城市 店名”，例如“北京 新荣记”。" }}</span>
      </article>
      <template v-for="(item, index) in results" :key="`${item.map_provider}-${item.provider_poi_id}-${index}`">
        <div v-if="index === 0" class="candidate-title">搜索候选店铺</div>
        <button
          class="search-item"
          :class="{ 'is-existing': findExistingPlace(item) }"
          type="button"
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
            <span class="candidate-action">{{ findExistingPlace(item) ? "编辑已有店家" : "点击加入" }}</span>
          </span>
        </button>
      </template>
    </section>
  </section>
</template>
