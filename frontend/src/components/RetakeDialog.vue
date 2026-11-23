<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="720px"
    :close-on-click-modal="false"
    @opened="onOpened"
    @closed="onClosed"
  >
    <div v-if="loading" class="loading-box">
      <el-skeleton :rows="5" animated />
    </div>

    <el-alert
      v-else-if="loadError"
      type="error"
      :closable="false"
      show-icon
      :title="loadError"
    />

    <div v-else-if="source" class="retake-body">
      <div class="player-wrap">
        <video
          ref="videoRef"
          :src="source.video_url"
          controls
          preload="metadata"
          playsinline
        ></video>
      </div>

      <div class="range-panel">
        <div class="range-head">
          <span class="label">要改哪一段？</span>
          <span class="hint">
            共 {{ source.source_duration.toFixed(2) }} 秒 ·
            {{ source.source_frames }} 帧 ·
            {{ source.width }}×{{ source.height }}
          </span>
        </div>

        <div class="time-inputs">
          <div class="time-field">
            <span class="hint">开始</span>
            <el-input-number
              v-model="startSeconds"
              :min="0"
              :max="maxStart"
              :step="oneLatentSeconds"
              :precision="2"
              size="small"
              controls-position="right"
              @change="onStartChanged"
            />
            <span class="hint mono">秒</span>
          </div>
          <div class="time-field">
            <span class="hint">结束</span>
            <el-input-number
              v-model="endSeconds"
              :min="oneLatentSeconds"
              :max="source.source_duration"
              :step="oneLatentSeconds"
              :precision="2"
              size="small"
              controls-position="right"
              @change="onEndChanged"
            />
            <span class="hint mono">秒</span>
          </div>
          <div class="range-duration">
            <span class="hint">重拍</span>
            <strong>{{ rangeDuration.toFixed(2) }} 秒</strong>
            <span class="hint mono">（{{ latentSpan }} latent 帧）</span>
          </div>
        </div>

        <div class="slider-wrap">
          <el-slider
            v-model="sliderRange"
            range
            :min="0"
            :max="sliderMax"
            :step="1"
            :marks="marks"
            :disabled="!source"
            @change="onSliderChange"
          />
        </div>

        <div class="step-hint">
          <el-icon><InfoFilled /></el-icon>
          <span>
            重拍以 8 帧（1 个 latent 帧）为最小单位，
            具体边界会自动对齐到最近的整格。
          </span>
        </div>
      </div>

      <div class="prompt-panel">
        <label class="label">这一段要改成什么？</label>
        <el-input
          v-model="prompt"
          type="textarea"
          :rows="3"
          :maxlength="4000"
          show-word-limit
          resize="vertical"
          placeholder="例如：这一段改成下雨天，人物撑一把黑伞，其余保持现状"
          :disabled="submitting"
        />
        <div class="options">
          <label class="check">
            <el-checkbox v-model="keepAudio" />
            <span>保留原音轨（不重新生成声音）</span>
          </label>
          <label v-if="appendOptionAvailable" class="check">
            <el-checkbox v-model="appendProjectPrompt" />
            <span>附带项目设定</span>
          </label>
        </div>
      </div>

      <div v-if="finalPromptPreview" class="preview">
        <div class="hint">实际传给 CLI 的 Prompt：</div>
        <pre>{{ finalPromptPreview }}</pre>
      </div>

      <el-alert
        v-if="submitError"
        type="error"
        :closable="true"
        show-icon
        :title="submitError"
        @close="submitError = null"
      />

      <el-alert
        v-if="successInfo"
        type="success"
        :closable="false"
        show-icon
        :title="successInfo"
      />

      <div class="dialog-footer">
        <el-button @click="visible = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="!canSubmit"
          @click="onSubmit"
        >
          {{ submitting ? "提交中..." : "开始重拍" }}
        </el-button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  fetchSegmentRetakeSource,
  fetchTaskRetakeSource,
  submitSegmentRetake,
  submitTaskRetake,
  type RetakeSourceInfo,
} from "@/api/retake";
import { extractError } from "@/api/http";

const props = defineProps<{
  modelValue: boolean;
  /** 二选一：单条任务或项目版本 */
  taskId?: string | null;
  projectId?: string | null;
  segmentId?: string | null;
  segmentLabel?: string;
  appendOptionAvailable?: boolean;
}>();

const emit = defineEmits<{
  (event: "update:modelValue", value: boolean): void;
  (event: "submitted", taskId: string): void;
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value),
});

const source = ref<RetakeSourceInfo | null>(null);
const loading = ref(false);
const loadError = ref<string | null>(null);

const videoRef = ref<HTMLVideoElement | null>(null);
const prompt = ref("");
const keepAudio = ref(false);
const appendProjectPrompt = ref(true);
const submitting = ref(false);
const submitError = ref<string | null>(null);
const successInfo = ref<string | null>(null);
const finalPromptPreview = ref<string | null>(null);

// 以 latent 为最小单位：滑块 0..total_latent
const startLatent = ref(0);
const endLatent = ref(1);

const isSegment = computed(() => Boolean(props.segmentId));

const dialogTitle = computed(() =>
  isSegment.value
    ? `局部重拍 · ${props.segmentLabel ?? "当前版本"}`
    : "局部重拍 · 改写这个视频的一段",
);

const oneLatentSeconds = computed(() => {
  const fps = source.value?.fps ?? 24;
  return Number((8 / (fps > 0 ? fps : 24)).toFixed(3));
});

const sliderMax = computed(() => source.value?.total_latent ?? 1);
const sliderRange = computed({
  get: () => [startLatent.value, endLatent.value],
  set: (value: number[] | number) => {
    if (Array.isArray(value)) {
      startLatent.value = value[0];
      endLatent.value = value[1];
    }
  },
});

const latentSpan = computed(() => Math.max(1, endLatent.value - startLatent.value));

const startSeconds = computed({
  get: () =>
    Number(((startLatent.value * 8) / (source.value?.fps ?? 24)).toFixed(2)),
  set: (value: number) => {
    const fps = source.value?.fps ?? 24;
    startLatent.value = Math.max(0, Math.floor((value * fps) / 8));
  },
});

const endSeconds = computed({
  get: () =>
    Number(((endLatent.value * 8) / (source.value?.fps ?? 24)).toFixed(2)),
  set: (value: number) => {
    const fps = source.value?.fps ?? 24;
    endLatent.value = Math.min(
      sliderMax.value,
      Math.max(startLatent.value + 1, Math.ceil((value * fps) / 8)),
    );
  },
});

const maxStart = computed(() => Math.max(0, (source.value?.source_duration ?? 0) - 0.01));

const rangeDuration = computed(() =>
  Number((latentSpan.value * 8 / (source.value?.fps ?? 24)).toFixed(2)),
);

const marks = computed(() => {
  const total = sliderMax.value;
  if (total <= 6) {
    const result: Record<number, string> = {};
    for (let i = 0; i <= total; i += 1) {
      result[i] = `${((i * 8) / (source.value?.fps ?? 24)).toFixed(2)}s`;
    }
    return result;
  }
  const result: Record<number, string> = {};
  for (let i = 0; i <= total; i += Math.ceil(total / 5)) {
    result[i] = `${((i * 8) / (source.value?.fps ?? 24)).toFixed(1)}s`;
  }
  return result;
});

const canSubmit = computed(
  () =>
    Boolean(source.value) &&
    prompt.value.trim().length > 0 &&
    endLatent.value > startLatent.value &&
    !submitting.value,
);

function onStartChanged() {
  if (startLatent.value >= endLatent.value) {
    endLatent.value = Math.min(sliderMax.value, startLatent.value + 1);
  }
}

function onEndChanged() {
  if (endLatent.value <= startLatent.value) {
    startLatent.value = Math.max(0, endLatent.value - 1);
  }
}

function onSliderChange(value: number[]) {
  startLatent.value = value[0];
  endLatent.value = value[1];
}

async function onOpened() {
  loadError.value = null;
  submitError.value = null;
  successInfo.value = null;
  finalPromptPreview.value = null;
  prompt.value = "";
  keepAudio.value = false;
  source.value = null;
  loading.value = true;

  try {
    let info: RetakeSourceInfo | null = null;
    if (props.segmentId) {
      info = await fetchSegmentRetakeSource(props.segmentId);
    } else if (props.taskId) {
      info = await fetchTaskRetakeSource(props.taskId);
    }
    if (!info) {
      throw new Error("缺少重拍来源");
    }
    if (info.total_latent < 1) {
      throw new Error("该视频太短，无法定位重拍区间");
    }
    source.value = info;
    startLatent.value = 0;
    endLatent.value = 1;
  } catch (err) {
    loadError.value = extractError(err).message;
  } finally {
    loading.value = false;
  }
}

function onClosed() {
  source.value = null;
  finalPromptPreview.value = null;
  submitError.value = null;
}

async function onSubmit() {
  if (!source.value) return;
  if (endLatent.value > sliderMax.value) {
    submitError.value = "结束时间超出视频长度";
    return;
  }
  if (!prompt.value.trim()) {
    submitError.value = "请描述这一段要改成什么";
    return;
  }

  submitting.value = true;
  submitError.value = null;
  successInfo.value = null;
  try {
    const payload = {
      prompt: prompt.value.trim(),
      startLatent: startLatent.value,
      endLatent: endLatent.value,
      keepAudio: keepAudio.value,
      seed: null,
    };

    const result =
      props.segmentId && props.projectId
        ? await submitSegmentRetake(
            props.projectId,
            props.segmentId,
            payload,
            appendProjectPrompt.value,
          )
        : await submitTaskRetake(props.taskId!, payload);

    finalPromptPreview.value = result.final_prompt;
    successInfo.value = result.message;
    ElMessage.success(result.message);
    emit("submitted", result.task_id);
    // 保留对话框，让用户能看到实际 Prompt；用户可自行关闭
  } catch (err) {
    submitError.value = extractError(err).message;
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.loading-box {
  padding: 8px 0;
}
.retake-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.player-wrap {
  background: #000;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  overflow: hidden;
  display: flex;
  justify-content: center;
}
.player-wrap video {
  width: 100%;
  max-height: 300px;
  display: block;
  object-fit: contain;
}
.range-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.range-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.label {
  font-size: 13px;
  font-weight: 500;
}
.time-inputs {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
}
.time-field {
  display: flex;
  align-items: center;
  gap: 6px;
}
.time-field :deep(.el-input-number) {
  width: 110px;
}
.range-duration {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
}
.range-duration strong {
  color: var(--accent);
}
.slider-wrap {
  padding: 0 10px 18px;
}
.step-hint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 11.5px;
  color: var(--text-faint);
  line-height: 1.6;
}
.prompt-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.options {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}
.check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-dim);
}
.preview {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.preview pre {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--text-dim);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 160px;
  overflow: auto;
}
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.mono {
  font-family: var(--mono);
}
</style>
