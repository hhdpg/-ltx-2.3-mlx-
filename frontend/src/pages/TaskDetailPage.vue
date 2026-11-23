<template>
  <div class="page">
    <div class="page-header">
      <div>
        <router-link to="/tasks" class="back-link">← 返回任务列表</router-link>
        <h2>任务详情</h2>
        <p class="hint mono">{{ taskId }}</p>
      </div>
      <div class="header-actions" v-if="task">
        <el-button
          v-if="isActive(task.status)"
          type="warning"
          plain
          @click="onCancel"
        >
          取消任务
        </el-button>
        <el-button
          v-else
          type="danger"
          plain
          @click="onDelete"
        >
          删除任务
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="loadError"
      type="error"
      :closable="false"
      show-icon
      :title="loadError"
    />

    <div v-else-if="loading && !task" class="panel loading-panel">
      <el-skeleton :rows="6" animated />
    </div>

    <template v-else-if="task">
      <div class="layout-grid">
        <section class="panel main-panel">
          <div class="status-row">
            <TaskStatusTag :status="task.status" />
            <span class="type-chip" :class="task.task_type === 'I2V' ? 'i2v' : 't2v'">
              {{ task.task_type === "I2V" ? "图片生成" : "文字生成" }}
            </span>
            <span class="hint" v-if="isActive(task.status)">
              已运行 {{ elapsed }}
            </span>
            <span class="spacer"></span>
            <span class="hint mono">{{ task.width }}×{{ task.height }} · {{ task.frames }}帧 · {{ task.frame_rate }}FPS</span>
          </div>

          <el-alert
            v-if="task.status === 'FAILED'"
            type="error"
            :closable="false"
            show-icon
            class="error-alert"
          >
            <template #title>{{ task.error_message || "生成失败" }}</template>
            <div class="error-actions">
              <span class="hint">完整信息见下方运行日志</span>
              <el-button size="small" text type="primary" @click="copyError">
                复制错误信息
              </el-button>
            </div>
          </el-alert>

          <div v-if="task.status === 'SUCCEEDED' && task.video_url" class="video-section">
            <h3 class="section-title">生成结果</h3>
            <VideoPlayer :src="withBase(task.video_url)" />
            <div class="video-actions">
              <el-button type="primary" @click="downloadVideo">
                <el-icon><Download /></el-icon>
                下载 MP4
              </el-button>
              <el-button @click="retakeVisible = true">
                <el-icon><Crop /></el-icon>
                局部重拍
              </el-button>
              <el-button
                v-if="task.task_type !== 'EXTEND' && task.task_type !== 'RETAKE'"
                @click="startContinuation"
              >
                <el-icon><VideoPlay /></el-icon>
                继续创作
              </el-button>
              <router-link
                v-else-if="extendProjectId"
                :to="`/projects/${extendProjectId}`"
                class="link-inline"
              >
                返回创作项目 →
              </router-link>
              <span class="hint">MP4 · 本地输出目录 · 支持拖动播放</span>
            </div>
          </div>

          <div v-else-if="task.status === 'QUEUED'" class="waiting-box">
            <el-icon size="22" class="spin-slow"><Loading /></el-icon>
            <div>
              <div>任务排队中，等待前序任务完成</div>
              <div class="hint">单任务队列：同一时间只允许一个推理进程</div>
            </div>
          </div>

          <div v-else-if="isActive(task.status)" class="waiting-box">
            <span class="dot warn pulse"></span>
            <div>
              <div>正在生成…（CLI 未提供结构化进度，不显示虚假百分比）</div>
              <div class="hint">已运行 {{ elapsed }}，日志实时刷新</div>
            </div>
          </div>

          <div v-else-if="task.status === 'FAILED'" class="waiting-box failed">
            <el-icon size="20" color="var(--error)"><CircleClose /></el-icon>
            <div>
              <div>任务未完成</div>
              <div class="hint">{{ task.error_message || "请查看日志定位原因" }}</div>
            </div>
          </div>

          <div v-else-if="task.status === 'CANCELED'" class="waiting-box">
            <el-icon size="20"><Remove /></el-icon>
            <div>
              <div>任务已取消</div>
              <div class="hint">未产生输出文件</div>
            </div>
          </div>

          <h3 class="section-title">运行日志</h3>
          <TaskLogViewer
            ref="logViewer"
            :task-id="task.id"
            :status="task.status"
            :active="true"
          />
        </section>

        <aside class="side-column">
          <section class="panel side-panel">
            <h3 class="panel-title">提示词</h3>
            <p class="prompt-full">{{ task.prompt }}</p>
          </section>

          <section v-if="task.task_type === 'I2V'" class="panel side-panel">
            <h3 class="panel-title">参考图片</h3>
            <img
              v-if="task.image_url"
              :src="withBase(task.image_url)"
              class="ref-image"
              alt="参考图片"
            />
            <p v-else class="hint">图片已不存在</p>
          </section>

          <section class="panel side-panel">
            <h3 class="panel-title">推理参数</h3>
            <div class="kv"><span>任务类型</span><code>{{ task.task_type }}</code></div>
            <div class="kv"><span>分辨率</span><code>{{ task.width }} × {{ task.height }}</code></div>
            <div class="kv"><span>帧数</span><code>{{ task.frames }}（8k+1）</code></div>
            <div class="kv"><span>帧率</span><code>{{ task.frame_rate }} FPS</code></div>
            <div class="kv"><span>模式</span><code>{{ task.mode }}</code></div>
            <div class="kv">
              <span>随机种子</span>
              <code>{{ task.seed ?? "随机" }}</code>
            </div>
            <div class="kv"><span>模型路径</span></div>
            <code class="path-block">{{ task.model_path }}</code>
            <template v-if="task.command_preview">
              <div class="kv" style="margin-top: 8px"><span>实际命令</span></div>
              <pre class="cmd-block">{{ task.command_preview }}</pre>
            </template>
          </section>

          <section class="panel side-panel">
            <h3 class="panel-title">时间信息</h3>
            <div class="kv"><span>创建</span><code>{{ formatDateTime(task.created_at) }}</code></div>
            <div class="kv"><span>开始</span><code>{{ formatDateTime(task.started_at) }}</code></div>
            <div class="kv"><span>结束</span><code>{{ formatDateTime(task.finished_at) }}</code></div>
            <div class="kv"><span>耗时</span><code>{{ formatDuration(task.run_seconds) }}</code></div>
            <div class="kv"><span>退出码</span><code>{{ task.exit_code ?? "—" }}</code></div>
            <div class="kv"><span>进程 PID</span><code>{{ task.pid ?? "—" }}</code></div>
          </section>

          <section v-if="task.output_path" class="panel side-panel">
            <h3 class="panel-title">输出文件</h3>
            <code class="path-block">{{ task.output_path }}</code>
          </section>
        </aside>
      </div>
    </template>

    <RetakeDialog
      v-model="retakeVisible"
      :task-id="task?.id ?? null"
      @submitted="onRetakeSubmitted"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import TaskStatusTag from "@/components/TaskStatusTag.vue";
import RetakeDialog from "@/components/RetakeDialog.vue";
import TaskLogViewer from "@/components/TaskLogViewer.vue";
import VideoPlayer from "@/components/VideoPlayer.vue";
import { cancelTask, deleteTask, downloadUrl, fetchTask } from "@/api/task";
import {
  attachSegment,
  createProject,
  fetchProjects,
} from "@/api/project";
import { extractError } from "@/api/http";
import { formatDateTime, formatDuration } from "@/utils/format";
import type { TaskDetail, TaskStatus } from "@/types";

const route = useRoute();
const router = useRouter();

const taskId = computed(() => String(route.params.id));
const task = ref<TaskDetail | null>(null);
const loading = ref(false);
const loadError = ref<string | null>(null);
const now = ref(Date.now());
const logViewer = ref<InstanceType<typeof TaskLogViewer> | null>(null);

const terminal: TaskStatus[] = ["SUCCEEDED", "FAILED", "CANCELED"];

const isActive = (status: TaskStatus) =>
  ["QUEUED", "STARTING", "RUNNING", "CANCELING"].includes(status);

const elapsed = computed(() => {
  if (!task.value) return "—";
  if (task.value.run_seconds) return formatDuration(task.value.run_seconds);
  if (!task.value.started_at) return "—";
  const start = new Date(task.value.started_at).getTime();
  return formatDuration((now.value - start) / 1000);
});

function withBase(path: string): string {
  return path.startsWith("/api") ? path : `/api${path}`;
}

async function load(showError = true) {
  try {
    task.value = await fetchTask(taskId.value);
    loadError.value = null;
    if (task.value.task_type === "EXTEND") {
      await loadExtendProject();
    }
  } catch (err) {
    const info = extractError(err);
    if (showError) {
      if (info.status === 404) {
        loadError.value = "任务不存在或已被删除";
      } else {
        loadError.value = info.message;
      }
    }
  }
}

async function onCancel() {
  if (!task.value) return;
  try {
    await ElMessageBox.confirm(
      "取消后推理进程会被终止，已生成的部分不会保留。确定取消吗？",
      "取消任务",
      { confirmButtonText: "取消任务", cancelButtonText: "再等等", type: "warning" },
    );
  } catch {
    return;
  }
  try {
    await cancelTask(task.value.id);
    ElMessage.success("已发送取消请求");
    await load(false);
  } catch (err) {
    ElMessage.error(extractError(err).message);
  }
}

async function onDelete() {
  if (!task.value) return;
  try {
    await ElMessageBox.confirm(
      "删除任务记录及输出视频文件，不可恢复。确定删除吗？",
      "删除任务",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "error" },
    );
  } catch {
    return;
  }
  try {
    await deleteTask(task.value.id, true);
    ElMessage.success("任务已删除");
    void router.push("/tasks");
  } catch (err) {
    ElMessage.error(extractError(err).message);
  }
}

function downloadVideo() {
  if (!task.value) return;
  window.location.href = downloadUrl(task.value.id);
}

const extendProjectId = ref<string | null>(null);
const retakeVisible = ref(false);

function onRetakeSubmitted(taskId: string) {
  ElMessage.success(`重拍任务已排队：${taskId.slice(0, 8)}`);
}

/** 把成功视频加入某个创作项目，然后跳到项目续写页。 */
async function startContinuation() {
  if (!task.value) return;
  try {
    const { items } = await fetchProjects();
    let projectId: string;
    if (items.length === 0) {
      const created = await createProject({
        name: `创作 ${new Date().toLocaleDateString("zh-CN")}`,
      });
      projectId = created.id;
      ElMessage.success("已创建新创作项目");
    } else if (items.length === 1) {
      projectId = items[0].id;
    } else {
      const chosen = await pickProject(items);
      if (!chosen) return;
      projectId = chosen;
    }
    await attachSegment(projectId, task.value.id);
    ElMessage.success("已加入创作项目，可以开始续写");
    void router.push(`/projects/${projectId}`);
  } catch (err) {
    const info = extractError(err);
    // 该任务已在某个项目里时，直接跳到对应项目
    if (info.status === 409 && info.message.includes("已加入项目")) {
      const { items } = await fetchProjects().catch(() => ({ items: [] }));
      const match = items.find((p) => p.id === extendProjectId.value) ?? items[0];
      if (match) {
        void router.push(`/projects/${match.id}`);
        return;
      }
    }
    ElMessage.error(info.message);
  }
}

/** 多项目时用简单确认框让用户选择。 */
async function pickProject(projects: { id: string; name: string }[]): Promise<string | null> {
  const result = await ElMessageBox.prompt(
    `检测到 ${projects.length} 个创作项目，请输入要加入的项目名称：\n` +
      projects.map((p) => `· ${p.name}`).join("\n"),
    "选择创作项目",
    {
      confirmButtonText: "加入",
      cancelButtonText: "取消",
      inputValidator: (value) =>
        projects.some((p) => p.name === (value ?? "").trim())
          ? true
          : "请输入列表中存在的项目名称",
    },
  ).catch(() => null);
  if (!result) return null;
  const value = String(result.value).trim();
  return projects.find((p) => p.name === value)?.id ?? null;
}

/** 续写任务：找到它所属的项目，提供“返回创作项目”入口。 */
async function loadExtendProject() {
  if (!task.value || task.value.task_type !== "EXTEND") return;
  try {
    const { items } = await fetchProjects();
    for (const project of items) {
      if (extendProjectId.value) break;
      const resp = await fetch(`/api/projects/${project.id}/segments`);
      if (!resp.ok) continue;
      const data = await resp.json();
      const segs = (data.items ?? []) as { task_id: string; project_id: string }[];
      const match = segs.find((item) => item.task_id === task.value?.id);
      if (match) {
        extendProjectId.value = match.project_id;
        break;
      }
    }
  } catch {
    // 忽略：仅影响入口显示
  }
}

async function copyError() {
  if (!task.value) return;
  const logs = logViewer.value?.getLines() ?? [];
  const payload = [
    `任务: ${task.value.id}`,
    `状态: ${task.value.status}`,
    `错误: ${task.value.error_message ?? ""}`,
    "",
    ...logs,
  ].join("\n");
  try {
    await navigator.clipboard.writeText(payload);
    ElMessage.success("错误信息已复制");
  } catch {
    ElMessage.error("复制失败，请手动选择日志文本");
  }
}

let pollTimer: number | null = null;
let tickTimer: number | null = null;

onMounted(async () => {
  loading.value = true;
  await load();
  loading.value = false;

  pollTimer = window.setInterval(async () => {
    if (!task.value) return;
    if (terminal.includes(task.value.status)) return;
    const previous = task.value.status;
    await load(false);
    if (task.value && previous !== task.value.status) {
      void logViewer.value?.refresh();
    }
  }, 2500);

  tickTimer = window.setInterval(() => {
    now.value = Date.now();
  }, 1000);
});

onUnmounted(() => {
  if (pollTimer !== null) window.clearInterval(pollTimer);
  if (tickTimer !== null) window.clearInterval(tickTimer);
});
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1320px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
}
.page-header h2 {
  margin: 2px 0 4px;
  font-size: 20px;
}
.back-link {
  font-size: 12px;
}
.header-actions {
  display: flex;
  gap: 8px;
}

.layout-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
  align-items: start;
}
@media (max-width: 1120px) {
  .layout-grid {
    grid-template-columns: 1fr;
  }
}

.main-panel {
  padding: 16px 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.loading-panel {
  padding: 24px;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.status-row .spacer {
  flex: 1;
}
.type-chip {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 4px;
}
.type-chip.t2v {
  color: #7fb1ff;
  background: rgba(76, 141, 255, 0.14);
}
.type-chip.i2v {
  color: #c4a3ff;
  background: rgba(139, 92, 246, 0.16);
}

.error-alert {
  margin: 0;
}
.error-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-dim);
  margin: 6px 0 0;
}

.video-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.video-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.waiting-box {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-radius: var(--radius);
  background: var(--bg-panel-soft);
  border: 1px solid var(--border);
  font-size: 13px;
}
.waiting-box.failed {
  border-color: rgba(248, 81, 73, 0.4);
}
.spin-slow {
  animation: spin 2.4s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.pulse {
  animation: pulse 1.6s ease-in-out infinite;
}
@keyframes pulse {
  0%,
  100% {
    opacity: 0.4;
  }
  50% {
    opacity: 1;
  }
}

.side-column {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.side-panel {
  padding: 14px 16px;
}
.prompt-full {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}
.ref-image {
  width: 100%;
  border-radius: 8px;
  border: 1px solid var(--border);
  display: block;
}
.kv {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  color: var(--text-faint);
  padding: 3px 0;
}
.kv code {
  color: var(--text);
  text-align: right;
}
.path-block {
  display: block;
  font-size: 11px;
  color: var(--text-dim);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  word-break: break-all;
}
.cmd-block {
  margin: 0;
  font-size: 11px;
  line-height: 1.6;
  color: var(--text-dim);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  white-space: pre-wrap;
  word-break: break-all;
}
.link-inline {
  font-size: 12px;
}
</style>
