<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>新建生成</h2>
        <p class="hint">输入提示词或上传参考图片，由本机 MLX 完成推理</p>
      </div>
    </div>

    <el-alert
      v-if="!system.ready && system.health"
      type="error"
      :closable="false"
      show-icon
      class="ready-alert"
    >
      <template #title>当前环境未就绪，暂时无法提交生成任务</template>
      <div class="alert-body">
        <div v-for="reason in system.blockingReasons" :key="reason">
          · {{ reason }}
        </div>
        <router-link to="/settings" class="alert-link">前往模型与环境检查 →</router-link>
      </div>
    </el-alert>

    <el-alert
      v-else-if="!system.health && system.error"
      type="warning"
      :closable="false"
      show-icon
      :title="system.error"
    />

    <div class="layout-grid">
      <section class="panel main-panel">
        <div class="mode-tabs">
          <button
            type="button"
            class="mode-tab"
            :class="{ active: generation.taskType === 'T2V' }"
            @click="generation.setTaskType('T2V')"
          >
            <el-icon><EditPen /></el-icon>
            文字生成
          </button>
          <button
            type="button"
            class="mode-tab"
            :class="{ active: generation.taskType === 'I2V' }"
            @click="generation.setTaskType('I2V')"
          >
            <el-icon><Picture /></el-icon>
            图片生成
          </button>
        </div>

        <PromptEditor
          v-model="generation.prompt"
          :max-length="maxPromptLength"
          :error="generation.errorFor('prompt')"
        />

        <div v-if="generation.taskType === 'I2V'" class="section">
          <div class="section-label">参考图片</div>
          <ImageUploader
            :file="generation.imageFile"
            :preview-url="generation.imagePreviewUrl"
            :meta="generation.imageMeta"
            :max-mb="settings?.max_upload_mb ?? 15"
            :error="generation.errorFor('image')"
            @change="onImageChange"
          />
        </div>

        <div class="section">
          <div class="section-label">生成设置</div>
          <GenerationSettings
            v-model:width="generation.width"
            v-model:height="generation.height"
            v-model:frames="generation.frames"
            v-model:frame-rate="generation.frameRate"
            v-model:mode="generation.mode"
            v-model:seed-input="generation.seedInput"
            v-model:random-seed="generation.randomSeed"
            :low-ram="lowRam"
            :low-ram-available="true"
            :allowed-resolutions="settings?.allowed_resolutions ?? []"
            :allowed-frames="settings?.allowed_frames ?? []"
            :allowed-frame-rates="settings?.allowed_frame_rates ?? []"
            :frames-error="generation.errorFor('frames')"
            :seed-error="generation.errorFor('seed')"
          />
        </div>

        <div class="submit-row">
          <el-button
            type="primary"
            size="large"
            :loading="generation.submitting"
            :disabled="!canSubmit"
            @click="onSubmit"
          >
            {{ generation.submitting ? "提交中..." : "开始生成" }}
          </el-button>
          <span class="hint">
            默认 {{ generation.width }}×{{ generation.height }} ·
            {{ generation.frames }} 帧 · {{ generation.frameRate }} FPS
          </span>
        </div>

        <el-alert
          v-if="generation.submitError"
          type="error"
          :closable="true"
          show-icon
          class="submit-alert"
          :title="generation.submitError"
          @close="generation.submitError = null"
        />

        <el-alert
          v-else-if="generation.lastTaskId && generation.lastMessage"
          type="success"
          :closable="true"
          show-icon
          class="submit-alert"
          :title="generation.lastMessage"
          @close="generation.lastMessage = null"
        >
          <div class="alert-body">
            任务编号 <code>{{ generation.lastTaskId }}</code>
            <router-link :to="`/tasks/${generation.lastTaskId}`" class="alert-link">
              查看详情 →
            </router-link>
          </div>
        </el-alert>
      </section>

      <aside class="side-column">
        <section class="panel side-panel">
          <h3 class="panel-title">当前队列</h3>
          <div class="queue-state">
            <span class="dot" :class="system.health?.queue_running ? 'warn' : 'idle'"></span>
            <span>{{ system.health?.queue_running ? "正在推理" : "队列空闲" }}</span>
          </div>
          <div class="kv">
            <span>等待任务</span><code>{{ system.health?.queue_size ?? 0 }}</code>
          </div>
          <div class="kv">
            <span>队列上限</span><code>{{ system.health?.max_queue_size ?? 10 }}</code>
          </div>
          <div class="kv">
            <span>单任务串行</span><code>是</code>
          </div>
          <p class="hint small-note">
            24GB 统一内存下只允许一个推理进程，避免内存压力导致失败。
          </p>
        </section>

        <section class="panel side-panel">
          <h3 class="panel-title">最近任务</h3>
          <div v-if="generation.recentTasks.length === 0" class="hint">
            还没有任务，提交第一个生成吧。
          </div>
          <router-link
            v-for="task in generation.recentTasks"
            :key="task.id"
            :to="`/tasks/${task.id}`"
            class="recent-item"
          >
            <div class="recent-top">
              <TaskStatusTag :status="task.status" />
              <span class="hint mono">{{ task.id.slice(0, 8) }}</span>
            </div>
            <div class="recent-prompt">{{ task.prompt_excerpt }}</div>
            <div class="hint">
              {{ task.width }}×{{ task.height }} · {{ task.frames }} 帧 ·
              {{ task.task_type }}
            </div>
          </router-link>
          <router-link to="/tasks" class="all-link">查看全部任务 →</router-link>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import PromptEditor from "@/components/PromptEditor.vue";
import ImageUploader from "@/components/ImageUploader.vue";
import GenerationSettings from "@/components/GenerationSettings.vue";
import TaskStatusTag from "@/components/TaskStatusTag.vue";
import { useGenerationStore } from "@/stores/generation";
import { useSystemStore } from "@/stores/system";

const generation = useGenerationStore();
const system = useSystemStore();
const router = useRouter();

const settings = computed(() => system.settings);
const maxPromptLength = computed(() => settings.value?.max_prompt_length ?? 4000);
const lowRam = ref(false);

const canSubmit = computed(
  () => system.ready && !generation.submitting,
);

watch(
  () => settings.value,
  (value) => {
    if (!value) return;
    lowRam.value = value.low_ram;
    if (!generation.prompt && !generation.lastTaskId) {
      generation.applyDefaults({
        width: value.default_width,
        height: value.default_height,
        frames: value.default_frames,
        frame_rate: value.default_frame_rate,
      });
    }
  },
  { immediate: true },
);

watch(
  () => generation.width,
  (value) => {
    // 横竖屏预设切换时保持合法组合
    if (!settings.value) return;
    const allowed = settings.value.allowed_resolutions;
    if (allowed.length && !allowed.some(([w]) => w === value)) {
      generation.width = allowed[0][0];
      generation.height = allowed[0][1];
    }
  },
);

function onImageChange(
  file: File | null,
  meta?: { width: number; height: number },
) {
  generation.setImage(file, meta);
}

async function onSubmit() {
  if (!system.ready) {
    ElMessage.error("环境未就绪，请先到「模型与环境」检查");
    return;
  }
  const taskId = await generation.submit(maxPromptLength.value);
  if (taskId) {
    ElMessage.success("任务已加入队列");
    await Promise.all([system.refreshHealth(), generation.loadRecent()]);
    void router.push(`/tasks/${taskId}`);
  } else if (generation.errors.length > 0) {
    ElMessage.error(generation.errors[0].message);
  }
}

onMounted(() => {
  if (!system.lastCheckedAt) void system.refreshAll();
  void generation.loadRecent();
});
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1280px;
}
.page-header h2 {
  margin: 0 0 4px;
  font-size: 20px;
}
.ready-alert {
  margin: 0;
}
.alert-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  line-height: 1.7;
}
.alert-link {
  font-size: 12px;
  margin-top: 4px;
}

.layout-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 16px;
  align-items: start;
}

@media (max-width: 1080px) {
  .layout-grid {
    grid-template-columns: 1fr;
  }
}

.main-panel {
  padding: 18px 20px 22px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.mode-tabs {
  display: flex;
  gap: 8px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  padding: 4px;
  border-radius: 9px;
  width: fit-content;
}
.mode-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-dim);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.mode-tab.active {
  background: var(--accent);
  color: #fff;
  font-weight: 500;
}

.section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.section-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-dim);
}

.submit-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.submit-alert {
  margin: 0;
}

.side-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.side-panel {
  padding: 16px;
}

.queue-state {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 12px;
}

.kv {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-dim);
  padding: 4px 0;
}
.kv code {
  color: var(--text);
}

.small-note {
  margin: 10px 0 0;
}

.recent-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  transition: all 0.15s;
}
.recent-item:hover {
  border-color: var(--border);
  background: var(--bg-panel-soft);
}
.recent-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.recent-prompt {
  font-size: 12.5px;
  color: var(--text);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.all-link {
  display: inline-block;
  margin-top: 10px;
  font-size: 12px;
}
</style>
