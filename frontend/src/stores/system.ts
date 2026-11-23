import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { HealthResponse, SettingsResponse, SystemInfoResponse } from "@/types";
import { fetchHealth, fetchSettings, fetchSystemInfo } from "@/api/system";
import { extractError } from "@/api/http";

export const useSystemStore = defineStore("system", () => {
  const health = ref<HealthResponse | null>(null);
  const info = ref<SystemInfoResponse | null>(null);
  const settings = ref<SettingsResponse | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const lastCheckedAt = ref<number>(0);

  const ready = computed(() => health.value?.ready === true);
  const modelPath = computed(
    () => health.value?.model_path ?? settings.value?.model_path ?? null,
  );
  const blockingReasons = computed(() => {
    if (health.value?.blocking_reasons?.length) {
      return health.value.blocking_reasons;
    }
    return info.value?.blocking_reasons ?? [];
  });

  async function refreshHealth(): Promise<void> {
    try {
      health.value = await fetchHealth();
      lastCheckedAt.value = Date.now();
      error.value = null;
    } catch (err) {
      error.value = extractError(err).message;
      health.value = null;
    }
  }

  async function refreshSystemInfo(): Promise<void> {
    try {
      info.value = await fetchSystemInfo();
      error.value = null;
    } catch (err) {
      error.value = extractError(err).message;
    }
  }

  async function refreshSettings(): Promise<void> {
    try {
      settings.value = await fetchSettings();
    } catch (err) {
      error.value = extractError(err).message;
    }
  }

  async function refreshAll(): Promise<void> {
    loading.value = true;
    try {
      await Promise.all([refreshHealth(), refreshSystemInfo(), refreshSettings()]);
    } finally {
      loading.value = false;
    }
  }

  return {
    health,
    info,
    settings,
    loading,
    error,
    lastCheckedAt,
    ready,
    modelPath,
    blockingReasons,
    refreshHealth,
    refreshSystemInfo,
    refreshSettings,
    refreshAll,
  };
});
