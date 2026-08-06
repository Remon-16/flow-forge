import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { initPlatformCache } from './utils/resolve-python'
import './assets/styles/global.css'

async function bootstrap(): Promise<void> {
  // 立即创建并挂载 Vue 应用，用户马上看到 UI（不再等待平台初始化）
  // Create and mount Vue app immediately — user sees UI right away (no longer waits for platform init)
  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.use(i18n)
  app.use(Antd)
  app.mount('#app')

  // 后台初始化平台缓存，不阻塞 UI 渲染
  // Initialize platform cache in background, non-blocking UI render
  // 非 Windows 平台守卫已移至 App.vue onMounted 中处理
  // Non-Windows platform guard moved to App.vue onMounted
  initPlatformCache().catch(() => {
    // 平台初始化失败不影响核心功能 / Platform init failure doesn't affect core features
  })
}

bootstrap()
