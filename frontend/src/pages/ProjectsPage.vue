<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>连续创作</h2>
        <p class="hint">每条创作主题下保存整条版本链，旧版本永不覆盖</p>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="reload">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新建项目
        </el-button>
      </div>
    </div>

    <div v-if="projects.length > 0" class="grid">
      <router-link
        v-for="project in projects"
        :key="project.id"
        :to="`/projects/${project.id}`"
        class="panel card"
      >
        <div class="thumb">
          <video
            v-if="project.current_video_url"
            :src="project.current_video_url"
            preload="metadata"
            muted
            playsinline
          ></video>
          <div v-else class="no-video">尚无版本</div>
          <span class="count-badge">{{ project.segment_count }} 段</span>
        </div>
        <div class="card-body">
          <div class="card-name">{{ project.name }}</div>
          <div class="card-meta mono">
            <template v-if="project.current_duration_seconds">
              当前 {{ project.current_duration_seconds.toFixed(2) }}s
            </template>
            <template v-else>未设置当前版本</template>
          </div>
          <div class="card-meta faint">{{ formatDateTime(project.updated_at) }}</div>
        </div>
      </router-link>
    </div>

    <div v-else-if="!loading" class="panel empty-state">
      <el-icon size="34"><Film /></el-icon>
      <p>还没有创作项目</p>
      <p class="hint">
        可以在生成成功的视频详情页点击「继续创作」，或在这里新建项目后添加视频。
      </p>
      <el-button type="primary" @click="openCreate">新建项目</el-button>
    </div>

    <el-dialog v-model="dialogVisible" title="新建创作项目" width="560px">
      <el-form label-width="96px">
        <el-form-item label="项目名称" required>
          <el-input v-model="form.name" placeholder="例如：海边日落短片" maxlength="200" />
        </el-form-item>
        <el-form-item label="角色设定">
          <el-input
            v-model="form.character_setting"
            type="textarea"
            :rows="2"
            placeholder="例如：一名穿深色外套的成年男性"
          />
        </el-form-item>
        <el-form-item label="场景设定">
          <el-input
            v-model="form.scene_setting"
            type="textarea"
            :rows="2"
            placeholder="例如：日落时分的海边，海面平静"
          />
        </el-form-item>
        <el-form-item label="视觉风格">
          <el-input
            v-model="form.style_setting"
            type="textarea"
            :rows="2"
            placeholder="例如：写实电影风格，镜头运动平稳"
          />
        </el-form-item>
        <el-form-item label="连续性要求">
          <el-input
            v-model="form.continuity_rules"
            type="textarea"
            :rows="2"
            placeholder="例如：尽量保持人物服装、发型和环境一致"
          />
        </el-form-item>
        <el-form-item label="附带设定">
          <el-switch v-model="form.append_project_prompt" />
          <span class="hint form-hint">续写时默认把上述设定拼进 Prompt</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { createProject, fetchProjects } from "@/api/project";
import { extractError } from "@/api/http";
import { formatDateTime } from "@/utils/format";
import type { GenerationProject } from "@/types";

const router = useRouter();

const projects = ref<GenerationProject[]>([]);
const loading = ref(false);
const dialogVisible = ref(false);
const creating = ref(false);

const form = reactive({
  name: "",
  character_setting: "",
  scene_setting: "",
  style_setting: "",
  continuity_rules: "",
  append_project_prompt: true,
});

async function reload() {
  loading.value = true;
  try {
    const data = await fetchProjects();
    projects.value = data.items;
  } catch (err) {
    ElMessage.error(extractError(err).message);
    projects.value = [];
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  form.name = "";
  form.character_setting = "";
  form.scene_setting = "";
  form.style_setting = "";
  form.continuity_rules = "";
  form.append_project_prompt = true;
  dialogVisible.value = true;
}

async function submitCreate() {
  if (!form.name.trim()) {
    ElMessage.error("请填写项目名称");
    return;
  }
  creating.value = true;
  try {
    const project = await createProject({
      name: form.name.trim(),
      character_setting: form.character_setting.trim() || null,
      scene_setting: form.scene_setting.trim() || null,
      style_setting: form.style_setting.trim() || null,
      continuity_rules: form.continuity_rules.trim() || null,
      append_project_prompt: form.append_project_prompt,
    });
    dialogVisible.value = false;
    ElMessage.success("项目已创建");
    void router.push(`/projects/${project.id}`);
  } catch (err) {
    ElMessage.error(extractError(err).message);
  } finally {
    creating.value = false;
  }
}

let timer: number | null = null;

onMounted(() => {
  void reload();
  timer = window.setInterval(() => void reload(), 20000);
});

onUnmounted(() => {
  if (timer !== null) window.clearInterval(timer);
});
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
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
.header-actions {
  display: flex;
  gap: 8px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}
.card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: border-color 0.15s, transform 0.15s;
}
.card:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
}
.thumb {
  position: relative;
  aspect-ratio: 16 / 10;
  background: #000;
  display: grid;
  place-items: center;
}
.thumb video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.no-video {
  color: var(--text-faint);
  font-size: 12px;
}
.count-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.65);
  color: #d5e2ff;
  font-family: var(--mono);
}
.card-body {
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.card-name {
  font-size: 13.5px;
  color: var(--text);
  font-weight: 500;
}
.card-meta {
  font-size: 11px;
  color: var(--text-dim);
}
.card-meta.faint {
  color: var(--text-faint);
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 60px 20px;
  color: var(--text-faint);
}
.empty-state p {
  margin: 0;
  font-size: 13px;
}
.form-hint {
  margin-left: 10px;
}
</style>
