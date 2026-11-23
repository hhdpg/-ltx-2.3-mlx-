<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { useSystemStore } from "@/stores/system";

const system = useSystemStore();

onMounted(() => {
  // 环境检查包含 MLX/CLI 探测，稍慢，放到挂载后执行
  void system.refreshAll();
});
</script>
