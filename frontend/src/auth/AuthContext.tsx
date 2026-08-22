/**
 * Состояние входа. Источник правды — серверная сессия: при загрузке
 * спрашиваем /api/auth/me/, поэтому сессия переживает перезагрузку страницы.
 * Токен Microsoft здесь не хранится и в localStorage не попадает.
 */
import { createContext, useContext, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, ApiError } from '../api/client'
import type { Me } from '../api/types'
import { acquireEntraToken } from './msal'

interface AuthValue {
  me: Me | null
  isLoading: boolean
  loginWithMicrosoft: () => Promise<void>
  loginWithPassword: (email: string, password: string) => Promise<void>
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
      } catch (error) {
        // 401/403 — просто «не вошёл», это не ошибка загрузки
        if (error instanceof ApiError && [401, 403].includes(error.status)) return null
        throw error
      }
    },
    retry: false,
    staleTime: 60_000,
  })

  const setMe = (me: Me | null) => queryClient.setQueryData(['me'], me)

  const microsoft = useMutation({
    mutationFn: async () => {
      const idToken = await acquireEntraToken()
      return post<Me>('/auth/entra/', { id_token: idToken })
    },
    onSuccess: setMe,
  })

  const password = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      post<Me>('/auth/local/', { email, password }),
    onSuccess: setMe,
  })

  const link = useMutation({
    mutationFn: (token: string) => post<Me>('/auth/magic-link/redeem/', { token }),
    onSuccess: setMe,
  })

  const requestLink = useMutation({
    mutationFn: (email: string) => post<void>('/auth/magic-link/request/', { email }),
  })

  const logout = useMutation({
    mutationFn: () => post<void>('/auth/logout/'),
    onSuccess: () => {
      setMe(null)
      queryClient.clear()
    },
  })

  const value: AuthValue = {
    me: data ?? null,
    isLoading,
    loginWithMicrosoft: async () => {
      await microsoft.mutateAsync()
    },
    loginWithPassword: async (email, passwordValue) => {
      await password.mutateAsync({ email, password: passwordValue })
    },
    loginWithLink: async (token) => {
      await link.mutateAsync(token)
    },
    requestLink: async (email) => {
      await requestLink.mutateAsync(email)
    },
    logout: async () => {
      await logout.mutateAsync()
    },
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth вызван вне AuthProvider')
  return value
}
