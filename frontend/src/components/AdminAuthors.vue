<script setup>
import { reactive, ref } from "vue";
import {
  createAdminAuthor,
  deleteAdminAuthor,
  resendAdminAuthorInvitation,
  resetAdminAuthorPassword,
  updateAdminAuthor,
} from "../utils/api";

defineProps({ authors: { type: Array, required: true } });
const emit = defineEmits(["refresh", "status"]);
const creating = ref(false);
const busyId = ref(null);
const draft = reactive({ author_name: "", email: "" });

function accountState(author) {
  if (!author.is_active) return "已停用";
  if (author.account_status === "pending_invite") return "等待激活";
  if (author.email && !author.email_verified) return "邮箱未验证";
  return "正常";
}

async function createAuthor() {
  if (!draft.author_name.trim() || !draft.email.trim() || creating.value) return;
  creating.value = true;
  try {
    await createAdminAuthor({ author_name: draft.author_name.trim(), email: draft.email.trim() });
    Object.assign(draft, { author_name: "", email: "" });
    emit("status", "邀请已发送。作者需要通过邮件设置账号和密码。");
    emit("refresh");
  } catch (error) {
    emit("status", `邀请失败：${error.message}`);
  } finally {
    creating.value = false;
  }
}

async function saveAuthor(author) {
  busyId.value = author.id;
  try {
    await updateAdminAuthor(author.id, {
      author_name: author.author_name.trim(),
      email: String(author.email || "").trim(),
      is_active: Boolean(author.is_active),
    });
    emit("status", `已更新作者：${author.author_name}`);
    emit("refresh");
  } catch (error) {
    emit("status", `更新失败：${error.message}`);
  } finally {
    busyId.value = null;
  }
}

async function sendInvitation(author) {
  if (!author.email) {
    emit("status", "请先填写并保存作者邮箱。");
    return;
  }
  busyId.value = author.id;
  try {
    await resendAdminAuthorInvitation(author.id);
    emit("status", `激活链接已发送给 ${author.author_name}。旧链接已经失效。`);
    emit("refresh");
  } catch (error) {
    emit("status", `发送失败：${error.message}`);
  } finally {
    busyId.value = null;
  }
}

async function resetPassword(author) {
  if (!author.email) {
    emit("status", "请先填写并保存作者邮箱。");
    return;
  }
  if (!window.confirm(`向 ${author.author_name} 发送密码重置邮件？`)) return;
  busyId.value = author.id;
  try {
    await resetAdminAuthorPassword(author.id);
    emit("status", `密码重置邮件已发送给 ${author.author_name}。`);
  } catch (error) {
    emit("status", `发送失败：${error.message}`);
  } finally {
    busyId.value = null;
  }
}

async function removeAuthor(author) {
  if (author.place_count > 0) {
    emit("status", `无法删除：${author.author_name} 名下仍有 ${author.place_count} 家店。请先停用账号或处理名下店铺。`);
    return;
  }
  const confirmation = window.prompt(
    `即将永久删除作者账号“${author.author_name}”。\n该操作会清除会话、邀请、密码重置和第三方绑定，无法撤销。\n\n请输入完整作者名确认：`,
  );
  if (confirmation === null) return;
  if (confirmation.trim() !== author.author_name) {
    emit("status", "删除已取消：输入的作者名不匹配。");
    return;
  }
  busyId.value = author.id;
  try {
    await deleteAdminAuthor(author.id, confirmation.trim());
    emit("status", `已永久删除作者账号：${author.author_name}`);
    emit("refresh");
  } catch (error) {
    emit("status", `删除失败：${error.message}`);
  } finally {
    busyId.value = null;
  }
}
</script>

<template>
  <section class="admin-module author-admin">
    <div class="section-title">
      <span>作者账号</span>
      <span class="pill">{{ authors.length }} 位</span>
    </div>

    <form class="author-create author-invite-form" @submit.prevent="createAuthor">
      <div class="field">
        <label for="newAuthorName">作者名</label>
        <input id="newAuthorName" v-model="draft.author_name" required maxlength="80" placeholder="用于地图署名">
      </div>
      <div class="field">
        <label for="newAuthorEmail">邮箱</label>
        <input id="newAuthorEmail" v-model="draft.email" type="email" required autocomplete="off" placeholder="author@example.com">
      </div>
      <button class="btn" type="submit" :disabled="creating">{{ creating ? "发送中" : "发送邀请" }}</button>
      <p class="subtle invite-explanation">系统发送 24 小时内有效的一次性链接；作者自行设置账号和密码。</p>
    </form>

    <div class="author-list">
      <article v-for="author in authors" :key="author.id" class="author-item">
        <div class="author-item-head">
          <div>
            <strong>{{ author.author_name }}</strong>
            <small v-if="author.username" class="author-username">@{{ author.username }}</small>
          </div>
          <div class="author-badges">
            <span class="pill">{{ author.place_count }} 家店</span>
            <span class="pill" :class="{ 'status-pending': accountState(author) !== '正常' }">{{ accountState(author) }}</span>
          </div>
        </div>
        <div class="author-fields">
          <div class="field">
            <label :for="`authorName-${author.id}`">作者名</label>
            <input :id="`authorName-${author.id}`" v-model="author.author_name" maxlength="80">
          </div>
          <div class="field">
            <label :for="`authorEmail-${author.id}`">邮箱</label>
            <input :id="`authorEmail-${author.id}`" v-model="author.email" type="email" placeholder="尚未填写">
          </div>
        </div>
        <div class="author-actions">
          <label class="check-field">
            <input v-model="author.is_active" type="checkbox">
            <span>{{ author.is_active ? "已启用" : "已停用" }}</span>
          </label>
          <button class="btn secondary compact" type="button" :disabled="busyId === author.id" @click="saveAuthor(author)">保存</button>
          <button class="btn secondary compact" type="button" :disabled="busyId === author.id || !author.email" @click="sendInvitation(author)">
            {{ author.account_status === "pending_invite" ? "重发邀请" : "发送验证链接" }}
          </button>
          <button v-if="author.account_status === 'active'" class="btn secondary compact" type="button" :disabled="busyId === author.id || !author.email" @click="resetPassword(author)">重置密码</button>
          <button class="btn danger compact author-delete-button" type="button" :disabled="busyId === author.id" :title="author.place_count > 0 ? `名下仍有 ${author.place_count} 家店，不能删除` : '永久删除作者账号'" @click="removeAuthor(author)">删除账号</button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.author-delete-button {
  border-color: rgba(190, 45, 65, 0.42) !important;
  background: rgba(190, 45, 65, 0.08) !important;
  color: #a52b3f !important;
}

.author-delete-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
</style>
