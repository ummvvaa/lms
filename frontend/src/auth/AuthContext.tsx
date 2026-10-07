/**
 * Сессия пользователя.
 *
 * Вход по почте и паролю; сессия живёт в httpOnly cookie, токенов на фронте
 * нет вовсе. Одноразовые ссылки остались для приглашений, сброса пароля
 * и входа выпускников.
 */
import { createContext, useContext, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { post } from '../api/client'
import type { Me } from '../api/types'
import { releaseTab } from './tabOwner'
import { claimSession, readSession } from './sessionRead'
import { beginUsageSessionChange, finishUsageSessionChange } from '../usage/session'

interface AuthValue {
  me: Me | null
  isLoading: boolean
  /** сервер не ответил на вопрос о сессии — не отказал, а промолчал */
  failed: boolean
  retry: () => void
  login: (email: string, password: string) => Promise<Me>
  changePassword: (currentPassword: string, newPassword: string) => Promise<Me>
  requestPasswordReset: (email: string) => Promise<void>
  setPasswordByToken: (token: string, newPassword: string) => Promise<Me>
  loginWithLink: (token: string) => Promise<void>
  requestLink: (email: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['me'],
    queryFn: () => readSession(queryClient),
    staleTime: 60_000,
  })

  const setMe = (me: Me | null) => {
    finishUsageSessionChange(me?.id ?? null)
    claimSession(queryClient, me)
    queryClient.setQueryData(['me'], me)
    // права и состав экранов зависят от роли — прежние ответы больше не годятся
    void queryClient.invalidateQueries({ queryKey: ['domains'] })
  }

  const changingSession = async <T,>(request: () => Promise<T>): Promise<T> => {
    beginUsageSessionChange()
    await queryClient.cancelQueries({ queryKey: ['me'] })
    try {
      return await request()
    } catch (error) {
      // Ответ мог потеряться уже после смены cookie: прежнему кэшу не доверяем.
      finishUsageSessionChange(null)
      void queryClient.invalidateQueries({ queryKey: ['me'] })
      throw error
    }
  }

  const password = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      // почта, логин или подтверждённая личная почта — различает сервер
      changingSession(() => post<Me>('/auth/login/', { login: email, password })),
    onSuccess: setMe,
  })

  const change = useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      post<Me>('/auth/password/change/', body),
    onSuccess: setMe,
  })

  const setByToken = useMutation({
    mutationFn: (body: { token: string; new_password: string }) =>
      changingSession(() => post<Me>('/auth/password/set/', body)),
    onSuccess: setMe,
  })

  const resetRequest = useMutation({
    mutationFn: (email: string) => post<{ detail: string }>('/auth/password/reset/', { email }),
  })

  const link = useMutation({
    mutationFn: (token: string) => changingSession(() => post<Me>('/auth/magic-link/redeem/', { token })),
    onSuccess: setMe,
  })

  const linkRequest = useMutation({
    mutationFn: (email: string) => post<{ detail: string }>('/auth/magic-link/request/', { email }),
  })

  const out = useMutation({
    mutationFn: () => changingSession(() => post<{ detail: string }>('/auth/logout/')),
    onSuccess: () => {
      finishUsageSessionChange(null)
      releaseTab()
      queryClient.setQueryData(['me'], null)
      queryClient.clear()
    },
  })

  const value: AuthValue = {
    me: data ?? null,
    // «ещё не знаем»: ни ответа, ни отказа — включая паузу без связи
    isLoading: isPending,
    failed: isError,
    retry: () => void refetch(),
    login: (email, passwordValue) => password.mutateAsync({ email, password: passwordValue }),
    changePassword: (currentPassword, newPassword) =>
      change.mutateAsync({ current_password: currentPassword, new_password: newPassword }),
    setPasswordByToken: (token, newPassword) => setByToken.mutateAsync({ token, new_password: newPassword }),
    requestPasswordReset: async (email) => {
      await resetRequest.mutateAsync(email)
    },
    loginWithLink: async (token) => {
      await link.mutateAsync(token)
    },
    requestLink: async (email) => {
      await linkRequest.mutateAsync(email)
    },
    logout: async () => {
      await out.mutateAsync()
    },
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  // eslint-disable-next-line i18n-text -- ошибка разработчика в консоли, человеку не показывается
  if (!value) throw new Error('useAuth вне AuthProvider')
  return value
}
