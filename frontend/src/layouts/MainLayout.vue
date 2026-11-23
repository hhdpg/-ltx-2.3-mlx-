<template>
  <div class="layout">
    <header class="topbar">
      <div class="brand">
        <span class="logo">LTX</span>
        <div class="brand-text">
          <strong>LTX Studio</strong>
          <span>本地视频生成工作台</span>
        </div>
      </div>

      <div class="status-area">
        <div class="status-chip" :title="mlxTitle">
          <span class="dot" :class="mlxDot"></span>
          <span>MLX GPU</span>
          <em>{{ mlxLabel }}</em>
        </div>
        <div class="status-chip" :title="modelTitle">
          <span class="dot" :class="modelDot"></span>
          <span>模型</span>
          <em>{{ modelLabel }}</em>
        </div>
        <el-button
          text
          :loading="system.loading"
          size="small"
          @click="recheck"
        >
          重新检测
        </el-button>
      </div>
    </header>

    <div class="body">
      <aside class="sidebar">
        <nav class="nav">
          <router-link
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            class="nav-item"
            :class="{ active: isActive(item.to) }"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </router-link>
        </nav>

        <div class="sidebar-block">
          <div class="block-title">最近任务</div>
          <div v-if="generation.recentTasks.length === 0" class="empty-mini">
            暂无任务
          </div>
          <router-link
            v-for="task in generation.recentTasks"
            :key="task.id"
            :to="`/tasks/${task.id}`"
            class="mini-task"
          >
            <span class="dot" :class="dotClass(task.status)"></span>
            <span class="mini-text">{{ task.prompt_excerpt }}</span>
          </router-link>
        </div>

        <div class="sidebar-foot">
          <div class="foot-line">
            <span>离线模式</span>
            <code>{{ system.health?.offline_mode ? "开启" : "关闭" }}</code>
          </div>
          <div class="foot-line">
            <span>队列</span>
            <code>{{ system.health?.queue_running ? "运行中" : "空闲" }}</code>
          </div>
        </div>
      </aside>

      <main class="content">
        <router-view />
      </main>
    </div>

    <footer class="statusbar">
      <span class="dot" :class="currentDot"></span>
      <span>当前任务：{{ currentLabel }}</span>
      <span v-if="system.blockingReasons.length" class="block-reason">
        · {{ system.blockingReasons[0] }}
      </span>
      <span class="spacer"></span>
      <span class="mono small">127.0.0.1 · 本地推理</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import { useSystemStore } from "@/stores/system";
import { useGenerationStore } from "@/stores/generation";
import { statusMeta } from "@/utils/format";
import type { TaskStatus } from "@/types";

const system = useSystemStore();
const generation = useGenerationStore();
const route = useRoute();

const navItems = [
  { to: "/generate", label: "新建生成", icon: "MagicStick" },
  { to: "/projects", label: "连续创作", icon: "Film" },
  { to: "/tasks", label: "任务历史", icon: "List" },
  { to: "/videos", label: "视频作品", icon: "VideoCamera" },
  { to: "/settings", label: "模型与环境", icon: "Cpu" },
  { to: "/logs", label: "系统日志", icon: "Document" },
];

function isActive(path: string): boolean {
  if (path === "/tasks") {
    // 任务详情也属于任务历史；/videos 单独高亮
    return route.path.startsWith("/tasks");
  }
  return route.path === path || route.path.startsWith(`${path}/`);
}

const mlxDot = computed(() => {
  if (!system.health) return "idle";
  return system.health.mlx_available ? "ok" : "error";
});
const mlxLabel = computed(() => {
  if (!system.health) return "检测中";
  return system.health.mlx_available ? "就绪" : "不可用";
});
const mlxTitle = computed(
  () => system.health?.mlx_device ?? system.health?.mlx_error ?? "尚未检测",
);

const modelDot = computed(() => {
  const health = system.health;
  if (!health) return "idle";
  if (health.model_configured && health.model_path) return "ok";
  return "error";
});
const modelLabel = computed(() => {
  const health = system.health;
  if (!health) return "检测中";
  return health.model_configured && health.model_path ? "已配置" : "未配置";
});
const modelTitle = computed(
  () => system.health?.model_path ?? system.health?.model_error ?? "模型未配置",
);

const activeTask = computed(() => generation.activeTask ?? null);
const currentLabel = computed(() => {
  if (!activeTask.value) return "空闲";
  return statusMeta(activeTask.value.status).label;
});
const currentDot = computed(() => {
  if (!activeTask.value) return "idle";
  return dotClass(activeTask.value.status);
});

function dotClass(status: TaskStatus): string {
  return statusMeta(status).active ? "warn" : status === "SUCCEEDED" ? "ok" : "idle";
}

let timer: number | null = null;

async function recheck() {
  await system.refreshAll();
  await generation.loadRecent();
}

onMounted(async () => {
  await generation.loadRecent();
  timer = window.setInterval(() => {
    void generation.loadRecent();
  }, 5000);
});

onUnmounted(() => {
  if (timer !== null) window.clearInterval(timer);
});
</script>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.topbar {
  height: 56px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: linear-gradient(135deg, #4c8dff, #8b5cf6);
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.5px;
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}
.brand-text strong {
  font-size: 14px;
}
.brand-text span {
  font-size: 11px;
  color: var(--text-faint);
}

.status-area {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-dim);
}
.status-chip em {
  font-style: normal;
  color: var(--text);
}

.body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.sidebar {
  width: 208px;
  flex: none;
  border-right: 1px solid var(--border);
  background: var(--bg-panel);
  display: flex;
  flex-direction: column;
  padding: 14px 10px;
  gap: 18px;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  color: var(--text-dim);
  font-size: 13px;
  transition: background 0.15s, color 0.15s;
}
.nav-item:hover {
  background: var(--bg-panel-soft);
  color: var(--text);
}
.nav-item.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 500;
}

.sidebar-block {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.block-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-faint);
  margin-bottom: 8px;
  padding-left: 4px;
}
.empty-mini {
  font-size: 12px;
  color: var(--text-faint);
  padding: 4px;
}
.mini-task {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 6px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-dim);
}
.mini-task:hover {
  background: var(--bg-panel-soft);
  color: var(--text);
}
.mini-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-foot {
  border-top: 1px solid var(--border);
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.foot-line {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-faint);
}
.foot-line code {
  color: var(--text-dim);
}

.content {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 18px 20px 24px;
}

.statusbar {
  height: 30px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 18px;
  border-top: 1px solid var(--border);
  background: var(--bg-panel);
  font-size: 12px;
  color: var(--text-dim);
}
.statusbar .spacer {
  flex: 1;
}
.block-reason {
  color: var(--warn);
}
.small {
  font-size: 11px;
  color: var(--text-faint);
}
</style>
