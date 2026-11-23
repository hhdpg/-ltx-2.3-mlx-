<template>
  <div class="generation-settings">
    <div class="grid">
      <div class="field">
        <label>分辨率</label>
        <el-select
          :model-value="resolutionKey"
          @update:model-value="onResolution"
          style="width: 100%"
        >
          <el-option
            v-for="preset in resolutions"
            :key="preset.key"
            :label="preset.label"
            :value="preset.key"
          />
        </el-select>
        <span class="hint-inline">宽 × 高</span>
      </div>

      <div class="field">
        <label>帧数</label>
        <el-select v-model="framesModel" style="width: 100%">
          <el-option
            v-for="option in frameOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <span class="hint-inline">{{ framesDuration }} 秒 · 8k+1</span>
      </div>

      <div class="field">
        <label>帧率</label>
        <el-select v-model="frameRateModel" style="width: 100%">
          <el-option
            v-for="rate in allowedFrameRates"
            :key="rate"
            :label="`${rate} FPS`"
            :value="rate"
          />
        </el-select>
        <span class="hint-inline">V1 仅 24 FPS</span>
      </div>

      <div class="field">
        <label>推理模式</label>
        <el-select v-model="modeModel" style="width: 100%">
          <el-option label="Distilled（推荐）" value="distilled" />
        </el-select>
        <span class="hint-inline">V1 仅开放 Distilled</span>
      </div>

      <div class="field seed-field">
        <label>随机种子</label>
        <div class="seed-row">
          <el-switch
            v-model="randomSeedModel"
            active-text="随机"
            inactive-text="固定"
            inline-prompt
          />
          <el-input
            v-if="!randomSeedModel"
            v-model="seedInputModel"
            placeholder="如 12345"
            style="flex: 1"
            :disabled="randomSeedModel"
          />
        </div>
        <span v-if="seedError" class="error-text">{{ seedError }}</span>
        <span v-else class="hint-inline">CLI 支持 --seed</span>
      </div>

      <div v-if="lowRamAvailable" class="field">
        <label>低内存模式</label>
        <div class="low-ram-row">
          <el-switch v-model="lowRamModel" />
          <span class="hint-inline">分块流式加载，降低峰值内存</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  width: number;
  height: number;
  frames: number;
  frameRate: number;
  mode: string;
  seedInput: string;
  randomSeed: boolean;
  lowRam: boolean;
  lowRamAvailable?: boolean;
  allowedResolutions: number[][];
  allowedFrames: number[];
  allowedFrameRates: number[];
  framesError?: string | null;
  seedError?: string | null;
}>();

const emit = defineEmits<{
  (event: "update:width", value: number): void;
  (event: "update:height", value: number): void;
  (event: "update:frames", value: number): void;
  (event: "update:frameRate", value: number): void;
  (event: "update:mode", value: string): void;
  (event: "update:seedInput", value: string): void;
  (event: "update:randomSeed", value: boolean): void;
  (event: "update:lowRam", value: boolean): void;
}>();

const resolutions = computed(() => {
  const pairs = props.allowedResolutions.length
    ? props.allowedResolutions
    : [
        [512, 320],
        [320, 512],
        [640, 384],
        [384, 640],
        [768, 512],
        [512, 768],
      ];
  return pairs.map(([w, h]) => ({
    key: `${w}x${h}`,
    label: `${w} × ${h}`,
    width: w,
    height: h,
  }));
});

const resolutionKey = computed(() => `${props.width}x${props.height}`);

function onResolution(key: string) {
  const preset = resolutions.value.find((item) => item.key === key);
  if (!preset) return;
  emit("update:width", preset.width);
  emit("update:height", preset.height);
}

const frameOptions = computed(() => {
  const frames = props.allowedFrames.length
    ? props.allowedFrames
    : [9, 25, 41, 49, 65, 81, 97, 121];
  return frames.map((value) => ({
    value,
    label: `${value} 帧 · ${(value / props.frameRate).toFixed(2)}s`,
  }));
});

const framesDuration = computed(() =>
  (props.frames / (props.frameRate || 24)).toFixed(2),
);

const framesModel = computed({
  get: () => props.frames,
  set: (value: number) => emit("update:frames", value),
});

const frameRateModel = computed({
  get: () => props.frameRate,
  set: (value: number) => emit("update:frameRate", value),
});

const modeModel = computed({
  get: () => props.mode,
  set: (value: string) => emit("update:mode", value),
});

const seedInputModel = computed({
  get: () => props.seedInput,
  set: (value: string) => emit("update:seedInput", value),
});

const randomSeedModel = computed({
  get: () => props.randomSeed,
  set: (value: boolean) => emit("update:randomSeed", value),
});

const lowRamModel = computed({
  get: () => props.lowRam,
  set: (value: boolean) => emit("update:lowRam", value),
});
</script>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field label {
  font-size: 12px;
  color: var(--text-dim);
  font-weight: 500;
}
.hint-inline {
  font-size: 11px;
  color: var(--text-faint);
}
.error-text {
  font-size: 11px;
  color: var(--error);
}

.seed-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.low-ram-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 32px;
}
</style>
