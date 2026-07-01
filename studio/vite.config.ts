import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      // 共享 schema 包路径别名 / Shared schema package path alias
      '@flow-forge-schemas': path.resolve(__dirname, '../shared/ts/index.ts'),
    },
  },
})
