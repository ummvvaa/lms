/**
 * Сессия пользователя.
 *
 * Вход по почте и паролю; сессия живёт в httpOnly cookie, токенов на фронте
 * нет вовсе. Одноразовые ссылки остались для приглашений, сброса пароля
 * и входа выпускников.
 */
import { createContext, useContext, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from '../api/client'
import type { Me } from '../api/types'

interface AuthValue {
  me: Me | null
  isLoading: boolean
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

  const { data, isLoading } = useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        return await get<Me>('/auth/me/')
      } catch {
        return null
      }
    },
    retry: false,
    staleTime: 60_000,
  })

  const setMe = (me: Me | null) => {
    queryClient.setQueryData(['me'], me)
    // права и состав экранов зависят от роли — прежние ответы больше не годятся
    void queryClient.invalidateQueries({ queryKey: ['domains'] })
  }

  const password = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      post<Me>('/auth/login/', { email, password }),
    onSuccess: setMe,
  })

  const change = useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      post<Me>('/auth/password/change/', body),
    onSuccess: setMe,
  })

  const setByToken = useMutation({
    mutationFn: (body: { token: string; new_password: string }) => post<Me>('/auth/password/set/', body),
    onSuccess: setMe,
  })

  const resetRequest = useMutation({
    mutationFn: (email: string) => post<{ detail: string }>('/auth/password/reset/', { email }),
  })

  const link = useMutation({
    mutationFn: (token: string) => post<Me>('/auth/magic-link/redeem/', { token }),
    onSuccess: setMe,
  })

  const linkRequest = useMutation({
    mutationFn: (email: string) => post<{ detail: string }>('/auth/magic-link/request/', { email }),
  })

  const out = useMutation({
    mutationFn: () => post<{ detail: string }>('/auth/logout/'),
    onSuccess: () => {
      queryClient.setQueryData(['me'], null)
      queryClient.clear()
    },
  })

  const value: AuthValue = {
    me: data ?? null,
    isLoading,
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
  if (!value) throw new Error('useAuth вне AuthProvider')
  return value
}
