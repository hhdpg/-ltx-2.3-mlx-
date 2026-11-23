import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { TaskStatus, TaskSummary } from "@/types";
import { submitGeneration } from "@/api/generation";
import { fetchTasks } from "@/api/task";
import { extractError } from "@/api/http";

export interface FormError {
  field: string;
  message: string;
}

export const useGenerationStore = defineStore("generation", () => {
  // 生成页只产生 T2V / I2V；EXTEND 由项目续写流程创建
  const taskType = ref<"T2V" | "I2V">("T2V");
  const prompt = ref("");
  const width = ref(512);
  const height = ref(320);
  const frames = ref(25);
  const frameRate = ref(24);
  const mode = ref("distilled");
  const seedInput = ref<string>("");
  const randomSeed = ref(true);
  const imageFile = ref<File | null>(null);
  const imagePreviewUrl = ref<string | null>(null);
  const imageMeta = ref<{ width: number; height: number; size: number } | null>(null);

  const submitting = ref(false);
  const uploadProgress = ref(0);
  const errors = ref<FormError[]>([]);
  const submitError = ref<string | null>(null);
  const lastTaskId = ref<string | null>(null);
  const lastMessage = ref<string | null>(null);

  const recentTasks = ref<TaskSummary[]>([]);
  const recentLoading = ref(false);

  const promptLength = computed(() => prompt.value.length);
  const promptRemaining = computed(() => 4000 - prompt.value.length);

  function setTaskType(value: "T2V" | "I2V"): void {
    taskType.value = value;
    if (value === "T2V") {
      clearImage();
    }
  }

  function applyDefaults(defaults: {
    width: number;
    height: number;
    frames: number;
    frame_rate: number;
    mode?: string;
  }): void {
    width.value = defaults.width;
    height.value = defaults.height;
    frames.value = defaults.frames;
    frameRate.value = defaults.frame_rate;
    if (defaults.mode) mode.value = defaults.mode;
  }

  function setImage(file: File | null, meta?: { width: number; height: number }): void {
    if (imagePreviewUrl.value) {
      URL.revokeObjectURL(imagePreviewUrl.value);
      imagePreviewUrl.value = null;
    }
    imageFile.value = file;
    if (file) {
      imagePreviewUrl.value = URL.createObjectURL(file);
      imageMeta.value = {
        width: meta?.width ?? 0,
        height: meta?.height ?? 0,
        size: file.size,
      };
    } else {
      imageMeta.value = null;
    }
  }

  function clearImage(): void {
    setImage(null);
  }

  function validate(maxPromptLength = 4000): FormError[] {
    const found: FormError[] = [];
    const text = prompt.value.trim();
    if (!text) {
      found.push({ field: "prompt", message: "请输入提示词" });
    } else if (text.length > maxPromptLength) {
      found.push({
        field: "prompt",
        message: `提示词最多 ${maxPromptLength} 字符，当前 ${text.length}`,
      });
    }
    if ((frames.value - 1) % 8 !== 0 || frames.value < 9) {
      found.push({ field: "frames", message: "帧数必须符合 8k+1 规则" });
    }
    if (taskType.value === "I2V" && !imageFile.value) {
      found.push({ field: "image", message: "图片生成模式必须上传参考图片" });
    }
    if (!randomSeed.value && seedInput.value.trim() !== "") {
      const parsed = Number(seedInput.value);
      if (!Number.isInteger(parsed) || parsed < 0) {
        found.push({ field: "seed", message: "随机种子必须是 0 或正整数" });
      }
    }
    errors.value = found;
    return found;
  }

  function resolveSeed(): number | null {
    if (randomSeed.value) return null;
    const text = seedInput.value.trim();
    if (!text) return null;
    const parsed = Number(text);
    return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
  }

  function toPayload(projectId: string | null = null) {
    return {
      task_type: taskType.value,
      prompt: prompt.value.trim(),
      width: width.value,
      height: height.value,
      frames: frames.value,
      frame_rate: frameRate.value,
      mode: mode.value,
      seed: resolveSeed(),
      image: taskType.value === "I2V" ? imageFile.value : null,
      projectId,
    };
  }

  async function submit(
    maxPromptLength = 4000,
    projectId: string | null = null,
  ): Promise<string | null> {
    if (submitting.value) return null;
    submitError.value = null;
    lastMessage.value = null;
    if (validate(maxPromptLength).length > 0) {
      return null;
    }

    submitting.value = true;
    uploadProgress.value = 0;
    try {
      const result = await submitGeneration(toPayload(projectId), (percent) => {
        uploadProgress.value = percent;
      });
      lastTaskId.value = result.task_id;
      lastMessage.value = result.message;
      // 提示词保留，方便用户微调后再次生成
      return result.task_id;
    } catch (err) {
      submitError.value = extractError(err).message;
      return null;
    } finally {
      submitting.value = false;
      uploadProgress.value = 0;
    }
  }

  async function loadRecent(): Promise<void> {
    recentLoading.value = true;
    try {
      const data = await fetchTasks({ limit: 5 });
      recentTasks.value = data.items;
    } catch {
      recentTasks.value = [];
    } finally {
      recentLoading.value = false;
    }
  }

  function errorFor(field: string): string | null {
    return errors.value.find((item) => item.field === field)?.message ?? null;
  }

  const activeTask = computed(() =>
    recentTasks.value.find((task) =>
      (["QUEUED", "STARTING", "RUNNING", "CANCELING"] as TaskStatus[]).includes(
        task.status,
      ),
    ),
  );

  return {
    taskType,
    prompt,
    width,
    height,
    frames,
    frameRate,
    mode,
    seedInput,
    randomSeed,
    imageFile,
    imagePreviewUrl,
    imageMeta,
    submitting,
    uploadProgress,
    errors,
    submitError,
    lastTaskId,
    lastMessage,
    recentTasks,
    recentLoading,
    activeTask,
    promptLength,
    promptRemaining,
    setTaskType,
    applyDefaults,
    setImage,
    clearImage,
    validate,
    submit,
    loadRecent,
    errorFor,
    resolveSeed,
    toPayload,
  };
});
