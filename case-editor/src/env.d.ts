/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module 'js-yaml' {
  export function load(input: string, opts?: any): any
  export function dump(obj: any, opts?: any): string
  export const DEFAULT_SCHEMA: any
}

interface FileEntry {
  name: string
  path: string
  isDirectory: boolean
  children?: FileEntry[]
}

export {}
