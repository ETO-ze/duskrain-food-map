<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import AdminBulkImport from "./AdminBulkImport.vue";
import AdminPlaceForm from "./AdminPlaceForm.vue";
import AdminPlaceList from "./AdminPlaceList.vue";
import AdminPoiSearch from "./AdminPoiSearch.vue";
import DeveloperMapPicker from "./DeveloperMapPicker.vue";
import {
  changeDeveloperPassword,
  completeDeveloperActivation,
  completeDeveloperPasswordReset,
  deleteDeveloperAvatar,
  deleteDeveloperPlace,
  developerLogin,
  developerLogout,
  getDeveloperAuthConfig,
  getDeveloperPlaces,
  getDeveloperPoiDetail,
  getDeveloperSession,
  inspectDeveloperActivation,
  requestDeveloperPasswordReset,
  searchDeveloperPoi,
  saveDeveloperPlace,
  unbindDeveloperOAuth,
  updateDeveloperProfile,
  uploadDeveloperAvatar,
} from "../utils/api";
import { categoryPayload, placeCategories } from "../utils/categories";

const loading = ref(true);
const session = ref(null);
const authConfig = ref({ password_min_length: 8, home_url: "https://duskrain.cn/", oauth_providers: {} });
const places = ref([]);
const activeModule = ref("list");
const authMode = ref("login");
const statusLine = ref("");
const modal = reactive({ open: false, title: "", message: "", redirect: false });
const credentials = reactive({ login: "", password: "" });
const passwordChange = reactive({ current: "", next: "", confirm: "" });
const activation = reactive({ token: "", author_name: "", email: "", username: "", existing_username: false, password: "", confirm: "" });
const passwordReset = reactive({ token: "", email: "", password: "", confirm: "" });
const profile = reactive({ username: "" });
const form = reactive(newForm());
const currentYear = new Date().getFullYear();
let homeRedirectTimer = 0;

const categoryOptions = computed(() => [...new Set(places.value.flatMap(placeCategories))]
  .sort((a, b) => a.localeCompare(b, "zh-CN")));
const initials = computed(() => String(session.value?.author_name || "D").trim().slice(0, 1).toUpperCase());
const providerMap = computed(() => new Map((session.value?.bound_providers || []).map((item) => [item.provider, item])));

function newForm() {
  return {
    id: "", map_provider: "amap", country_code: "CN", coordinate_system: "gcj02",
    provider_poi_id: "", name: "", address: "", lng: "", lat: "", city: "", district: "",
    provider_category: "", phone: "", business_hours: "", amap_detail_url: "",
    provider_detail_url: "", my_category: "", my_categories: [], rating: null,
    rating_author: session.value?.author_name || "", recommend_level: "", review_url: "",
    review_text: "", tags: "", note: "", visited_at: "", cover_image: "", image_urls: "",
    hide_images: false, is_public: true,
  };
}

function setStatus(message) {
  statusLine.value = message;
}

function fillFromPlace(place, includeId = true) {
  const categories = placeCategories(place);
  Object.assign(form, {
    ...newForm(), ...place, id: includeId ? place.id || "" : "",
    my_category: categories[0] || "", my_categories: [...categories],
    rating_author: session.value.author_name, rating: place.rating ?? null,
    hide_images: Boolean(place.hide_images), is_public: place.is_public ?? true,
  });
}

function readPayload() {
  const categories = categoryPayload(form.my_categories, form.my_category);
  return {
    provider_poi_id: String(form.provider_poi_id || "").trim(),
    map_provider: form.map_provider === "google" ? "google" : "amap",
    country_code: String(form.country_code || "").trim().toUpperCase(),
    coordinate_system: form.map_provider === "google" ? "wgs84" : "gcj02",
    name: String(form.name || "").trim(), address: String(form.address || "").trim(),
    lng: Number(form.lng), lat: Number(form.lat), city: String(form.city || "").trim(),
    district: String(form.district || "").trim(), provider_category: String(form.provider_category || "").trim(),
    phone: String(form.phone || "").trim(), business_hours: String(form.business_hours || "").trim(),
    amap_detail_url: String(form.amap_detail_url || "").trim(),
    provider_detail_url: String(form.provider_detail_url || form.amap_detail_url || "").trim(),
    ...categories, rating: form.rating === "" || form.rating == null ? null : Number(form.rating),
    rating_author: session.value.author_name, recommend_level: form.recommend_level || "",
    review_url: String(form.review_url || "").trim(), review_text: String(form.review_text || "").trim(),
    tags: String(form.tags || "").trim(), note: String(form.note || "").trim(),
    visited_at: form.visited_at || "", cover_image: String(form.cover_image || "").trim(),
    image_urls: String(form.image_urls || "").trim(), hide_images: Boolean(form.hide_images),
    is_public: Boolean(form.is_public),
  };
}

async function loadPlaces() {
  places.value = await getDeveloperPlaces();
}

async function loadSession() {
  session.value = await getDeveloperSession();
  profile.username = session.value.username;
  if (!session.value.must_change_password) await loadPlaces();
}

async function login() {
  try {
    session.value = await developerLogin(credentials.login, credentials.password);
    credentials.password = "";
    profile.username = session.value.username;
    if (!session.value.must_change_password) await loadPlaces();
    setStatus(session.value.must_change_password ? "请先更新旧的初始密码。" : "登录成功。");
  } catch (error) {
    setStatus(`登录失败：${error.message}`);
  }
}

async function changePassword() {
  if (passwordChange.next !== passwordChange.confirm) return setStatus("两次输入的新密码不一致。");
  try {
    session.value = await changeDeveloperPassword(passwordChange.current, passwordChange.next);
    Object.assign(passwordChange, { current: "", next: "", confirm: "" });
    await loadPlaces();
    setStatus("密码已更新，其他设备上的会话已退出。");
  } catch (error) {
    setStatus(`修改失败：${error.message}`);
  }
}

async function inspectActivation() {
  try {
    const data = await inspectDeveloperActivation(activation.token);
    Object.assign(activation, data);
  } catch (error) {
    setStatus(error.message);
  }
}

async function activateAccount() {
  if (activation.password !== activation.confirm) return setStatus("两次输入的密码不一致。");
  try {
    session.value = await completeDeveloperActivation(activation.token, activation.username, activation.password);
    profile.username = session.value.username;
    window.history.replaceState({}, "", window.location.pathname);
    await loadPlaces();
    setStatus("账户已激活。");
  } catch (error) {
    setStatus(`激活失败：${error.message}`);
  }
}

async function requestReset() {
  try {
    await requestDeveloperPasswordReset(passwordReset.email);
    setStatus("如果该邮箱已绑定作者账号，重置邮件会在几分钟内送达。");
  } catch (error) {
    setStatus(`发送失败：${error.message}`);
  }
}

async function finishReset() {
  if (passwordReset.password !== passwordReset.confirm) return setStatus("两次输入的密码不一致。");
  try {
    await completeDeveloperPasswordReset(passwordReset.token, passwordReset.password);
    authMode.value = "login";
    window.history.replaceState({}, "", window.location.pathname);
    setStatus("密码已重置，请重新登录。");
  } catch (error) {
    setStatus(`重置失败：${error.message}`);
  }
}

function startOAuth(provider, mode = "login") {
  window.location.assign(`/food-map/api/developer/oauth/${provider}/start?mode=${mode}`);
}

async function unbindProvider(provider) {
  if (!window.confirm(`确认解除 ${provider === "google" ? "Google" : "GitHub"} 绑定？`)) return;
  try {
    session.value = await unbindDeveloperOAuth(provider);
    setStatus("登录方式已解除绑定。");
  } catch (error) {
    setStatus(`解绑失败：${error.message}`);
  }
}

async function saveProfile() {
  try {
    session.value = await updateDeveloperProfile(profile.username);
    profile.username = session.value.username;
    setStatus("账号名已更新。");
  } catch (error) {
    setStatus(`保存失败：${error.message}`);
  }
}

async function uploadAvatar(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    session.value = await uploadDeveloperAvatar(file);
    setStatus("头像已更新。");
  } catch (error) {
    setStatus(`上传失败：${error.message}`);
  } finally {
    event.target.value = "";
  }
}

async function removeAvatar() {
  try {
    session.value = await deleteDeveloperAvatar();
    setStatus("头像已移除。");
  } catch (error) {
    setStatus(`操作失败：${error.message}`);
  }
}

async function logout() {
  await developerLogout().catch(() => {});
  session.value = null;
  places.value = [];
  authMode.value = "login";
  Object.assign(form, newForm());
  setStatus("已退出登录。");
}

function resetForm() {
  setStatus("");
  Object.assign(form, newForm());
  activeModule.value = "edit";
}

function selectPlace(place) {
  setStatus("");
  fillFromPlace(place);
  activeModule.value = "edit";
}

function selectCandidate(candidate) {
  setStatus("");
  fillFromPlace(candidate, false);
  activeModule.value = "edit";
}

function openModule(module) {
  setStatus("");
  activeModule.value = module;
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
      setStatus("你已经保存过这家店，已切换到现有记录。");
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

async function handleBulkCompleted(createdPlaces) {
  await loadPlaces();
  if (createdPlaces?.length) fillFromPlace(createdPlaces[createdPlaces.length - 1]);
}

function showOAuthResult(result) {
  const messages = {
    cancelled: ["登录已取消", "你取消了第三方授权。"],
    expired: ["请求已过期", "请重新发起登录或绑定。"],
    failed: ["登录未完成", "第三方身份验证失败，请稍后重试。"],
    conflict: ["无法绑定", "这个第三方身份已经绑定其他作者账号。"],
    unbound: ["尚未绑定", "请先使用邮箱或账号和密码登录，再到账号与安全中绑定。"],
    not_registered: ["尚未注册", "尚未注册，请联系超级管理员。"],
  };
  if (!messages[result]) return;
  [modal.title, modal.message] = messages[result];
  modal.open = true;
  modal.redirect = result === "not_registered";
  if (modal.redirect) {
    homeRedirectTimer = window.setTimeout(() => window.location.assign(authConfig.value.home_url), 3000);
  }
}

function closeModal() {
  if (modal.redirect) return;
  modal.open = false;
  if (homeRedirectTimer) window.clearTimeout(homeRedirectTimer);
}

onMounted(async () => {
  document.body.classList.add("map-day");
  const query = new URLSearchParams(window.location.search);
  activation.token = query.get("activate") || "";
  passwordReset.token = query.get("reset") || "";
  const oauthResult = query.get("oauth_result") || "";
  try {
    authConfig.value = await getDeveloperAuthConfig();
    if (activation.token) {
      authMode.value = "activation";
      await inspectActivation();
    } else if (passwordReset.token) {
      authMode.value = "reset";
    }
    if (!activation.token && !passwordReset.token) {
      try {
        await loadSession();
      } catch (_) {
        session.value = null;
      }
    }
    if (oauthResult) {
      window.history.replaceState({}, "", window.location.pathname);
      showOAuthResult(oauthResult);
    }
  } catch (error) {
    setStatus(error.message);
  } finally {
    loading.value = false;
  }
});

onUnmounted(() => {
  document.body.classList.remove("map-day");
  if (homeRedirectTimer) window.clearTimeout(homeRedirectTimer);
});
</script>

<template>
  <main class="developer-page">
    <section v-if="loading" class="developer-auth-card auth-loading">
      <p class="eyebrow">DUSKRAIN</p>
      <h1>正在读取账户</h1>
    </section>

    <section v-else-if="!session" class="developer-auth-shell">
      <a class="developer-brand" href="https://duskrain.cn/" aria-label="返回 DuskRain 主页">
        <span class="brand-mark">D</span><span>DuskRain</span>
      </a>

      <div v-if="authMode === 'activation'" class="developer-auth-card">
        <p class="eyebrow">ACCOUNT ACTIVATION</p>
        <h1>激活作者账户</h1>
        <p class="subtle">{{ activation.author_name }}<span v-if="activation.email"> · {{ activation.email }}</span></p>
        <form class="developer-auth-form" @submit.prevent="activateAccount">
          <div class="field"><label for="activationUsername">账号名</label><input id="activationUsername" v-model="activation.username" minlength="3" maxlength="32" autocomplete="username" required><small v-if="activation.existing_username">已为你保留原账号名；激活后仍可在“账号与安全”中修改。</small><small v-else>请自定义 3–32 个字符的账号名，之后仍可修改。</small></div>
          <div class="field"><label for="activationPassword">密码</label><input id="activationPassword" v-model="activation.password" type="password" minlength="8" autocomplete="new-password" required></div>
          <div class="field"><label for="activationConfirm">确认密码</label><input id="activationConfirm" v-model="activation.confirm" type="password" minlength="8" autocomplete="new-password" required></div>
          <button class="btn auth-primary" type="submit">激活账户</button>
        </form>
      </div>

      <div v-else-if="authMode === 'reset'" class="developer-auth-card">
        <p class="eyebrow">PASSWORD RESET</p>
        <h1>设置新密码</h1>
        <p class="subtle">密码至少 8 位。</p>
        <form class="developer-auth-form" @submit.prevent="finishReset">
          <div class="field"><label for="resetPassword">新密码</label><input id="resetPassword" v-model="passwordReset.password" type="password" minlength="8" autocomplete="new-password" required></div>
          <div class="field"><label for="resetConfirm">确认密码</label><input id="resetConfirm" v-model="passwordReset.confirm" type="password" minlength="8" autocomplete="new-password" required></div>
          <button class="btn auth-primary" type="submit">更新密码</button>
        </form>
      </div>

      <div v-else-if="authMode === 'forgot'" class="developer-auth-card">
        <p class="eyebrow">ACCOUNT RECOVERY</p>
        <h1>找回密码</h1>
        <p class="subtle">输入已验证的作者邮箱。</p>
        <form class="developer-auth-form" @submit.prevent="requestReset">
          <div class="field"><label for="recoveryEmail">邮箱</label><input id="recoveryEmail" v-model="passwordReset.email" type="email" autocomplete="email" required></div>
          <button class="btn auth-primary" type="submit">发送重置邮件</button>
          <button class="text-button" type="button" @click="authMode = 'login'">返回登录</button>
        </form>
      </div>

      <div v-else class="developer-auth-card">
        <p class="eyebrow">AUTHOR WORKSPACE</p>
        <h1>登录作者工作台</h1>
        <p class="subtle">仅限超级管理员邀请并启用的作者。</p>
        <div v-if="authConfig.oauth_providers.google || authConfig.oauth_providers.github" class="oauth-actions">
          <button v-if="authConfig.oauth_providers.google" class="oauth-button" type="button" @click="startOAuth('google')"><span class="google-mark">G</span>使用 Google 登录</button>
          <button v-if="authConfig.oauth_providers.github" class="oauth-button" type="button" @click="startOAuth('github')"><span class="github-mark">GH</span>使用 GitHub 登录</button>
        </div>
        <div v-if="authConfig.oauth_providers.google || authConfig.oauth_providers.github" class="auth-divider"><span>或使用密码</span></div>
        <form class="developer-auth-form" @submit.prevent="login">
          <div class="field"><label for="developerLogin">邮箱或账号名</label><input id="developerLogin" v-model="credentials.login" autocomplete="username" required></div>
          <div class="field"><label for="developerPassword">密码</label><input id="developerPassword" v-model="credentials.password" type="password" autocomplete="current-password" required></div>
          <button class="btn auth-primary" type="submit">登录</button>
          <button class="text-button" type="button" @click="authMode = 'forgot'">忘记密码？</button>
        </form>
      </div>
      <div class="auth-status" role="status">{{ statusLine }}</div>
      <footer class="developer-auth-footer">
        <nav aria-label="DuskRain 相关链接">
          <a href="https://duskrain.cn/#about">关于 DuskRain</a>
          <a href="https://duskrain.cn/privacy/">隐私政策</a>
          <a href="https://duskrain.cn/terms/">服务条款</a>
          <a href="mailto:prdusk.com@gmail.com">联系我们</a>
        </nav>
        <span>© {{ currentYear }} DuskRain</span>
      </footer>
    </section>

    <section v-else-if="session.must_change_password" class="developer-auth-shell">
      <div class="developer-auth-card">
        <p class="eyebrow">SECURITY UPDATE</p>
        <h1>更新初始密码</h1>
        <p class="subtle">{{ session.author_name }}，新密码至少 8 位，不能继续使用旧的共享密码。</p>
        <form class="developer-auth-form" @submit.prevent="changePassword">
          <div class="field"><label for="currentPassword">当前密码</label><input id="currentPassword" v-model="passwordChange.current" type="password" required></div>
          <div class="field"><label for="newPassword">新密码</label><input id="newPassword" v-model="passwordChange.next" type="password" minlength="8" required></div>
          <div class="field"><label for="confirmPassword">确认新密码</label><input id="confirmPassword" v-model="passwordChange.confirm" type="password" minlength="8" required></div>
          <button class="btn auth-primary" type="submit">更新密码</button>
          <button class="text-button" type="button" @click="logout">退出</button>
        </form>
        <div class="auth-status">{{ statusLine }}</div>
      </div>
      <footer class="developer-auth-footer">
        <nav aria-label="DuskRain 相关链接">
          <a href="https://duskrain.cn/#about">关于 DuskRain</a>
          <a href="https://duskrain.cn/privacy/">隐私政策</a>
          <a href="https://duskrain.cn/terms/">服务条款</a>
          <a href="mailto:prdusk.com@gmail.com">联系我们</a>
        </nav>
        <span>© {{ currentYear }} DuskRain</span>
      </footer>
    </section>

    <section v-else class="developer-workspace">
      <aside class="developer-sidebar">
        <a class="developer-brand workspace-brand" href="https://duskrain.cn/"><span class="brand-mark">D</span><span>DuskRain</span></a>
        <nav class="developer-menu" aria-label="作者管理菜单">
          <button :class="{ 'is-active': activeModule === 'list' }" type="button" @click="openModule('list')">我的店家</button>
          <button :class="{ 'is-active': activeModule === 'search' }" type="button" @click="openModule('search')">搜索新建</button>
          <button :class="{ 'is-active': activeModule === 'map' }" type="button" @click="openModule('map')">地图选点</button>
          <button :class="{ 'is-active': activeModule === 'bulk' }" type="button" @click="openModule('bulk')">批量新建</button>
          <button :class="{ 'is-active': activeModule === 'edit' }" type="button" @click="resetForm">编辑资料</button>
          <button :class="{ 'is-active': activeModule === 'account' }" type="button" @click="openModule('account')">账号与安全</button>
        </nav>
        <button class="sidebar-account" type="button" @click="openModule('account')">
          <img v-if="session.avatar_url" :src="session.avatar_url" alt=""><span v-else class="avatar-fallback">{{ initials }}</span>
          <span><strong>{{ session.author_name }}</strong><small>@{{ session.username }}</small></span>
        </button>
      </aside>

      <div class="developer-main">
        <header class="developer-header">
          <div><p class="eyebrow">AUTHOR WORKSPACE</p><h1>{{ activeModule === "account" ? "账号与安全" : session.author_name }}</h1></div>
          <div class="developer-header-actions">
            <a class="btn secondary compact" href="/food-map/" target="_blank" rel="noopener">进入美食地图</a>
            <button class="btn secondary compact" type="button" @click="logout">退出</button>
          </div>
        </header>

        <div class="developer-content">
          <AdminPlaceList v-if="activeModule === 'list'" :places="places" enable-category-filter enable-sort @new="openModule('search')" @edit="selectPlace" @delete="removePlace" />
          <AdminPoiSearch v-if="activeModule === 'search'" :places="places" :search-handler="searchDeveloperPoi" :detail-handler="getDeveloperPoiDetail" @select-place="selectPlace" @select-candidate="selectCandidate" @status="setStatus" />
          <DeveloperMapPicker v-if="activeModule === 'map'" :places="places" @select-place="selectPlace" @select-candidate="selectCandidate" @status="setStatus" />
          <AdminBulkImport v-if="activeModule === 'bulk'" :places="places" :fixed-author="session.author_name" :save-place-handler="saveDeveloperPlace" :search-handler="searchDeveloperPoi" :detail-handler="getDeveloperPoiDetail" @completed="handleBulkCompleted" @status="setStatus" />
          <AdminPlaceForm v-if="activeModule === 'edit'" :form="form" :author-options="[session.author_name]" :category-options="categoryOptions" author-locked @save="savePlace" @new="resetForm" @delete="removePlace" />

          <section v-if="activeModule === 'account'" class="account-settings">
            <article class="settings-card profile-card">
              <div class="settings-title"><div><h2>个人资料</h2><p>头像和账号名会显示在你的工作台中。</p></div></div>
              <div class="avatar-editor">
                <img v-if="session.avatar_url" :src="session.avatar_url" alt="当前头像"><span v-else class="avatar-preview">{{ initials }}</span>
                <div><label class="btn secondary compact avatar-upload">上传头像<input type="file" accept="image/jpeg,image/png,image/webp" @change="uploadAvatar"></label><button v-if="session.avatar_url" class="text-button" type="button" @click="removeAvatar">移除</button><small>JPEG、PNG 或 WebP，不超过 2 MB。</small></div>
              </div>
              <form class="settings-form" @submit.prevent="saveProfile">
                <div class="field"><label for="profileAuthor">作者名</label><input id="profileAuthor" :value="session.author_name" disabled></div>
                <div class="field"><label for="profileEmail">邮箱</label><input id="profileEmail" :value="session.email || '尚未添加'" disabled></div>
                <div class="field"><label for="profileUsername">账号名</label><input id="profileUsername" v-model="profile.username" minlength="3" maxlength="32" required></div>
                <button class="btn compact" type="submit">保存账号名</button>
              </form>
            </article>

            <article class="settings-card">
              <div class="settings-title"><div><h2>登录方式</h2><p>第三方身份必须在这里主动绑定，不会按邮箱自动关联。</p></div></div>
              <div v-for="provider in ['google', 'github']" :key="provider" class="provider-row">
                <span class="provider-icon" :class="provider">{{ provider === 'google' ? 'G' : 'GH' }}</span>
                <span><strong>{{ provider === "google" ? "Google" : "GitHub" }}</strong><small v-if="providerMap.get(provider)">{{ providerMap.get(provider).provider_login || providerMap.get(provider).provider_email || "已绑定" }}</small><small v-else>尚未绑定</small></span>
                <button v-if="providerMap.get(provider)" class="btn secondary compact" type="button" @click="unbindProvider(provider)">解绑</button>
                <button v-else class="btn secondary compact" type="button" :disabled="!authConfig.oauth_providers[provider]" @click="startOAuth(provider, 'bind')">绑定</button>
              </div>
            </article>

            <article class="settings-card">
              <div class="settings-title"><div><h2>修改密码</h2><p>更新后会退出其他设备上的工作台会话。</p></div></div>
              <form class="settings-form password-settings" @submit.prevent="changePassword">
                <div class="field"><label for="settingsCurrentPassword">当前密码</label><input id="settingsCurrentPassword" v-model="passwordChange.current" type="password" autocomplete="current-password" required></div>
                <div class="field"><label for="settingsNewPassword">新密码</label><input id="settingsNewPassword" v-model="passwordChange.next" type="password" minlength="8" autocomplete="new-password" required></div>
                <div class="field"><label for="settingsConfirmPassword">确认新密码</label><input id="settingsConfirmPassword" v-model="passwordChange.confirm" type="password" minlength="8" autocomplete="new-password" required></div>
                <button class="btn compact" type="submit">更新密码</button>
              </form>
            </article>
          </section>
        </div>
        <div class="status-line workspace-status">{{ statusLine }}</div>
      </div>
    </section>

    <div v-if="modal.open" class="auth-modal-backdrop" role="presentation" @click.self="closeModal">
      <section class="auth-modal" role="dialog" aria-modal="true" :aria-label="modal.title">
        <h2>{{ modal.title }}</h2><p>{{ modal.message }}</p>
        <div class="modal-actions">
          <a v-if="modal.redirect" class="btn" :href="authConfig.home_url">返回 DuskRain 个人主页</a>
          <button v-else class="btn" type="button" @click="closeModal">知道了</button>
        </div>
        <small v-if="modal.redirect">3 秒后自动返回</small>
      </section>
    </div>
  </main>
</template>
