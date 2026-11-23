<template>
  <div class="prompt-editor">
    <div class="label-row">
      <label>提示词</label>
      <span class="counter" :class="{ over: remaining < 0 }">
        {{ remaining }} 字符
      </span>
    </div>

    <el-input
      v-model="model"
      type="textarea"
      :rows="6"
      :maxlength="maxLength"
      resize="vertical"
      placeholder="描述你希望生成的视频画面和动作..."
    />

    <div class="footer-row">
      <div class="samples">
        <span class="hint">示例：</span>
        <button
          v-for="sample in samples"
          :key="sample.label"
          type="button"
          class="sample-chip"
          @click="applySample(sample.text)"
        >
          {{ sample.label }}
        </button>
      </div>
      <span v-if="error" class="error-text">{{ error }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { ElMessageBox } from "element-plus";

const props = defineProps<{
  modelValue: string;
  maxLength?: number;
  error?: string | null;
}>();

const emit = defineEmits<{
  (event: "update:modelValue", value: string): void;
}>();

const maxLength = computed(() => props.maxLength ?? 4000);

const model = computed({
  get: () => props.modelValue,
  set: (value: string) => emit("update:modelValue", value),
});

const remaining = computed(() => maxLength.value - props.modelValue.length);

const samples = [
  {
    label: "海边日落",
    text: "A cinematic sunset over the ocean, golden light reflecting on gentle waves, slow drifting camera, film grain, 35mm lens",
  },
  {
    label: "猫咪特写",
    text: "A fluffy cat sitting by a rain-streaked window, warm indoor lighting, subtle head turn, shallow depth of field",
  },
  {
    label: "城市夜景",
    text: "Neon-lit city street at night after rain, reflections on wet asphalt, slow dolly forward, cinematic teal and orange grading",
  },
];

async function applySample(text: string) {
  if (props.modelValue.trim()) {
    try {
      await ElMessageBox.confirm(
        "示例会替换当前提示词，是否继续？",
        "替换提示词",
        { confirmButtonText: "替换", cancelButtonText: "取消", type: "warning" },
      );
    } catch {
      return;
    }
  }
  emit("update:modelValue", text);
}
</script>

<style scoped>
.prompt-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.label-row label {
  font-size: 13px;
  font-weight: 500;
}
.counter {
  font-size: 12px;
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
}
.counter.over {
  color: var(--error);
}
.footer-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.samples {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.sample-chip {
  background: var(--bg-panel-soft);
  border: 1px solid var(--border);
  color: var(--text-dim);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.sample-chip:hover {
  color: var(--accent);
  border-color: var(--accent);
}
.error-text {
  color: var(--error);
  font-size: 12px;
}
</style>
