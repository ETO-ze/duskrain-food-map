<script setup>
import { onMounted, reactive, ref } from "vue";
import AdminBulkImport from "./AdminBulkImport.vue";
import AdminPlaceForm from "./AdminPlaceForm.vue";
import AdminPlaceList from "./AdminPlaceList.vue";
import AdminPoiSearch from "./AdminPoiSearch.vue";
import DeveloperMapPicker from "./DeveloperMapPicker.vue";
import {
  changeDeveloperPassword,
  deleteDeveloperPlace,
  developerLogin,
  developerLogout,
  getDeveloperPlaces,
  getDeveloperSession,
  saveDeveloperPlace,
} from "../utils/api";

const loading = ref(true);
const session = ref(null);
const places = ref([]);
const activeModule = ref("list");
const statusLine = ref("");
const credentials = reactive({ username: "", password: "" });
const passwordChange = reactive({ current: "", next: "", confirm: "" });
const form = reactive(newForm());

function newForm() {
  return {
    id: "",
    map_provider: "amap",
    country_code: "CN",
    coordinate_system: "gcj02",
    provider_poi_id: "",
    name: "",
    address: "",
    lng: "",
    lat: "",
    city: "",
    district: "",
    provider_category: "",
    phone: "",
    business_hours: "",
    amap_detail_url: "",
    provider_detail_url: "",
    my_category: "",
    rating: null,
    rating_author: session.value?.author_name || "",
    recommend_level: "",
    review_url: "",
    review_text: "",
    tags: "",
    note: "",
    visited_at: "",
    cover_image: "",
    image_urls: "",
    hide_images: false,
    is_public: true,
  };
}

function setStatus(message) {
  statusLine.value = message;
}

function fillFromPlace(place, includeId = true) {
  Object.assign(form, {
    ...newForm(),
    ...place,
    id: includeId ? place.id || "" : "",
    rating_author: session.value.author_name,
    rating: place.rating ?? null,
    hide_images: Boolean(place.hide_images),
    is_public: place.is_public ?? true,
  });
}

function readPayload() {
  return {
    provider_poi_id: String(form.provider_poi_id || "").trim(),
    map_provider: form.map_provider === "google" ? "google" : "amap",
    country_code: String(form.country_code || "").trim().toUpperCase(),
    coordinate_system: form.map_provider === "google" ? "wgs84" : "gcj02",
    name: String(form.name || "").trim(),
    address: String(form.address || "").trim(),
    lng: Number(form.lng),
    lat: Number(form.lat),
    city: String(form.city || "").trim(),
    district: String(form.district || "").trim(),
    provider_category: String(form.provider_category || "").trim(),
    phone: String(form.phone || "").trim(),
    business_hours: String(form.business_hours || "").trim(),
    amap_detail_url: String(form.amap_detail_url || "").trim(),
    provider_detail_url: String(form.provider_detail_url || form.amap_detail_url || "").trim(),
    my_category: String(form.my_category || "").trim(),
    rating: form.rating === "" || form.rating == null ? null : Number(form.rating),
    rating_author: session.value.author_name,
    recommend_level: form.recommend_level || "",
    review_url: String(form.review_url || "").trim(),
    review_text: String(form.review_text || "").trim(),
    tags: String(form.tags || "").trim(),
    note: String(form.note || "").trim(),
    visited_at: form.visited_at || "",
    cover_image: String(form.cover_image || "").trim(),
    image_urls: String(form.image_urls || "").trim(),
    hide_images: Boolean(form.hide_images),
    is_public: Boolean(form.is_public),
  };
}

async function loadPlaces() {
  places.value = await getDeveloperPlaces();
}

async function handleBulkCompleted(createdPlaces) {
  await loadPlaces();
  if (createdPlaces?.length) fillFromPlace(createdPlaces[createdPlaces.length - 1]);
}

async function login() {
  try {
    session.value = await developerLogin(credentials.username, credentials.password);
    credentials.password = "";
    if (!session.value.must_change_password) await loadPlaces();
    setStatus(session.value.must_change_password ? "首次登录必须修改初始密码。" : "登录成功。");
  } catch (error) {
    setStatus(`登录失败：${error.message}`);
  }
}

async function changePassword() {
  if (passwordChange.next !== passwordChange.confirm) {
    setStatus("两次输入的新密码不一致。");
    return;
  }
  try {
    session.value = await changeDeveloperPassword(passwordChange.current, passwordChange.next);
    Object.assign(passwordChange, { current: "", next: "", confirm: "" });
    await loadPlaces();
    setStatus("密码已修改，可以开始管理自己的店家。");
  } catch (error) {
    setStatus(`修改失败：${error.message}`);
  }
}

async function logout() {
  await developerLogout().catch(() => {});
  session.value = null;
  places.value = [];
  Object.assign(form, newForm());
  setStatus("已退出登录。");
}

function resetForm() {
  Object.assign(form, newForm());
  activeModule.value = "edit";
}

function selectPlace(place) {
  fillFromPlace(place);
  activeModule.value = "edit";
}

function selectCandidate(candidate) {
  fillFromPlace(candidate, false);
  activeModule.value = "edit";
}

async function savePlace() {
  try {
    const saved = await saveDeveloperPlace(readPayload(), form.id);
    fillFromPlace(saved);
    await loadPlaces();
    setStatus("已保存。");
  } catch (error) {
    if (error.status === 409 && error.detail?.existing) {
      await loadPlaces();
      fillFromPlace(error.detail.existing);
      setStatus("同一作者已保存过这家店，已切换到现有记录。");
      return;
    }
    setStatus(`保存失败：${error.message}`);
  }
}

async function removePlace(place = form) {
  if (!place?.id || !window.confirm("确认删除自己的这家店？")) return;
  try {
    await deleteDeveloperPlace(place.id);
    await loadPlaces();
    resetForm();
    activeModule.value = "list";
    setStatus("已删除。");
  } catch (error) {
    setStatus(`删除失败：${error.message}`);
  }
}

onMounted(async () => {
  document.body.classList.add("map-day");
  try {
    session.value = await getDeveloperSession();
    if (!session.value.must_change_password) await loadPlaces();
  } catch (_) {
    session.value = null;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <main class="developer-page">
    <section v-if="loading" class="developer-auth-card">
      <p class="eyebrow">DUSKRAIN DEVELOPER</p>
      <h1>正在读取账号</h1>
    </section>

    <section v-else-if="!session" class="developer-auth-card">
      <p class="eyebrow">DUSKRAIN DEVELOPER</p>
      <h1>作者管理登录</h1>
      <p class="subtle">仅限超级管理员创建并启用的作者账号。</p>
      <form class="developer-auth-form" @submit.prevent="login">
        <div class="field">
          <label for="developerUsername">账号</label>
          <input id="developerUsername" v-model="credentials.username" autocomplete="username" required>
        </div>
        <div class="field">
          <label for="developerPassword">密码</label>
          <input id="developerPassword" v-model="credentials.password" type="password" autocomplete="current-password" required>
        </div>
        <button class="btn" type="submit">登录</button>
      </form>
      <div class="status-line">{{ statusLine }}</div>
    </section>

    <section v-else-if="session.must_change_password" class="developer-auth-card">
      <p class="eyebrow">FIRST LOGIN</p>
      <h1>修改初始密码</h1>
      <p class="subtle">{{ session.author_name }}，新密码至少 8 位，不能继续使用 123123。</p>
      <form class="developer-auth-form" @submit.prevent="changePassword">
        <div class="field">
          <label for="currentPassword">当前密码</label>
          <input id="currentPassword" v-model="passwordChange.current" type="password" required>
        </div>
        <div class="field">
          <label for="newPassword">新密码</label>
          <input id="newPassword" v-model="passwordChange.next" type="password" minlength="8" required>
        </div>
        <div class="field">
          <label for="confirmPassword">确认新密码</label>
          <input id="confirmPassword" v-model="passwordChange.confirm" type="password" minlength="8" required>
        </div>
        <button class="btn" type="submit">修改密码</button>
        <button class="btn secondary" type="button" @click="logout">退出</button>
      </form>
      <div class="status-line">{{ statusLine }}</div>
    </section>

    <section v-else class="developer-workspace">
      <header class="developer-header">
        <div>
          <p class="eyebrow">AUTHOR WORKSPACE</p>
          <h1>{{ session.author_name }}</h1>
          <p class="subtle">{{ session.username }} · 仅管理自己的店家</p>
        </div>
        <button class="btn secondary compact" type="button" @click="logout">退出</button>
      </header>

      <nav class="developer-menu" aria-label="作者管理菜单">
        <button class="admin-menu-btn" :class="{ 'is-active': activeModule === 'list' }" type="button" @click="activeModule = 'list'">我的店家</button>
        <button class="admin-menu-btn" :class="{ 'is-active': activeModule === 'search' }" type="button" @click="activeModule = 'search'">搜索新建</button>
        <button class="admin-menu-btn" :class="{ 'is-active': activeModule === 'map' }" type="button" @click="activeModule = 'map'">地图选点</button>
        <button class="admin-menu-btn" :class="{ 'is-active': activeModule === 'bulk' }" type="button" @click="activeModule = 'bulk'">批量新建</button>
        <button class="admin-menu-btn" :class="{ 'is-active': activeModule === 'edit' }" type="button" @click="resetForm">编辑资料</button>
      </nav>

      <AdminPlaceList
        v-if="activeModule === 'list'"
        :places="places"
        @new="resetForm"
        @edit="selectPlace"
        @delete="removePlace"
      />
      <AdminPoiSearch
        v-if="activeModule === 'search'"
        :places="places"
        @select-place="selectPlace"
        @select-candidate="selectCandidate"
        @status="setStatus"
      />
      <DeveloperMapPicker
        v-if="activeModule === 'map'"
        :places="places"
        @select-place="selectPlace"
        @select-candidate="selectCandidate"
        @status="setStatus"
      />
      <AdminBulkImport
        v-if="activeModule === 'bulk'"
        :places="places"
        :fixed-author="session.author_name"
        :save-place-handler="saveDeveloperPlace"
        @completed="handleBulkCompleted"
        @status="setStatus"
      />
      <AdminPlaceForm
        v-if="activeModule === 'edit'"
        :form="form"
        :author-options="[session.author_name]"
        author-locked
        @save="savePlace"
        @new="resetForm"
        @delete="removePlace"
      />
      <div class="status-line">{{ statusLine }}</div>
    </section>
  </main>
</template>
