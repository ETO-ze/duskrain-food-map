<script setup>
import { computed, defineAsyncComponent } from "vue";
import PublicMap from "./components/PublicMap.vue";
const GlobalMap = defineAsyncComponent(() => import("./components/GlobalMap.vue"));
const AdminDashboard = defineAsyncComponent(() => import("./components/AdminDashboard.vue"));
const DeveloperDashboard = defineAsyncComponent(() => import("./components/DeveloperDashboard.vue"));
const ReviewPage = defineAsyncComponent(() => import("./components/ReviewPage.vue"));
const LuGuide2026 = defineAsyncComponent(() => import("./components/LuGuide2026.vue"));

const isAdmin = computed(() => window.location.pathname.includes("/admin"));
const isDeveloper = computed(() => window.location.pathname.includes("/developer"));
const isGlobal = computed(() => window.location.pathname.includes("/global"));
const isLuGuide = computed(() => window.location.pathname.includes("/guide"));
const reviewMatch = computed(() => window.location.pathname.match(/\/review\/(\d+)/));
const reviewPlaceId = computed(() => reviewMatch.value?.[1] || "");
</script>

<template>
  <AdminDashboard v-if="isAdmin" />
  <DeveloperDashboard v-else-if="isDeveloper" />
  <ReviewPage v-else-if="reviewPlaceId" :place-id="reviewPlaceId" />
  <LuGuide2026 v-else-if="isLuGuide" />
  <GlobalMap v-else-if="isGlobal" />
  <PublicMap v-else />
</template>
