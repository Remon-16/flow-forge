import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import electronSimple from 'vite-plugin-electron/simple'

export default defineConfig(({ mode }) => {
  const plugins: any[] = [vue()]

  if (mode === 'electron') {
    plugins.push(
      electronSimple({
        main: {
          entry: 'electron/main.ts',
        },
        preload: {
          input: 'electron/preload.ts',
        },
        renderer: {},
      }),
    )
  }

  return { plugins }
})
