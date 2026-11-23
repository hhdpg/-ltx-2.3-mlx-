<template>
  <div class="log-viewer">
    <div class="log-toolbar">
      <div class="left">
        <span class="dot" :class="polling ? 'warn' : 'idle'"></span>
        <span class="hint">{{ polling ? "自动刷新中" : "已停止刷新" }}</span>
        <span class="hint">· {{ lines.length }} 行</span>
      </div>
      <div class="right">
        <el-switch
          v-model="autoScroll"
          active-text="自动滚动"
          size="small"
        />
        <el-button size="small" text @click="refresh">立即刷新</el-button>
        <el-button size="small" text @click="copyAll">复制全部</el-button>
      </div>
    </div>

    <pre ref="preRef" class="log-body">{{ displayText }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { fetchTaskLogs } from "@/api/task";
import type { TaskStatus } from "@/types";

const props = defineProps<{
  taskId: string;
  status: TaskStatus;
  active: boolean;
}>();

const lines = ref<string[]>([]);
const autoScroll = ref(true);
const polling = ref(false);
const preRef = ref<HTMLElement | null>(null);

const terminal: TaskStatus[] = ["SUCCEEDED", "FAILED", "CANCELED"];
const displayText = computed(() =>
  lines.value.length ? lines.value.join("\n") : "（暂无日志）",
);

let timer: number | null = null;

async function refresh() {
  try {
    const data = await fetchTaskLogs(props.taskId, 1000);
    const changed =
      data.lines.length !== lines.value.length ||
      data.lines[data.lines.length - 1] !== lines.value[lines.value.length - 1];
    lines.value = data.lines;
    if (changed && autoScroll.value) {
      await nextTick();
      if (preRef.value) preRef.value.scrollTop = preRef.value.scrollHeight;
    }
  } catch {
    // 轮询失败静默处理，避免日志组件刷屏报错
  }
}

function startPolling() {
  stopPolling();
  polling.value = true;
  void refresh();
  timer = window.setInterval(async () => {
    await refresh();
    if (terminal.includes(props.status)) {
      stopPolling();
    }
  }, 2000);
}

function stopPolling() {
  if (timer !== null) {
    window.clearInterval(timer);
    timer = null;
  }
  polling.value = false;
}

async function copyAll() {
  try {
    await navigator.clipboard.writeText(displayText.value);
    ElMessage.success("日志已复制");
  } catch {
    ElMessage.error("复制失败，请手动选择文本");
  }
}

watch(
  () => props.active,
  (active) => {
    if (active) startPolling();
    else stopPolling();
  },
  { immediate: true },
);

watch(
  () => props.status,
  (status) => {
    if (terminal.includes(status)) {
      void refresh().then(() => stopPolling());
    }
  },
);

onUnmounted(stopPolling);

defineExpose({ refresh, getLines: () => lines.value });
</script>

<style scoped>
.log-viewer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.log-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.left,
.right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.log-body {
  margin: 0;
  background: #0a0d12;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  height: 320px;
  overflow: auto;
  font-size: 11.5px;
  line-height: 1.6;
  color: #b9c6d4;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
