<script setup>
defineProps({
  active: { type: String, required: true },
});

defineEmits(["change"]);

const items = [
  ["list", "店家库"],
  ["search", "搜索导入"],
  ["bulk", "批量新建"],
  ["edit", "编辑资料"],
  ["authors", "作者账号"],
  ["settings", "地图设置"],
];
</script>

<template>
  <nav class="admin-menu" aria-label="管理菜单">
    <button
      v-for="[key, label] in items"
      :key="key"
      class="admin-menu-btn"
      :class="{ 'is-active': active === key }"
      type="button"
      @click="$emit('change', key)"
    >
      {{ label }}
    </button>
  </nav>
</template>
