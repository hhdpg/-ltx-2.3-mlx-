<template>
  <div class="page">
    <el-alert v-if="loadError" type="error" :closable="false" show-icon :title="loadError" />

    <template v-else-if="project">
      <div class="page-header">
        <div>
          <router-link to="/projects" class="back-link">← 返回连续创作</router-link>
          <h2>{{ project.name }}</h2>
          <p class="hint mono">{{ project.id }}</p>
        </div>
        <div class="header-actions">
          <el-button size="small" @click="settingsVisible = true">项目设定</el-button>
          <el-button size="small" type="danger" plain @click="onDeleteProject">
            删除项目
          </el-button>
        </div>
      </div>

      <div class="layout-grid">
        <section class="panel main-panel">
          <!-- 空项目：先创建首段视频 -->
          <div v-if="segments.length === 0" class="block first-block">
            <div class="block-head">
              <h3 class="block-title">先创建第一段视频</h3>
              <span class="hint">续写需要一段已有视频作为源，生成成功后自动成为第 1 段</span>
            </div>

            <el-alert type="info" :closable="false" show-icon>
              <template #title>这个项目还没有任何视频版本</template>
              <div class="first-hint">
                可以直接在这里生成第一段（自动加入本项目），
                也可以在「任务历史 / 视频作品」里对已成功的视频点击「继续创作」。
              </div>
            </el-alert>

            <div class="mode-tabs">
              <button
                type="button"
                class="mode-tab"
                :class="{ active: firstForm.taskType === 'T2V' }"
                @click="firstForm.taskType = 'T2V'"
              >
                文字生成
              </button>
              <button
                type="button"
                class="mode-tab"
                :class="{ active: firstForm.taskType === 'I2V' }"
                @click="firstForm.taskType = 'I2V'"
              >
                图片生成
              </button>
            </div>

            <div class="field">
              <label>提示词</label>
              <el-input
                v-model="firstForm.prompt"
                type="textarea"
                :rows="4"
                :maxlength="4000"
                show-word-limit
                resize="vertical"
                placeholder="描述第一段视频的画面、人物与动作"
                :disabled="firstSubmitting"
              />
            </div>

            <div v-if="firstForm.taskType === 'I2V'" class="field">
              <label>参考图片</label>
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                @change="onFirstImage"
              />
              <div v-if="firstImageName" class="hint">已选择：{{ firstImageName }}</div>
            </div>

            <div class="first-grid">
              <div class="field">
                <label>分辨率</label>
                <el-select v-model="firstForm.resolution" style="width: 100%">
                  <el-option
                    v-for="preset in resolutionOptions"
                    :key="preset.key"
                    :label="preset.label"
                    :value="preset.key"
                  />
                </el-select>
              </div>
              <div class="field">
                <label>帧数</label>
                <el-select v-model="firstForm.frames" style="width: 100%">
                  <el-option
                    v-for="value in allowedFrames"
                    :key="value"
                    :label="`${value} 帧 · ${(value / 24).toFixed(2)}s`"
                    :value="value"
                  />
                </el-select>
              </div>
            </div>

            <el-alert
              v-if="firstError"
              type="error"
              :closable="true"
              show-icon
              :title="firstError"
              @close="firstError = null"
            />

            <div class="submit-row">
              <el-button
                type="primary"
                size="large"
                :loading="firstSubmitting"
                :disabled="!canCreateFirst"
                @click="onCreateFirst"
              >
                {{ firstSubmitting ? "提交中..." : "生成第一段" }}
              </el-button>
              <span class="hint">默认 512×320 · 25 帧 · 24 FPS · Distilled</span>
            </div>
          </div>

          <template v-else>
          <!-- 源视频 -->
          <div class="block">
            <div class="block-head">
              <h3 class="block-title">当前源视频</h3>
              <span class="hint" v-if="sourceSegment">
                第 {{ sourceSegment.segment_index }} 段 ·
                {{ sourceSegment.width }}x{{ sourceSegment.height }} ·
                {{ (sourceSegment.duration_seconds ?? 0).toFixed(2) }}s ·
                {{ (sourceSegment.frame_rate ?? 24).toFixed(0) }}fps
              </span>
            </div>
            <div v-if="sourceSegment && sourceSegment.video_ready" class="player-shell">
              <video
                :key="sourceSegment.id"
                :src="segmentVideoUrl(sourceSegment.id)"
                controls
                preload="metadata"
                playsinline
              ></video>
            </div>
            <el-empty v-else description="该版本视频不可用" :image-size="80" />

            <div class="source-meta">
              <div class="kv"><span>用户原始 Prompt</span></div>
              <p class="prompt-text">{{ sourceSegment?.prompt }}</p>
              <template v-if="sourceSegment?.final_prompt && sourceSegment.final_prompt !== sourceSegment.prompt">
                <div class="kv"><span>实际传给 CLI 的 Prompt</span></div>
                <pre class="final-prompt">{{ sourceSegment.final_prompt }}</pre>
              </template>
            </div>
            <div class="source-switch">
              <span class="hint">切换源版本：</span>
              <el-select
                :model-value="sourceSegmentId"
                size="small"
                style="width: 320px"
                @update:model-value="onSwitchSource"
              >
                <el-option
                  v-for="segment in segments"
                  :key="segment.id"
                  :label="segmentLabel(segment)"
                  :value="segment.id"
                  :disabled="!segment.video_ready"
                />
              </el-select>
            </div>
          </div>

          <!-- 续写表单 -->
          <div class="block">
            <div class="block-head">
              <h3 class="block-title">接下来发生什么？</h3>
              <span class="hint">只写下一步动作，画面上下文由源视频提供</span>
            </div>

            <el-input
              v-model="form.prompt"
              type="textarea"
              :rows="4"
              :maxlength="4000"
              show-word-limit
              resize="vertical"
              placeholder="例如：人物继续沿着海边向前走，随后停下来望向海平面，镜头缓慢跟随。"
              :disabled="submitting"
            />

            <ExtendLengthSelector
              v-model="form.extendFrames"
              :fps="sourceSegment?.frame_rate ?? 24"
              :allowed="allowedExtendFrames"
            />

            <div class="options-row">
              <div class="opt-item">
                <span class="hint">附带项目设定</span>
                <el-switch v-model="form.appendProjectPrompt" />
              </div>
              <div class="opt-item">
                <span class="hint">随机种子</span>
                <el-switch
                  v-model="randomSeed"
                  active-text="随机"
                  inactive-text="固定"
                  inline-prompt
                  style="margin-left: 6px"
                />
                <el-input
                  v-if="!randomSeed"
                  v-model="seedInput"
                  size="small"
                  placeholder="如 12345"
                  style="width: 120px; margin-left: 8px"
                />
              </div>
              <el-button size="small" text @click="previewVisible = !previewVisible">
                {{ previewVisible ? "隐藏最终 Prompt" : "查看最终 Prompt" }}
              </el-button>
            </div>

            <div v-if="previewVisible" class="preview-box">
              <el-button size="small" :loading="previewing" @click="doPreview">
                生成预览
              </el-button>
              <pre v-if="finalPromptPreview" class="final-prompt">{{ finalPromptPreview }}</pre>
              <p v-else class="hint">点击“生成预览”查看实际传给 CLI 的完整 Prompt。</p>
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
              v-if="lastResult"
              type="success"
              :closable="true"
              show-icon
              :title="lastResult.message"
              @close="lastResult = null"
            >
              <div class="result-lines">
                <span>新增约 {{ lastResult.estimated_added_seconds }} 秒（{{ lastResult.estimated_added_frames }} 帧）</span>
                <router-link :to="`/tasks/${lastResult.task_id}`" class="link">
                  查看任务与日志 →
                </router-link>
              </div>
            </el-alert>

            <div class="submit-row">
              <el-button
                type="primary"
                size="large"
                :loading="submitting"
                :disabled="submitting || !sourceSegment || !sourceSegment.video_ready"
                @click="onSubmit"
              >
                {{ submitting ? "提交中..." : "开始续写" }}
              </el-button>
              <el-alert
                v-if="!sourceSegment || !sourceSegment.video_ready"
                type="warning"
                :closable="false"
                show-icon
                :title="noSourceHint"
                class="inline-alert"
              />
              <span v-else-if="!form.prompt.trim()" class="hint empty-hint">
                ↑ 先在「接下来发生什么？」里写下一步动作
              </span>
              <span v-else class="hint">
                单任务队列 · 同一时间只允许一个推理进程
              </span>
            </div>
          </div>

          <div class="block">
            <SegmentTimeline
              :items="segments"
              :children="childrenMap"
              :current-segment-id="project.current_segment_id"
              @extend="onExtendSegment"
              @retake="onRetakeSegment"
              @set-current="onSetCurrent"
              @command="onTimelineCommand"
            />
          </div>
          </template>
        </section>

        <aside class="side-column">
          <section class="panel side-panel">
            <h3 class="panel-title">项目设定</h3>
            <div class="kv-block">
              <span class="k">角色</span>
              <span class="v">{{ project.character_setting || "未设置" }}</span>
            </div>
            <div class="kv-block">
              <span class="k">场景</span>
              <span class="v">{{ project.scene_setting || "未设置" }}</span>
            </div>
            <div class="kv-block">
              <span class="k">风格</span>
              <span class="v">{{ project.style_setting || "未设置" }}</span>
            </div>
            <div class="kv-block">
              <span class="k">连续性</span>
              <span class="v">{{ project.continuity_rules || "未设置" }}</span>
            </div>
            <div class="kv-block">
              <span class="k">附带设定</span>
              <span class="v">{{ project.append_project_prompt ? "开启" : "关闭" }}</span>
            </div>
          </section>

          <section class="panel side-panel">
            <h3 class="panel-title">剧情摘要</h3>
            <el-input
              v-model="storySummary"
              type="textarea"
              :rows="5"
              placeholder="记录当前剧情走向，仅作备忘，不会作为视觉条件提交"
            />
            <el-button
              size="small"
              style="margin-top: 8px"
              :loading="savingSummary"
              @click="saveSummary"
            >
              保存摘要
            </el-button>
          </section>

          <section class="panel side-panel">
            <h3 class="panel-title">添加到项目</h3>
            <p class="hint">
              把已完成的 T2V / I2V 视频作为新版本加入本项目。
            </p>
            <el-select
              v-model="attachTaskId"
              placeholder="选择已完成的任务"
              style="width: 100%"
              :loading="loadingTasks"
              filterable
            >
              <el-option
                v-for="task in attachableTasks"
                :key="task.id"
                :label="`${task.id.slice(0, 8)} · ${task.prompt_excerpt}`"
                :value="task.id"
              />
            </el-select>
            <el-button
              size="small"
              type="primary"
              style="margin-top: 8px"
              :disabled="!attachTaskId"
              :loading="attaching"
              @click="onAttach"
            >
              加入项目
            </el-button>
          </section>
        </aside>
      </div>
    </template>

    <div v-else-if="loading" class="panel loading-panel">
      <el-skeleton :rows="6" animated />
    </div>

    <el-dialog v-model="settingsVisible" title="项目设定" width="600px">
      <el-form label-width="96px">
        <el-form-item label="项目名称">
          <el-input v-model="settingsForm.name" maxlength="200" />
        </el-form-item>
        <el-form-item label="角色设定">
          <el-input v-model="settingsForm.character_setting" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="场景设定">
          <el-input v-model="settingsForm.scene_setting" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="视觉风格">
          <el-input v-model="settingsForm.style_setting" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="连续性要求">
          <el-input v-model="settingsForm.continuity_rules" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="附带设定">
          <el-switch v-model="settingsForm.append_project_prompt" />
          <span class="hint form-hint">仅影响之后的续写任务，不回写历史</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="settingsVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingSettings" @click="saveSettings">
          保存
        </el-button>
      </template>
    </el-dialog>

    <RetakeDialog
      v-model="retakeVisible"
      :project-id="projectId"
      :segment-id="retakeSegment?.id ?? null"
      :segment-label="retakeSegment ? `第 ${retakeSegment.segment_index} 段` : undefined"
      :append-option-available="true"
      @submitted="onRetakeSubmitted"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import SegmentTimeline from "@/components/SegmentTimeline.vue";
import RetakeDialog from "@/components/RetakeDialog.vue";
import ExtendLengthSelector from "@/components/ExtendLengthSelector.vue";
import {
  attachSegment,
  deleteProject,
  deleteSegment,
  fetchProject,
  fetchSegments,
  previewPrompt,
  segmentVideoUrl,
  setCurrentSegment,
  submitExtend,
  updateProject,
} from "@/api/project";
import { fetchTasks } from "@/api/task";
import { submitGeneration } from "@/api/generation";
import { extractError } from "@/api/http";
import { useSystemStore } from "@/stores/system";
import type {
  ExtendResponse,
  GenerationProjectDetail,
  GenerationSegment,
  TaskSummary,
} from "@/types";

const route = useRoute();
const router = useRouter();
const system = useSystemStore();

const projectId = computed(() => String(route.params.id));
const project = ref<GenerationProjectDetail | null>(null);
const segments = ref<GenerationSegment[]>([]);
const childrenMap = ref<Record<string, string[]>>({});
const loading = ref(false);
const loadError = ref<string | null>(null);

const sourceSegmentId = ref<string | null>(null);
const sourceSegment = computed(() =>
  segments.value.find((item) => item.id === sourceSegmentId.value) ?? null,
);

const form = reactive({
  prompt: "",
  extendFrames: 4,
  appendProjectPrompt: true,
});
const randomSeed = ref(true);
const seedInput = ref("");
const previewVisible = ref(false);
const finalPromptPreview = ref<string | null>(null);
const previewing = ref(false);
const submitting = ref(false);
const submitError = ref<string | null>(null);
const lastResult = ref<ExtendResponse | null>(null);

const allowedExtendFrames = computed(() => {
  const configured = system.settings?.allowed_extend_frames ?? [];
  return configured.length ? configured : [1, 2, 4, 8];
});

const attachTaskId = ref<string | null>(null);
const attachableTasks = ref<TaskSummary[]>([]);
const loadingTasks = ref(false);
const attaching = ref(false);

const storySummary = ref("");
const savingSummary = ref(false);

const settingsVisible = ref(false);
const savingSettings = ref(false);
const settingsForm = reactive({
  name: "",
  character_setting: "",
  scene_setting: "",
  style_setting: "",
  continuity_rules: "",
  append_project_prompt: true,
});

const noSourceHint = computed(() => {
  if (segments.value.length === 0) {
    return "还没有源视频：请先在上方「生成第一段」，或在「添加到项目」里选择一个已完成的视频";
  }
  if (!sourceSegment.value) {
    return "请在上方「切换源版本」里选择一个视频版本";
  }
  return "该版本的视频文件不可用（可能已被删除），请切换到其他版本";
});

// ---------- 空项目：生成第一段 ----------
const firstForm = reactive({
  taskType: "T2V" as "T2V" | "I2V",
  prompt: "",
  resolution: "512x320",
  frames: 25,
});
const firstImage = ref<File | null>(null);
const firstImageName = ref<string | null>(null);
const firstSubmitting = ref(false);
const firstError = ref<string | null>(null);

const resolutionOptions = computed(() => {
  const pairs = system.settings?.allowed_resolutions ?? [
    [512, 320],
    [320, 512],
  ];
  return pairs.map(([w, h]) => ({ key: `${w}x${h}`, label: `${w} × ${h}`, w, h }));
});

const allowedFrames = computed(() => system.settings?.allowed_frames ?? [9, 25, 41, 49]);

const canCreateFirst = computed(
  () =>
    firstForm.prompt.trim().length > 0 &&
    !firstSubmitting.value &&
    (firstForm.taskType !== "I2V" || Boolean(firstImage.value)),
);

function onFirstImage(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0] ?? null;
  firstImage.value = file;
  firstImageName.value = file?.name ?? null;
}

async function onCreateFirst() {
  if (!canCreateFirst.value) return;
  const preset = resolutionOptions.value.find((p) => p.key === firstForm.resolution);
  if (!preset) {
    firstError.value = "请选择分辨率";
    return;
  }
  if (firstForm.taskType === "I2V" && !firstImage.value) {
    firstError.value = "图片生成模式必须上传参考图片";
    return;
  }

  firstError.value = null;
  firstSubmitting.value = true;
  try {
    const result = await submitGeneration(
      {
        task_type: firstForm.taskType,
        prompt: firstForm.prompt.trim(),
        width: preset.w,
        height: preset.h,
        frames: firstForm.frames,
        frame_rate: 24,
        mode: "distilled",
        seed: null,
        image: firstForm.taskType === "I2V" ? firstImage.value : null,
        projectId: projectId.value,
      },
      undefined,
    );
    ElMessage.success("第一段已加入队列，完成后自动成为第 1 段");
    startWatch(result.task_id);
    firstForm.prompt = "";
    firstImage.value = null;
    firstImageName.value = null;
  } catch (err) {
    firstError.value = extractError(err).message;
  } finally {
    firstSubmitting.value = false;
  }
}

function segmentLabel(segment: GenerationSegment): string {
  const suffix = segment.task_type === "EXTEND" ? "续写" : "初始";
  const dur = (segment.duration_seconds ?? 0).toFixed(2);
  return `第 ${segment.segment_index} 段（${suffix} · ${dur}s）`;
}

async function load(showError = true) {
  try {
    const [detail, segData] = await Promise.all([
      fetchProject(projectId.value),
      fetchSegments(projectId.value),
    ]);
    project.value = detail;
    segments.value = segData.items;
    childrenMap.value = segData.children;

    storySummary.value = detail.story_summary ?? "";
    if (form.appendProjectPrompt !== detail.append_project_prompt) {
      form.appendProjectPrompt = detail.append_project_prompt;
    }

    if (!sourceSegmentId.value) {
      sourceSegmentId.value = segData.current_segment_id ?? segData.items[0]?.id ?? null;
    } else if (!segData.items.some((item) => item.id === sourceSegmentId.value)) {
      sourceSegmentId.value = segData.current_segment_id ?? segData.items[0]?.id ?? null;
    }
    loadError.value = null;
  } catch (err) {
    const info = extractError(err);
    if (showError) {
      loadError.value =
        info.status === 404 ? "项目不存在或已被删除" : info.message;
    }
  }
}

function onSwitchSource(segmentId: string) {
  sourceSegmentId.value = segmentId;
  finalPromptPreview.value = null;
}

function onExtendSegment(segment: GenerationSegment) {
  sourceSegmentId.value = segment.id;
  finalPromptPreview.value = null;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---------- 局部重拍 ----------
const retakeVisible = ref(false);
const retakeSegment = ref<GenerationSegment | null>(null);

function onRetakeSegment(segment: GenerationSegment) {
  retakeSegment.value = segment;
  retakeVisible.value = true;
}

function onRetakeSubmitted(taskId: string) {
  ElMessage.success(`重拍任务已排队：${taskId.slice(0, 8)}`);
  startWatch(taskId);
}

async function onSetCurrent(segment: GenerationSegment) {
  try {
    await setCurrentSegment(projectId.value, segment.id);
    ElMessage.success(`已将第 ${segment.segment_index} 段设为当前版本`);
    await load(false);
  } catch (err) {
    ElMessage.error(extractError(err).message);
  }
}

async function onTimelineCommand(command: string, segment: GenerationSegment) {
  if (command === "detail") {
    void router.push(`/tasks/${segment.task_id}`);
    return;
  }
  if (command === "download") {
    window.location.href = `/api/segments/${segment.id}/download`;
    return;
  }
  if (command === "delete") {
    try {
      await ElMessageBox.confirm(
        `删除第 ${segment.segment_index} 段？若该版本仍被其他版本引用则无法删除。`,
        "删除版本",
        { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
      );
    } catch {
      return;
    }
    try {
      await deleteSegment(segment.id, false);
      ElMessage.success("版本已删除");
      if (sourceSegmentId.value === segment.id) sourceSegmentId.value = null;
      await load(false);
    } catch (err) {
      ElMessage.error(extractError(err).message);
    }
  }
}

async function doPreview() {
  if (!form.prompt.trim()) {
    previewing.value = false;
    ElMessage.warning("请先填写本次动作提示词");
    return;
  }
  previewing.value = true;
  try {
    finalPromptPreview.value = await previewPrompt(
      projectId.value,
      form.prompt.trim(),
      form.appendProjectPrompt,
    );
  } catch (err) {
    ElMessage.error(extractError(err).message);
  } finally {
    previewing.value = false;
  }
}

function resolveSeed(): number | null {
  if (randomSeed.value) return null;
  const text = seedInput.value.trim();
  if (!text) return null;
  const parsed = Number(text);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

async function onSubmit() {
  if (!sourceSegment.value) return;
  const action = form.prompt.trim();
  if (!action) {
    submitError.value = "请填写本次动作提示词";
    return;
  }
  const seed = resolveSeed();
  if (!randomSeed.value && seedInput.value.trim() && seed === null) {
    submitError.value = "随机种子必须是 0 或正整数";
    return;
  }

  submitError.value = null;
  submitting.value = true;
  try {
    const result = await submitExtend(projectId.value, {
      source_segment_id: sourceSegment.value.id,
      prompt: action,
      extend_frames: form.extendFrames,
      seed,
      append_project_prompt: form.appendProjectPrompt,
      anchor_frame: null,
      anchor_strength: null,
      anchor_image: null,
    });
    lastResult.value = result;
    // 保留提示词，便于基于同一动作微调后再试；清理以防重复提交
    ElMessage.success("续写任务已加入队列");
    startWatch(result.task_id);
    void load(false);
  } catch (err) {
    submitError.value = extractError(err).message;
  } finally {
    submitting.value = false;
  }
}

let watchTimer: number | null = null;
let refreshTimer: number | null = null;

function stopWatch() {
  if (watchTimer !== null) {
    window.clearInterval(watchTimer);
    watchTimer = null;
  }
}

async function pollTask(taskId: string) {
  try {
    const resp = await fetch(`/api/tasks/${taskId}`);
    if (!resp.ok) return;
    const data = await resp.json();
    const status = data.status as string;
    if (status === "SUCCEEDED") {
      stopWatch();
      ElMessage.success("续写已完成，创作链已添加新版本");
      await load(false);
    } else if (status === "FAILED" || status === "CANCELED") {
      stopWatch();
      await load(false);
    }
  } catch {
    // 轮询失败静默
  }
}

function startWatch(taskId: string) {
  stopWatch();
  watchTimer = window.setInterval(() => void pollTask(taskId), 3000);
}

async function loadAttachableTasks() {
  loadingTasks.value = true;
  try {
    const data = await fetchTasks({ status: "SUCCEEDED", limit: 30 });
    attachableTasks.value = data.items.filter((item) => item.task_type !== "EXTEND");
  } catch {
    attachableTasks.value = [];
  } finally {
    loadingTasks.value = false;
  }
}

async function onAttach() {
  if (!attachTaskId.value) return;
  attaching.value = true;
  try {
    const segment = await attachSegment(projectId.value, attachTaskId.value);
    ElMessage.success(`已加入项目（第 ${segment.segment_index} 段）`);
    attachTaskId.value = null;
    await load(false);
    await loadAttachableTasks();
  } catch (err) {
    ElMessage.error(extractError(err).message);
  } finally {
    attaching.value = false;
  }
}

async function saveSummary() {
  savingSummary.value = true;
  try {
    await updateProject(projectId.value, {
      story_summary: storySummary.value.trim() || null,
    });
    ElMessage.success("剧情摘要已保存");
    await load(false);
  } catch (err) {
    ElMessage.error(extractError(err).message);
  } finally {
    savingSummary.value = false;
  }
}

function openSettings() {
  if (!project.value) return;
  settingsForm.name = project.value.name;
  settingsForm.character_setting = project.value.character_setting ?? "";
  settingsForm.scene_setting = project.value.scene_setting ?? "";
  settingsForm.style_setting = project.value.style_setting ?? "";
  settingsForm.continuity_rules = project.value.continuity_rules ?? "";
  settingsForm.append_project_prompt = project.value.append_project_prompt;
}

async function saveSettings() {
  if (!settingsForm.name.trim()) {
    ElMessage.error("项目名称不能为空");
    return;
  }
  savingSettings.value = true;
  try {
    await updateProject(projectId.value, {
      name: settingsForm.name.trim(),
      character_setting: settingsForm.character_setting.trim() || null,
      scene_setting: settingsForm.scene_setting.trim() || null,
      style_setting: settingsForm.style_setting.trim() || null,
      continuity_rules: settingsForm.continuity_rules.trim() || null,
      append_project_prompt: settingsForm.append_project_prompt,
    });
    settingsVisible.value = false;
    ElMessage.success("项目设定已保存");
    await load(false);
  } catch (err) {
    ElMessage.error(extractError(err).message);
  } finally {
    savingSettings.value = false;
  }
}

async function onDeleteProject() {
  try {
    await ElMessageBox.confirm(
      "删除项目会移除所有版本记录。视频文件默认保留，可勾选一并删除。",
      "删除项目",
      { type: "warning", confirmButtonText: "继续", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  let deleteVideos = false;
  try {
    await ElMessageBox.confirm(
      "是否同时删除这些版本的视频文件？（不可恢复）",
      "文件处理",
      {
        type: "error",
        confirmButtonText: "删除文件",
        cancelButtonText: "仅删记录",
        distinguishCancelAndClose: true,
      },
    );
    deleteVideos = true;
  } catch (action) {
    if (action === "close") return;
    deleteVideos = false;
  }

  try {
    const result = await deleteProject(projectId.value, deleteVideos);
    ElMessage.success(result.message);
    void router.push("/projects");
  } catch (err) {
    ElMessage.error(extractError(err).message);
  }
}

onMounted(async () => {
  if (!system.settings) void system.refreshSettings();
  loading.value = true;
  await load();
  loading.value = false;
  if (project.value) openSettings();
  void loadAttachableTasks();
  refreshTimer = window.setInterval(() => {
    if (!lastResult.value) return;
    void load(false);
  }, 8000);
});

onUnmounted(() => {
  if (refreshTimer !== null) window.clearInterval(refreshTimer);
  stopWatch();
});
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  max-width: 1360px;
  min-width: 0;
}
.page > * {
  min-width: 0;
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
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 16px;
  align-items: start;
  min-width: 0;
}
@media (max-width: 1120px) {
  .layout-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
.main-panel {
  padding: 16px 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 22px;
  min-width: 0;
}
.loading-panel {
  padding: 24px;
}
.block {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.block-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.block-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}
.player-shell {
  background: #000;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--border);
  display: flex;
  justify-content: center;
  max-width: 100%;
  min-width: 0;
}
.player-shell video {
  width: 100%;
  max-width: 100%;
  max-height: 48vh;
  display: block;
  object-fit: contain;
}
.source-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.kv {
  font-size: 11px;
  color: var(--text-faint);
}
.prompt-text {
  margin: 0;
  font-size: 12.5px;
  color: var(--text);
  line-height: 1.6;
}
.final-prompt {
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
  max-height: 220px;
  overflow: auto;
}
.first-block {
  gap: 14px;
}
.first-hint {
  font-size: 12px;
  line-height: 1.65;
  color: var(--text-dim);
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
  padding: 6px 16px;
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
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.field label {
  font-size: 12px;
  color: var(--text-dim);
  font-weight: 500;
}
.first-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}

.source-switch {
  display: flex;
  align-items: center;
  gap: 8px;
}
.options-row {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
}
.opt-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.preview-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}
.result-lines {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12px;
  align-items: center;
}
.link {
  font-size: 12px;
}
.submit-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.inline-alert {
  flex: 1;
  min-width: 240px;
}
.empty-hint {
  color: var(--warn);
}
.side-column {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.side-panel {
  padding: 14px 16px;
}
.kv-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 5px 0;
  border-bottom: 1px solid var(--border);
}
.kv-block:last-child {
  border-bottom: none;
}
.kv-block .k {
  font-size: 11px;
  color: var(--text-faint);
}
.kv-block .v {
  font-size: 12.5px;
  color: var(--text);
  line-height: 1.55;
}
.form-hint {
  margin-left: 10px;
}
</style>
