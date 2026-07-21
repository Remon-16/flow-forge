import { createRouter, createWebHashHistory } from 'vue-router'
import HomePage from '../views/HomePage.vue'
import EditorView from '../views/EditorView.vue'
import YamlEditorView from '../views/YamlEditorView.vue'
import { ENABLE_DIAGNOSTICS } from '../utils/feature-flags'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomePage,
    },
    {
      path: '/excel',
      name: 'excel-editor',
      component: EditorView,
    },
    {
      path: '/yaml',
      name: 'yaml-editor',
      component: YamlEditorView,
    },
    {
      path: '/plan-annotator',
      name: 'plan-annotator',
      component: () => import('../views/PlanAnnotatorView.vue'),
    },
    {
      path: '/agent',
      name: 'agent',
      component: () => import('../views/AgentView.vue'),
    },
    {
      path: '/executor',
      name: 'executor',
      component: () => import('../views/ExecutorView.vue'),
    },
    {
      path: '/converter',
      name: 'converter',
      component: () => import('../views/ConverterView.vue'),
    },
    // 诊断工具路由 — 正式发布时设 ENABLE_DIAGNOSTICS=false 即可隐藏
    // Diagnostic route — hidden by setting ENABLE_DIAGNOSTICS=false for release
    ...(ENABLE_DIAGNOSTICS ? [{
      path: '/counter',
      name: 'counter',
      component: () => import('../views/CounterView.vue'),
    }] : []),
  ],
})

export default router
