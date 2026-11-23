<template>
  <div class="image-uploader">
    <div
      v-if="!file"
      class="dropzone"
      :class="{ dragging, invalid: !!error }"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
      @click="triggerPick"
    >
      <el-icon size="22"><UploadFilled /></el-icon>
      <div class="drop-title">点击上传或拖拽图片</div>
      <div class="drop-hint">支持 PNG / JPG / JPEG / WEBP，不超过 {{ maxMb }}MB</div>
      <input
        ref="inputRef"
        type="file"
        accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
        hidden
        @change="onPick"
      />
    </div>

    <div v-else class="preview-card">
      <img :src="previewUrl ?? undefined" alt="参考图片预览" />
      <div class="preview-meta">
        <div class="meta-line">
          <span>文件</span>
          <code>{{ file.name }}</code>
        </div>
        <div class="meta-line">
          <span>尺寸</span>
          <code>{{ meta?.width || "?" }} × {{ meta?.height || "?" }}</code>
        </div>
        <div class="meta-line">
          <span>大小</span>
          <code>{{ formatBytes(file.size) }}</code>
        </div>
        <el-button size="small" @click="triggerPick">更换图片</el-button>
        <el-button size="small" type="danger" plain @click="remove">移除</el-button>
        <input
          ref="inputRef"
          type="file"
          accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
          hidden
          @change="onPick"
        />
      </div>
    </div>

    <div v-if="error" class="error-text">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { formatBytes } from "@/utils/format";

const props = defineProps<{
  file: File | null;
  previewUrl: string | null;
  meta: { width: number; height: number; size: number } | null;
  maxMb?: number;
  error?: string | null;
}>();

const emit = defineEmits<{
  (event: "change", file: File | null, meta?: { width: number; height: number }): void;
}>();

const inputRef = ref<HTMLInputElement | null>(null);
const dragging = ref(false);

const ACCEPTED = ["image/png", "image/jpeg", "image/webp"];
const ACCEPTED_EXT = [".png", ".jpg", ".jpeg", ".webp"];

function triggerPick() {
  inputRef.value?.click();
}

function remove() {
  emit("change", null);
}

async function handleFile(file: File) {
  const maxMb = props.maxMb ?? 15;
  const lower = file.name.toLowerCase();
  const hasValidExt = ACCEPTED_EXT.some((ext) => lower.endsWith(ext));

  if (!ACCEPTED.includes(file.type) && !hasValidExt) {
    ElMessage.error("仅支持 PNG、JPG、JPEG、WEBP 图片");
    return;
  }
  if (file.size > maxMb * 1024 * 1024) {
    ElMessage.error(`图片不能超过 ${maxMb}MB（当前 ${formatBytes(file.size)}）`);
    return;
  }

  // 前端预检图片尺寸；后端仍会校验真实文件类型
  try {
    const meta = await readDimensions(file);
    emit("change", file, meta);
  } catch {
    ElMessage.error("无法读取该图片，请确认文件未损坏");
  }
}

function readDimensions(file: File): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const result = { width: img.naturalWidth, height: img.naturalHeight };
      URL.revokeObjectURL(url);
      resolve(result);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("decode failed"));
    };
    img.src = url;
  });
}

function onPick(event: Event) {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (file) void handleFile(file);
  target.value = "";
}

function onDrop(event: DragEvent) {
  dragging.value = false;
  const file = event.dataTransfer?.files?.[0];
  if (file) void handleFile(file);
}
</script>

<style scoped>
.image-uploader {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dropzone {
  border: 1.5px dashed var(--border-strong);
  border-radius: var(--radius);
  padding: 22px;
  text-align: center;
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.dropzone:hover,
.dropzone.dragging {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--text);
}
.dropzone.invalid {
  border-color: var(--error);
}
.drop-title {
  font-size: 13px;
}
.drop-hint {
  font-size: 11px;
  color: var(--text-faint);
}

.preview-card {
  display: flex;
  gap: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px;
  background: var(--bg-panel-soft);
}
.preview-card img {
  width: 160px;
  height: 110px;
  object-fit: cover;
  border-radius: 6px;
  background: #000;
  flex: none;
}
.preview-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  flex: 1;
}
.meta-line {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--text-faint);
}
.meta-line code {
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.error-text {
  color: var(--error);
  font-size: 12px;
}
</style>
