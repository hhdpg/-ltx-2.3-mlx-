<template>
  <div class="video-player">
    <div class="player-shell">
      <video
        ref="videoRef"
        :src="src"
        controls
        preload="metadata"
        playsinline
        @loadedmetadata="onLoaded"
        @error="onError"
      ></video>
    </div>
    <div v-if="error" class="player-error">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ error }}</span>
    </div>
    <div v-else-if="meta" class="player-meta">
      <span>{{ resolution }}</span>
      <span>·</span>
      <span>{{ meta.duration.toFixed(2) }}s</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";

const props = defineProps<{ src: string }>();

const videoRef = ref<HTMLVideoElement | null>(null);
const error = ref<string | null>(null);
const meta = ref<{ duration: number; width: number; height: number } | null>(null);

const resolution = computed(() =>
  meta.value ? `${meta.value.width} × ${meta.value.height}` : "",
);

function onLoaded() {
  const el = videoRef.value;
  if (!el) return;
  error.value = null;
  meta.value = {
    duration: Number.isFinite(el.duration) ? el.duration : 0,
    width: el.videoWidth,
    height: el.videoHeight,
  };
}

function onError() {
  error.value = "视频加载失败，请确认输出文件仍然存在";
}

watch(
  () => props.src,
  () => {
    error.value = null;
    meta.value = null;
    if (videoRef.value) videoRef.value.load();
  },
);
</script>

<style scoped>
.video-player {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.player-shell {
  background: #000;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--border);
  display: flex;
  justify-content: center;
}
video {
  width: 100%;
  max-height: 60vh;
  display: block;
}
.player-meta {
  display: flex;
  gap: 6px;
  font-size: 12px;
  color: var(--text-faint);
}
.player-error {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--error);
  font-size: 12px;
}
</style>
