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
  // 初始化平台缓存（在 app 挂载前获取 OS 平台信息）
  // Init platform cache (get OS platform info before app mounts)
  await initPlatformCache()

  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.use(i18n)
  app.use(Antd)
  app.mount('#app')
}

bootstrap()
