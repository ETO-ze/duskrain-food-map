<script setup>
defineProps({
  mapTheme: { type: String, required: true },
});

defineEmits(["toggle-theme"]);
</script>

<template>
  <section class="admin-module admin-settings">
    <div class="section-title">
      <span>地图设置</span>
    </div>
    <div class="setting-row">
      <div>
        <strong>地图色彩</strong>
        <p class="subtle">切换地图底图时，左侧管理面板也会同步切换日间 / 夜间主题。</p>
      </div>
      <button class="btn secondary" type="button" @click="$emit('toggle-theme')">
        {{ mapTheme === "night" ? "日间地图" : "夜间地图" }}
      </button>
    </div>
  </section>
</template>
