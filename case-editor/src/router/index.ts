import { createRouter, createWebHashHistory } from 'vue-router'
import EditorView from '../views/EditorView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'editor',
      component: EditorView,
    },
  ],
})

export default router
