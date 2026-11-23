import { createRouter, createWebHistory } from "vue-router";
import MainLayout from "@/layouts/MainLayout.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      component: MainLayout,
      children: [
        { path: "", redirect: "/generate" },
        {
          path: "generate",
          name: "generate",
          component: () => import("@/pages/GeneratePage.vue"),
          meta: { title: "新建生成" },
        },
        {
          path: "tasks",
          name: "tasks",
          component: () => import("@/pages/TasksPage.vue"),
          meta: { title: "任务历史" },
        },
        {
          path: "tasks/:id",
          name: "task-detail",
          component: () => import("@/pages/TaskDetailPage.vue"),
          meta: { title: "任务详情" },
        },
        {
          path: "projects",
          name: "projects",
          component: () => import("@/pages/ProjectsPage.vue"),
          meta: { title: "连续创作" },
        },
        {
          path: "projects/:id",
          name: "project-detail",
          component: () => import("@/pages/ProjectDetailPage.vue"),
          meta: { title: "创作项目" },
        },
        {
          path: "videos",
          name: "videos",
          component: () => import("@/pages/VideosPage.vue"),
          meta: { title: "视频作品" },
        },
        {
          path: "settings",
          name: "settings",
          component: () => import("@/pages/SettingsPage.vue"),
          meta: { title: "模型与环境" },
        },
        {
          path: "logs",
          name: "logs",
          component: () => import("@/pages/SystemLogsPage.vue"),
          meta: { title: "系统日志" },
        },
      ],
    },
    { path: "/:pathMatch(.*)*", redirect: "/generate" },
  ],
});

router.afterEach((to) => {
  const title = (to.meta.title as string) || "LTX Studio";
  document.title = `${title} · LTX Studio`;
});

export default router;
