<template>
  <div class="segment-timeline">
    <div class="timeline-head">
      <span class="title">创作链</span>
      <span class="hint">{{ items.length }} 个版本 · 按父子关系展示</span>
    </div>

    <div v-if="items.length === 0" class="hint empty">
      还没有版本。生成一个视频后可以加入项目。
    </div>

    <div v-else class="tree">
      <div
        v-for="node in flatNodes"
        :key="node.segment.id"
        class="seg-row"
        :class="{ current: node.segment.is_current, dim: node.depth > 0 }"
        :style="{ paddingLeft: `${node.depth * 22 + 10}px` }"
        @click="$emit('select', node.segment)"
      >
        <span class="branch-marker">{{ node.depth > 0 ? "└" : "●" }}</span>

        <div class="seg-thumb">
          <video
            v-if="node.segment.video_ready"
            :src="segmentVideoUrl(node.segment.id)"
            preload="metadata"
            muted
            playsinline
          ></video>
          <el-icon v-else><Warning /></el-icon>
        </div>

        <div class="seg-body">
          <div class="seg-line1">
            <span class="idx">第 {{ node.segment.segment_index }} 段</span>
            <code class="type">{{ node.segment.task_type }}</code>
            <span v-if="node.segment.extend_frames" class="mono small">
              +{{ node.segment.extend_frames }} latent
            </span>
            <el-tag v-if="node.segment.is_current" size="small" type="success">
              当前版本
            </el-tag>
            <el-tag v-if="node.segment.child_count > 1" size="small" type="warning">
              {{ node.segment.child_count }} 个分支
            </el-tag>
          </div>
          <div class="seg-prompt" :title="node.segment.prompt">
            {{ node.segment.prompt }}
          </div>
          <div class="seg-meta mono">
            {{ node.segment.width }}x{{ node.segment.height }} ·
            {{ (node.segment.duration_seconds ?? 0).toFixed(2) }}s ·
            {{ node.segment.frame_rate ?? 24 }}fps
          </div>
        </div>

        <div class="seg-actions" @click.stop>
          <el-button
            v-if="node.segment.video_ready"
            size="small"
            text
            @click="$emit('retake', node.segment)"
          >
            重拍
          </el-button>
          <el-button size="small" text type="primary" @click="$emit('extend', node.segment)">
            续写
          </el-button>
          <el-button
            v-if="!node.segment.is_current && node.segment.video_ready"
            size="small"
            text
            @click="$emit('set-current', node.segment)"
          >
            设为当前
          </el-button>
          <el-dropdown trigger="click" @command="(cmd: string) => $emit('command', cmd, node.segment)">
            <el-button size="small" text>⋯</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="detail">查看详情</el-dropdown-item>
                <el-dropdown-item command="download">下载视频</el-dropdown-item>
                <el-dropdown-item
                  command="delete"
                  :disabled="node.segment.child_count > 0"
                  divided
                >
                  删除版本
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { GenerationSegment } from "@/types";
import { segmentVideoUrl } from "@/api/project";

const props = defineProps<{
  items: GenerationSegment[];
  children: Record<string, string[]>;
  currentSegmentId: string | null;
}>();

defineEmits<{
  (event: "select", segment: GenerationSegment): void;
  (event: "extend", segment: GenerationSegment): void;
  (event: "retake", segment: GenerationSegment): void;
  (event: "set-current", segment: GenerationSegment): void;
  (event: "command", command: string, segment: GenerationSegment): void;
}>();

interface FlatNode {
  segment: GenerationSegment;
  depth: number;
}

/** 按父子关系展开为树（深度优先），不假设只有一条直线。 */
const flatNodes = computed<FlatNode[]>(() => {
  const byId = new Map(props.items.map((item) => [item.id, item]));
  const roots = props.items
    .filter((item) => !item.parent_segment_id || !byId.has(item.parent_segment_id))
    .sort((a, b) => a.segment_index - b.segment_index);

  const result: FlatNode[] = [];
  const visited = new Set<string>();

  const walk = (segment: GenerationSegment, depth: number) => {
    if (visited.has(segment.id)) return;
    visited.add(segment.id);
    result.push({ segment, depth });
    const childIds = props.children[segment.id] ?? [];
    const children = childIds
      .map((id) => byId.get(id))
      .filter((item): item is GenerationSegment => Boolean(item))
      .sort((a, b) => a.segment_index - b.segment_index);
    for (const child of children) walk(child, depth + 1);
  };

  for (const root of roots) walk(root, 0);

  // 兜底：孤儿节点（理论上不会出现）也要展示
  for (const item of props.items) {
    if (!visited.has(item.id)) walk(item, 0);
  }
  return result;
});
</script>

<style scoped>
.segment-timeline {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.timeline-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.timeline-head .title {
  font-size: 14px;
  font-weight: 600;
}
.empty {
  padding: 18px 0;
}
.tree {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.seg-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  transition: background 0.12s, border-color 0.12s;
  cursor: pointer;
}
.seg-row:hover {
  background: var(--bg-panel-soft);
  border-color: var(--border);
}
.seg-row.current {
  background: var(--accent-soft);
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
}
.branch-marker {
  color: var(--text-faint);
  font-family: var(--mono);
  flex: none;
}
.seg-thumb {
  width: 78px;
  height: 50px;
  flex: none;
  border-radius: 5px;
  overflow: hidden;
  background: #000;
  display: grid;
  place-items: center;
  color: var(--text-faint);
}
.seg-thumb video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.seg-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.seg-line1 {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.idx {
  font-size: 12.5px;
  font-weight: 500;
}
.type {
  font-size: 10px;
  padding: 0 5px;
  border-radius: 3px;
  background: var(--bg-input);
  color: var(--text-dim);
}
.seg-prompt {
  font-size: 12px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.seg-meta {
  font-size: 10.5px;
  color: var(--text-faint);
}
.small {
  font-size: 11px;
  color: var(--text-faint);
}
.seg-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: none;
}
.seg-actions :deep(.el-button) {
  padding: 2px 6px;
  margin-left: 0;
}
</style>
