import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  // Tailwind v4 подключается плагином, без postcss.config и tailwind.config:
  // тема и состав утилит задаются в самом CSS (`src/styles/base.css`)
  plugins: [react(), tailwindcss()],
  // `@/…` — то же самое, что `paths` в tsconfig. Компоненты shadcn ходят
  // друг к другу и в `lib/utils` только этим псевдонимом, и без пары здесь
  // проверка типов проходит, а сборка падает на первом же импорте
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // в контейнере файловые события не всегда доходят — опрашиваем
    watch: { usePolling: true },
    proxy: {
      '/api': { target: process.env.VITE_API_TARGET ?? 'http://backend:8000', changeOrigin: true },
    },
  },
})
