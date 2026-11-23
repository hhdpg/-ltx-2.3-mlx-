<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>模型与环境</h2>
        <p class="hint">所有检测均在本机执行，不请求任何云端推理接口</p>
      </div>
      <el-button :loading="system.loading" @click="recheck">
        <el-icon><Refresh /></el-icon>
        重新检测
      </el-button>
    </div>

    <el-alert
      v-if="system.health && !system.health.ready"
      type="error"
      :closable="false"
      show-icon
      title="环境未就绪，无法提交生成任务"
    >
      <div class="alert-list">
        <div v-for="reason in system.blockingReasons" :key="reason">· {{ reason }}</div>
      </div>
    </el-alert>
    <el-alert
      v-else-if="system.health"
      type="success"
      :closable="false"
      show-icon
      title="环境检查通过，可以开始生成"
    />

    <div class="layout-grid">
      <section class="panel check-panel">
        <h3 class="panel-title">环境检查</h3>
        <div v-if="checks.length === 0" class="hint">检测中…</div>
        <div v-for="check in checks" :key="check.key" class="check-row">
          <span class="dot" :class="check.status"></span>
          <span class="check-label">{{ check.label }}</span>
          <span class="check-message" :title="check.detail ?? check.message">
            {{ check.message }}
          </span>
        </div>
      </section>

      <section class="panel info-panel">
        <h3 class="panel-title">系统信息</h3>
        <div class="kv"><span>设备平台</span><code>{{ info?.platform ?? "—" }}</code></div>
        <div class="kv"><span>CPU 架构</span><code>{{ info?.architecture ?? "—" }}</code></div>
        <div class="kv"><span>CPU 核心</span><code>{{ info?.cpu_count ?? "—" }}</code></div>
        <div class="kv"><span>Python</span><code>{{ info?.python_version ?? "—" }}</code></div>
        <div class="kv">
          <span>统一内存</span>
          <code>
            {{ info?.total_memory_gb ?? "—" }} GiB
            <template v-if="info?.available_memory_gb != null">
              （可用 {{ info.available_memory_gb }} GiB）
            </template>
          </code>
        </div>
        <div class="kv">
          <span>磁盘空间</span>
          <code>
            剩余 {{ info?.disk_free_gb ?? "—" }} / 共 {{ info?.disk_total_gb ?? "—" }} GiB
          </code>
        </div>
        <div class="kv"><span>CLI 版本</span><code>{{ info?.cli_version ?? "未检测到版本行" }}</code></div>
        <div class="kv"><span>离线模式</span><code>{{ settings?.offline_mode ? "开启" : "关闭" }}</code></div>
      </section>
    </div>

    <section class="panel path-panel">
      <h3 class="panel-title">路径配置</h3>
      <div class="kv"><span>模型仓库 ID</span><code>{{ info?.model_id ?? "—" }}</code></div>
      <div class="kv"><span>CLI 可执行文件</span><code class="break">{{ info?.cli_path ?? "未配置" }}</code></div>
      <div class="kv"><span>模型本地路径</span><code class="break">{{ modelPath ?? "未配置" }}</code></div>
      <div class="kv"><span>上传目录</span><code class="break">{{ info?.upload_dir ?? "—" }}</code></div>
      <div class="kv"><span>输出目录</span><code class="break">{{ info?.output_dir ?? "—" }}</code></div>
      <div class="kv"><span>日志目录</span><code class="break">{{ info?.log_dir ?? "—" }}</code></div>
      <p class="hint">
        模型路径优先级：.env 的 LTX_MODEL_PATH → 设置页保存的目录 → Hugging Face 本地缓存。
        程序不会为查找模型而联网。
      </p>
    </section>

    <section class="panel settings-panel">
      <h3 class="panel-title">默认生成参数</h3>
      <el-form label-width="120px" class="settings-form">
        <el-form-item label="默认分辨率">
          <el-select v-model="form.resolutionKey" style="width: 220px">
            <el-option
              v-for="preset in resolutionOptions"
              :key="preset.key"
              :label="preset.label"
              :value="preset.key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="默认帧数">
          <el-select v-model="form.frames" style="width: 220px">
            <el-option
              v-for="frames in settings?.allowed_frames ?? []"
              :key="frames"
              :label="`${frames} 帧（${(frames / 24).toFixed(2)}s）`"
              :value="frames"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="默认帧率">
          <el-select v-model="form.frameRate" style="width: 220px">
            <el-option
              v-for="rate in settings?.allowed_frame_rates ?? [24]"
              :key="rate"
              :label="`${rate} FPS`"
              :value="rate"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="低内存模式">
          <div class="low-ram-row">
            <el-switch v-model="form.lowRam" />
            <span class="hint">开启后 CLI 追加 --low-ram（分块流式加载，速度变慢但峰值内存更低）</span>
          </div>
        </el-form-item>
        <el-form-item label="模型本地目录">
          <el-input
            v-model="form.modelPath"
            placeholder="留空则使用 .env 或本地缓存"
            style="width: 520px; max-width: 100%"
          />
          <div class="hint" style="margin-top: 4px">
            保存时会校验目录内是否存在有效权重文件；不完整的模型会被拒绝。
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="save">保存设置</el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useSystemStore } from "@/stores/system";
import { updateSettings } from "@/api/system";
import { extractError } from "@/api/http";

const system = useSystemStore();
const saving = ref(false);

const info = computed(() => system.info);
const settings = computed(() => system.settings);
const modelPath = computed(() => system.modelPath);
const checks = computed(() => info.value?.checks ?? []);

const resolutionOptions = computed(() => {
  const pairs = settings.value?.allowed_resolutions ?? [];
  return pairs.map(([w, h]) => ({ key: `${w}x${h}`, label: `${w} × ${h}`, w, h }));
});

const form = reactive({
  resolutionKey: "512x320",
  frames: 25,
  frameRate: 24,
  lowRam: false,
  modelPath: "",
});

function syncForm() {
  const s = settings.value;
  if (!s) return;
  form.resolutionKey = `${s.default_width}x${s.default_height}`;
  form.frames = s.default_frames;
  form.frameRate = s.default_frame_rate;
  form.lowRam = s.low_ram;
  form.modelPath = s.model_path ?? "";
}

watch(settings, syncForm, { immediate: true });

function resetForm() {
  syncForm();
  ElMessage.info("已恢复为当前保存值");
}

async function save() {
  const preset = resolutionOptions.value.find((item) => item.key === form.resolutionKey);
  saving.value = true;
  try {
    await updateSettings({
      default_width: preset?.w,
      default_height: preset?.h,
      default_frames: form.frames,
      default_frame_rate: form.frameRate,
      low_ram: form.lowRam,
      model_path: form.modelPath.trim() || "",
    });
    ElMessage.success("设置已保存");
    await system.refreshAll();
  } catch (err) {
    ElMessage.error(extractError(err).message);
  } finally {
    saving.value = false;
  }
}

async function recheck() {
  await system.refreshAll();
  ElMessage.success("环境检测已刷新");
}

onMounted(() => {
  void system.refreshAll();
});
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1180px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
}
.page-header h2 {
  margin: 0 0 4px;
  font-size: 20px;
}
.alert-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}
.layout-grid {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  gap: 16px;
  align-items: start;
}
@media (max-width: 1000px) {
  .layout-grid {
    grid-template-columns: 1fr;
  }
}
.check-panel,
.info-panel {
  padding: 18px;
}
.check-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px solid var(--border);
  font-size: 12.5px;
}
.check-row:last-child {
  border-bottom: none;
}
.check-label {
  width: 90px;
  flex: none;
  color: var(--text-dim);
}
.check-message {
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kv {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 12.5px;
  padding: 5px 0;
  color: var(--text-faint);
}
.kv code {
  color: var(--text);
  text-align: right;
}
.kv code.break {
  word-break: break-all;
  max-width: 70%;
}
.path-panel,
.settings-panel {
  padding: 18px;
}
.settings-form {
  margin-top: 8px;
}
.low-ram-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
