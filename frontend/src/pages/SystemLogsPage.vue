<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>系统日志</h2>
        <p class="hint">应用日志与任务日志，自动刷新（不包含敏感环境变量）</p>
      </div>
      <div class="header-actions">
        <el-select v-model="source" style="width: 220px">
          <el-option label="应用日志（app.log）" value="app" />
          <el-option
            v-for="task in tasks"
            :key="task.id"
            :label="`任务日志 ${task.id.slice(0, 8)}`"
            :value="task.id"
          />
        </el-select>
        <el-switch v-model="autoRefresh" active-text="自动刷新" />
        <el-button @click="reload">立即刷新</el-button>
      </div>
    </div>

    <div class="panel log-panel">
      <div class="log-head">
        <span class="hint">{{ sourceLabel }}</span>
        <span class="spacer"></span>
        <span class="hint">{{ lines.length }} 行</span>
        <el-button size="small" text @click="copyAll">复制</el-button>
      </div>
      <pre ref="preRef" class="log-body">{{ display }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { fetchTaskLogs, fetchTasks } from "@/api/task";
import { fetchSystemLogs } from "@/api/system";
import { extractError } from "@/api/http";
import type { TaskSummary } from "@/types";
const source = ref<string>("app");
const tasks = ref<TaskSummary[]>([]);
const lines = ref<string[]>([]);
const autoRefresh = ref(true);
const preRef = ref<HTMLElement | null>(null);

const sourceLabel = computed(() => {
  if (source.value === "app") return "应用日志 · logs/app.log";
  const task = tasks.value.find((item) => item.id === source.value);
  return task
    ? `任务日志 · ${task.id.slice(0, 8)}（${task.status}）`
    : "任务日志";
});

const display = computed(() =>
  lines.value.length ? lines.value.join("\n") : "（暂无日志内容）",
);

async function loadTasks() {
  try {
    const data = await fetchTasks({ limit: 20 });
    tasks.value = data.items;
  } catch {
    tasks.value = [];
  }
}

async function reload() {
  try {
    if (source.value === "app") {
      const data = await fetchSystemLogs(1000);
      lines.value = data.lines;
    } else {
      const data = await fetchTaskLogs(source.value, 1000);
      lines.value = data.lines;
    }
    if (autoRefresh.value) {
      await nextTick();
      if (preRef.value) preRef.value.scrollTop = preRef.value.scrollHeight;
    }
  } catch (err) {
    ElMessage.error(extractError(err).message);
  }
}

async function copyAll() {
  try {
    await navigator.clipboard.writeText(display.value);
    ElMessage.success("已复制");
  } catch {
    ElMessage.error("复制失败");
  }
}

let timer: number | null = null;

watch(source, () => void reload());

onMounted(async () => {
  await loadTasks();
  await reload();
  timer = window.setInterval(() => {
    if (autoRefresh.value) void reload();
  }, 3000);
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
  height: 100%;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
}
.page-header h2 {
  margin: 0 0 4px;
  font-size: 20px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.log-panel {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  min-height: 420px;
}
.log-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.log-head .spacer {
  flex: 1;
}
.log-body {
  margin: 0;
  flex: 1;
  background: #0a0d12;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  overflow: auto;
  font-size: 11.5px;
  line-height: 1.6;
  color: #b9c6d4;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: calc(100vh - 260px);
}
</style>
