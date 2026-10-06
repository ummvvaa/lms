import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'

// Проверки чистых функций фронта (`*.test.ts` рядом с кодом): без браузера
// и без сборки экранов — плагины vite здесь не нужны
export default defineConfig({
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
})
