<script setup>
import { reactive, ref } from "vue";
import { createAdminAuthor, resetAdminAuthorPassword, updateAdminAuthor } from "../utils/api";

const props = defineProps({
  authors: { type: Array, required: true },
});

const emit = defineEmits(["refresh", "status"]);
const creating = ref(false);
const draft = reactive({ username: "", author_name: "", is_active: true });

async function createAuthor() {
  if (!draft.username.trim() || !draft.author_name.trim() || creating.value) return;
  creating.value = true;
  try {
    await createAdminAuthor({
      username: draft.username.trim(),
      author_name: draft.author_name.trim(),
      is_active: draft.is_active,
    });
    Object.assign(draft, { username: "", author_name: "", is_active: true });
    emit("status", "作者账号已创建，初始密码为 123123。");
    emit("refresh");
  } catch (error) {
    emit("status", `创建失败：${error.message}`);
  } finally {
    creating.value = false;
  }
}

async function saveAuthor(author) {
  try {
    await updateAdminAuthor(author.id, {
      username: author.username.trim(),
      author_name: author.author_name.trim(),
      is_active: Boolean(author.is_active),
    });
    emit("status", `已更新作者：${author.author_name}`);
    emit("refresh");
  } catch (error) {
    emit("status", `更新失败：${error.message}`);
  }
}

async function resetPassword(author) {
  if (!window.confirm(`将 ${author.author_name} 的密码重置为 123123，并要求下次登录修改？`)) return;
  try {
    await resetAdminAuthorPassword(author.id);
    emit("status", `已重置 ${author.author_name} 的密码，并注销其现有会话。`);
    emit("refresh");
  } catch (error) {
    emit("status", `重置失败：${error.message}`);
  }
}
</script>

<template>
  <section class="admin-module author-admin">
    <div class="section-title">
      <span>作者账号</span>
      <span class="pill">{{ authors.length }} 位</span>
    </div>

    <form class="author-create" @submit.prevent="createAuthor">
      <div class="field">
        <label for="newAuthorName">作者姓名</label>
        <input id="newAuthorName" v-model="draft.author_name" required placeholder="作者姓名">
      </div>
      <div class="field">
        <label for="newAuthorUsername">登录账号</label>
        <input id="newAuthorUsername" v-model="draft.username" required placeholder="adminxxx">
      </div>
      <label class="check-field">
        <input v-model="draft.is_active" type="checkbox">
        <span>立即启用</span>
      </label>
      <button class="btn" type="submit" :disabled="creating">
        {{ creating ? "创建中" : "添加作者" }}
      </button>
    </form>

    <div class="author-list">
      <article v-for="author in authors" :key="author.id" class="author-item">
        <div class="author-item-head">
          <strong>{{ author.author_name }}</strong>
          <span class="pill">{{ author.place_count }} 家店</span>
        </div>
        <div class="author-fields">
          <div class="field">
            <label :for="`authorName-${author.id}`">作者姓名</label>
            <input :id="`authorName-${author.id}`" v-model="author.author_name">
          </div>
          <div class="field">
            <label :for="`authorUsername-${author.id}`">登录账号</label>
            <input :id="`authorUsername-${author.id}`" v-model="author.username">
          </div>
        </div>
        <div class="author-actions">
          <label class="check-field">
            <input v-model="author.is_active" type="checkbox">
            <span>{{ author.is_active ? "已启用" : "已停用" }}</span>
          </label>
          <button class="btn secondary compact" type="button" @click="saveAuthor(author)">保存</button>
          <button class="btn secondary compact" type="button" @click="resetPassword(author)">重置密码</button>
        </div>
        <small class="subtle">
          {{ author.must_change_password ? "等待首次修改密码" : "密码已更新" }}
        </small>
      </article>
    </div>
  </section>
</template>
