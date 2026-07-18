import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { initPlatformCache } from './utils/resolve-python'
import { getOsPlatform } from './utils/desktop-bridge'
import './assets/styles/global.css'

async function bootstrap(): Promise<void> {
  // 初始化平台缓存（在 app 挂载前获取 OS 平台信息）
  // Init platform cache (get OS platform info before app mounts)
  await initPlatformCache()

  // 非 Windows 平台守卫：阻止应用挂载，防止在无 Job Object 保护的环境下运行子进程。
  // Non-Windows guard: prevent app mount to avoid running without Job Object protection.
  const platform = await getOsPlatform()
  if (platform !== 'windows') {
    alert('Flow Forge Studio 仅支持 Windows 平台。\n\n请使用命令行工具代替：\n  cd agent && python main.py ...\n  cd python && python main.py ...')
    return
  }

  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.use(i18n)
  app.use(Antd)
  app.mount('#app')
}

bootstrap()
