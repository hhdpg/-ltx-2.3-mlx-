<template>
  <div class="task-tag" :style="{ '--c': meta.color }">
    <span class="dot" :class="meta.active ? 'warn' : ''" :style="{ background: meta.color }"></span>
    <span>{{ meta.label }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { TaskStatus } from "@/types";
import { statusMeta } from "@/utils/format";

const props = defineProps<{ status: TaskStatus }>();
const meta = computed(() => statusMeta(props.status));
</script>

<style scoped>
.task-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--c);
  background: color-mix(in srgb, var(--c) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--c) 35%, transparent);
  white-space: nowrap;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
</style>
