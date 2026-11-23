<template>
  <div class="extend-length">
    <div class="label-row">
      <label>续写长度</label>
      <span class="hint">按源视频 {{ (fps ?? 24).toFixed(0) }} FPS 实时换算</span>
    </div>

    <div class="options">
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        class="opt"
        :class="{ active: modelValue === option.value }"
        @click="$emit('update:modelValue', option.value)"
      >
        <span class="dur">约 {{ option.seconds.toFixed(2) }} 秒</span>
        <span class="detail">{{ option.frames }} 帧 · extend_frames={{ option.value }}</span>
      </button>
    </div>

    <p class="hint note">
      新增帧数 = extend_frames × 8；distilled Extend 会把源视频最后 25 帧
      固定为新窗口的开头上下文。
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  modelValue: number;
  fps: number | null;
  allowed: number[];
}>();

defineEmits<{
  (event: "update:modelValue", value: number): void;
}>();

const options = computed(() => {
  const allowed = props.allowed.length ? props.allowed : [1, 2, 4, 8];
  const fps = props.fps && props.fps > 0 ? props.fps : 24;
  return allowed.map((value) => {
    const frames = value * 8;
    return {
      value,
      frames,
      seconds: Number((frames / fps).toFixed(3)),
    };
  });
});
</script>

<style scoped>
.extend-length {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.label-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.label-row label {
  font-size: 13px;
  font-weight: 500;
}
.options {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.opt {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: flex-start;
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-input);
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.15s;
}
.opt:hover {
  border-color: var(--border-strong);
}
.opt.active {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--text);
}
.dur {
  font-size: 13px;
  font-weight: 500;
}
.detail {
  font-size: 10.5px;
  color: var(--text-faint);
  font-family: var(--mono);
}
.note {
  margin: 0;
}
</style>
