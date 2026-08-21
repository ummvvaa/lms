/**
 * MSAL.js: получаем id_token у Microsoft и один раз отдаём его бэкенду.
 * Дальше работает наша сессия, токен Microsoft нигде не сохраняется.
 *
 * Библиотека грузится лениво: пока Entra не настроен, приложение
 * поднимается и без неё — вход идёт через одноразовую ссылку.
 */

const CLIENT_ID = import.meta.env.VITE_ENTRA_CLIENT_ID ?? ''
const TENANT_ID = import.meta.env.VITE_ENTRA_TENANT_ID ?? ''

export const isEntraConfigured = Boolean(CLIENT_ID && TENANT_ID)

type MsalApp = {
  initialize: () => Promise<void>
  loginPopup: (request: unknown) => Promise<{ idToken: string }>
}

let app: MsalApp | null = null

async function getApp(): Promise<MsalApp> {
  if (app) return app
  if (!isEntraConfigured) throw new Error('Вход через Microsoft не настроен')

  const msal = await import('@azure/msal-browser')
  const instance = new msal.PublicClientApplication({
    auth: {
      clientId: CLIENT_ID,
      authority: `https://login.microsoftonline.com/${TENANT_ID}`,
      redirectUri: window.location.origin,
    },
    // Токен Microsoft живёт только в памяти вкладки и в localStorage не пишется
    cache: { cacheLocation: 'memoryStorage', storeAuthStateInCookie: false },
  })
  await instance.initialize()
  app = instance as unknown as MsalApp
  return app
}

export async function acquireEntraToken(): Promise<string> {
  const instance = await getApp()
  const result = await instance.loginPopup({ scopes: ['openid', 'profile', 'email'] })
  if (!result.idToken) throw new Error('Microsoft не вернул id_token')
  return result.idToken
}
