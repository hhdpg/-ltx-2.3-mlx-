<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>任务历史</h2>
        <p class="hint">共 {{ total }} 个任务 · 状态由后端统一维护</p>
      </div>
      <div class="header-actions">
        <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 140px" @change="reload">
          <el-option v-for="option in statusOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
        <el-select v-model="typeFilter" placeholder="全部类型" clearable style="width: 120px" @change="reload">
          <el-option label="文字生成 T2V" value="T2V" />
          <el-option label="图片生成 I2V" value="I2V" />
        </el-select>
        <el-button :loading="loading" @click="reload">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <div class="panel table-panel">
      <div v-if="tasks.length > 0" class="task-table">
        <div class="task-row task-head">
          <div class="col-id">任务编号</div>
          <div class="col-type">类型</div>
          <div class="col-prompt">提示词</div>
          <div class="col-params">参数</div>
          <div class="col-status">状态</div>
          <div class="col-time">耗时 / 创建</div>
          <div class="col-actions">操作</div>
        </div>        <div
          v-for="row in tasks"
          :key="row.id"
          class="task-row task-body"
          @click="openTask(row)"
        >
          <div class="col-id">
            <code class="mono">{{ row.id.slice(0, 8) }}</code>
          </div>
          <div class="col-type">
            <span class="type-chip" :class="typeChipClass(row.task_type)">
              {{ row.task_type }}
            </span>
          </div>
          <div class="col-prompt" :title="row.prompt">
            <span class="prompt-cell">{{ row.prompt_excerpt }}</span>
          </div>
          <div class="col-params mono small">
            {{ row.width }}x{{ row.height }} / {{ row.frames }}f
          </div>
          <div class="col-status">
            <TaskStatusTag :status="row.status" />
          </div>
          <div class="col-time">
            <div class="mono small">{{ formatDuration(row.run_seconds) }}</div>
            <div class="mono tiny">{{ formatShort(row.created_at) }}</div>
          </div>
          <div class="col-actions" @click.stop>
            <el-button size="small" text type="primary" @click="openTask(row)">
              详情
            </el-button>
            <el-button
              v-if="isActive(row.status)"
              size="small"
              text
              type="warning"
              @click="onCancel(row)"
            >
              取消
            </el-button>
            <el-button
              v-else
              size="small"
              text
              type="danger"
              @click="onDelete(row)"
            >
              删除
            </el-button>
          </div>
        </div>
      </div>

      <div v-else-if="!loading" class="empty-state">
        <el-icon size="34"><Files /></el-icon>
        <p>{{ hasFilter ? "没有符合筛选条件的任务" : "还没有生成任务" }}</p>
        <router-link to="/generate" class="link">去新建生成 →</router-link>
      </div>

      <div class="pager">
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import TaskStatusTag from "@/components/TaskStatusTag.vue";
import { cancelTask, deleteTask, fetchTasks } from "@/api/task";
import { extractError } from "@/api/http";
import { formatDateTime, formatDuration } from "@/utils/format";
import type { TaskStatus, TaskSummary } from "@/types";

const router = useRouter();

function formatShort(value: string | null | undefined): string {
  if (!value) return "—";
  const full = formatDateTime(value);
  return full.length > 16 ? full.slice(5) : full;
}

const tasks = ref<TaskSummary[]>([]);
const total = ref(0);
const loading = ref(false);
const statusFilter = ref<TaskStatus | "">("");
const typeFilter = ref<"T2V" | "I2V" | "">("");
const page = ref(1);
const pageSize = 20;

const statusOptions = [
  { value: "QUEUED", label: "排队中" },
  { value: "STARTING", label: "启动中" },
  { value: "RUNNING", label: "生成中" },
  { value: "SUCCEEDED", label: "已完成" },
  { value: "FAILED", label: "失败" },
  { value: "CANCELING", label: "正在取消" },
  { value: "CANCELED", label: "已取消" },
];

const hasFilter = computed(() => Boolean(statusFilter.value || typeFilter.value));

function typeChipClass(type: string): string {
  if (type === "I2V") return "i2v";
  if (type === "EXTEND") return "extend";
  if (type === "RETAKE") return "retake";
  return "t2v";
}

function isActive(status: TaskStatus): boolean {
  return ["QUEUED", "STARTING", "RUNNING", "CANCELING"].includes(status);
}

async function reload() {
  loading.value = true;
  try {
    const data = await fetchTasks({
      status: statusFilter.value || undefined,
      task_type: typeFilter.value || undefined,
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

function openTask(row: TaskSummary) {
  void router.push(`/tasks/${row.id}`);
}

async function onCancel(row: TaskSummary) {
  try {
    await ElMessageBox.confirm(
      "取消后任务会被终止，已生成的部分不会保留。确定取消吗？",
      "取消任务",
      { confirmButtonText: "取消任务", cancelButtonText: "再等等", type: "warning" },
    );
  } catch {
    return;
  }
  try {
    await cancelTask(row.id);
    ElMessage.success("已发送取消请求");
    await reload();
  } catch (err) {
    ElMessage.error(extractError(err).message);
  }
}

async function onDelete(row: TaskSummary) {
  try {
    await ElMessageBox.confirm(
      "删除任务记录，同时删除输出视频文件。此操作不可恢复，确定删除吗？",
      "删除任务",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "error" },
    );
  } catch {
    return;
  }
  try {
    await deleteTask(row.id, true);
    ElMessage.success("任务已删除");
    await reload();
  } catch (err) {
    ElMessage.error(extractError(err).message);
  }
}

let timer: number | null = null;

onMounted(() => {
  void reload();
  timer = window.setInterval(() => {
    if (tasks.value.some((task) => isActive(task.status))) void reload();
  }, 4000);
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
  flex-wrap: wrap;
}
.page-header h2 {
  margin: 0 0 4px;
  font-size: 20px;
}
.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.table-panel {
  padding: 6px 12px 12px;
}
.task-table {
  width: 100%;
  overflow-x: auto;
}
.task-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
}
.col-id {
  width: 84px;
  flex: none;
}
.col-type {
  width: 58px;
  flex: none;
}
.col-prompt {
  flex: 1;
  min-width: 90px;
}
.col-params {
  width: 118px;
  flex: none;
}
.col-status {
  width: 98px;
  flex: none;
}
.col-time {
  width: 112px;
  flex: none;
}
.col-actions {
  width: 96px;
  flex: none;
  display: flex;
  justify-content: flex-end;
  gap: 2px;
}

@media (max-width: 1180px) {
  .col-params {
    display: none;
  }
  .col-time {
    width: 104px;
  }
}

@media (max-width: 980px) {
  .col-id {
    display: none;
  }
  .col-type {
    width: 50px;
  }
  .col-status {
    width: 92px;
  }
  .col-actions {
    width: 88px;
  }
  .col-time {
    width: 96px;
  }
  .task-row {
    gap: 6px;
  }
}
.task-head {
  font-size: 12px;
  color: var(--text-faint);
  border-bottom: 1px solid var(--border);
  padding-top: 8px;
  padding-bottom: 8px;
}
.task-body {
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.12s;
}
.task-body:last-child {
  border-bottom: none;
}
.task-body:hover {
  background: var(--bg-panel-soft);
}
.col-id code {
  font-size: 11.5px;
  color: var(--text-dim);
}
.prompt-cell {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}
.col-actions :deep(.el-button) {
  padding: 2px 4px;
  margin-left: 0;
}
.type-chip {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 4px;
  font-family: var(--mono);
}
.type-chip.t2v {
  color: #7fb1ff;
  background: rgba(76, 141, 255, 0.14);
}
.type-chip.i2v {
  color: #c4a3ff;
  background: rgba(139, 92, 246, 0.16);
}
.type-chip.extend {
  color: #6fd6a8;
  background: rgba(63, 185, 80, 0.16);
}
.type-chip.retake {
  color: #f0b849;
  background: rgba(210, 153, 34, 0.18);
}
.small {
  font-size: 11.5px;
  color: var(--text-dim);
}
.tiny {
  font-size: 10.5px;
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
  padding-top: 10px;
}
</style>
