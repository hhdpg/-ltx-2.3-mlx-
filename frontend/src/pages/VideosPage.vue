<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>视频作品</h2>
        <p class="hint">已完成任务的视频，点击卡片查看详情</p>
      </div>
      <el-button :loading="loading" @click="reload">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <div v-if="loading && tasks.length === 0" class="grid">
      <div v-for="n in 3" :key="n" class="panel card skeleton"></div>
    </div>

    <div v-else-if="tasks.length > 0" class="grid">
      <router-link
        v-for="task in tasks"
        :key="task.id"
        :to="`/tasks/${task.id}`"
        class="panel card"
      >
        <div class="thumb">
          <video :src="videoUrl(task.id)" preload="metadata" muted playsinline></video>
          <div class="thumb-overlay">
            <el-icon size="26"><VideoPlay /></el-icon>
          </div>
          <span class="type-badge">{{ task.task_type }}</span>
        </div>
        <div class="card-body">
          <div class="card-prompt">{{ task.prompt_excerpt }}</div>
          <div class="card-meta mono">
            {{ task.width }}×{{ task.height }} · {{ task.frames }}f ·
            {{ formatDuration(task.run_seconds) }}
          </div>
          <div class="card-meta faint">{{ formatDateTime(task.created_at) }}</div>
        </div>
      </router-link>
    </div>

    <div v-else class="panel empty-state">
      <el-icon size="34"><VideoCamera /></el-icon>
      <p>还没有已完成的视频作品</p>
      <router-link to="/generate" class="link">去新建生成 →</router-link>
    </div>

    <div v-if="total > pageSize" class="pager">
      <el-pagination
        background
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="onPageChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { fetchTasks, videoUrl } from "@/api/task";
import { extractError } from "@/api/http";
import { formatDateTime, formatDuration } from "@/utils/format";
import type { TaskSummary } from "@/types";

const tasks = ref<TaskSummary[]>([]);
const total = ref(0);
const loading = ref(false);
const page = ref(1);
const pageSize = 12;

async function reload() {
  loading.value = true;
  try {
    const data = await fetchTasks({
      status: "SUCCEEDED",
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    });
    tasks.value = data.items;
    total.value = data.total;
  } catch (err) {
    ElMessage.error(extractError(err).message);
    tasks.value = [];
  } finally {
    loading.value = false;
  }
}

function onPageChange(value: number) {
  page.value = value;
  void reload();
}

let timer: number | null = null;

onMounted(() => {
  void reload();
  timer = window.setInterval(() => void reload(), 15000);
});

onUnmounted(() => {
  if (timer !== null) window.clearInterval(timer);
});
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
}
.page-header h2 {
  margin: 0 0 4px;
  font-size: 20px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}
.card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: border-color 0.15s, transform 0.15s;
}
.card:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
}
.card.skeleton {
  height: 230px;
  background: var(--bg-panel-soft);
}
.thumb {
  position: relative;
  aspect-ratio: 16 / 10;
  background: #000;
  overflow: hidden;
}
.thumb video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.thumb-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #fff;
  background: rgba(0, 0, 0, 0.28);
  opacity: 0;
  transition: opacity 0.15s;
}
.card:hover .thumb-overlay {
  opacity: 1;
}
.type-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  font-size: 10px;
  font-family: var(--mono);
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.6);
  color: #d5e2ff;
}
.card-body {
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.card-prompt {
  font-size: 12.5px;
  color: var(--text);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 34px;
}
.card-meta {
  font-size: 11px;
  color: var(--text-dim);
}
.card-meta.faint {
  color: var(--text-faint);
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 60px 0;
  color: var(--text-faint);
}
.empty-state p {
  margin: 0;
  font-size: 13px;
}
.link {
  font-size: 12px;
}
.pager {
  display: flex;
  justify-content: flex-end;
}
</style>
