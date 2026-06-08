<script setup>
import { computed } from "vue";
import PublicMap from "./components/PublicMap.vue";
import GlobalMap from "./components/GlobalMap.vue";
import AdminDashboard from "./components/AdminDashboard.vue";
import ReviewPage from "./components/ReviewPage.vue";

const isAdmin = computed(() => window.location.pathname.includes("/admin"));
const isGlobal = computed(() => window.location.pathname.includes("/global"));
const reviewMatch = computed(() => window.location.pathname.match(/\/review\/(\d+)/));
const reviewPlaceId = computed(() => reviewMatch.value?.[1] || "");
</script>

<template>
  <AdminDashboard v-if="isAdmin" />
  <ReviewPage v-else-if="reviewPlaceId" :place-id="reviewPlaceId" />
  <GlobalMap v-else-if="isGlobal" />
  <PublicMap v-else />
</template>
