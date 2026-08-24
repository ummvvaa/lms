/**
 * Бренд школы. Название приходит из настроек сборки (`frontend/.env`
 * или переменные окружения) — в коде экранов напрямую не пишется.
 */

/** Полное название: вход, заголовок вкладки, письма. */
export const SCHOOL_NAME: string = import.meta.env.VITE_SCHOOL_NAME || 'Школа'

/** Короткое: свёрнутый сайдбар и узкие места. */
export const SCHOOL_SHORT_NAME: string = import.meta.env.VITE_SCHOOL_SHORT_NAME || SCHOOL_NAME

/**
 * Пути к вариантам логотипа. Каждому месту — свой размер,
 * один файл на все случаи не растягивается.
 */
export const LOGO = {
  /** страница входа */
  login: '/brand/logo-192.png',
  /** сайдбар */
  sidebar: '/brand/logo-96.png',
  /** шапка */
  header: '/brand/logo-56.png',
  /** ИИ-виджет */
  assistant: '/brand/logo-ai-96.png',
} as const
