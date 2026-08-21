/**
 * Типы API.
 *
 * Файл `schema.ts` генерируется из OpenAPI-схемы DRF командой
 * `npm run gen:api` и в репозиторий не коммитится. Здесь — только
 * то, на что опирается каркас приложения.
 */

export type Role =
  | 'student'
  | 'director_behavior'
  | 'director_admission'
  | 'director_exam'
  | 'director_talent'
  | 'director_sport'
  | 'admin'

export type DomainCode = 'behavior' | 'admission' | 'exam' | 'talent' | 'sport'

export interface Identity {
  id: number
  provider: string
  provider_title: string
  email: string
  is_primary: boolean
  last_login_at: string | null
}

export interface Me {
  id: number
  email: string
  full_name: string
  role: Role
  role_title: string
  domain: DomainCode | null
  domain_title: string | null
  student_id: number | null
  identities: Identity[]
}

export interface DomainField {
  name: string
  title: string
  type: 'string' | 'integer' | 'number' | 'boolean' | 'date' | 'datetime' | 'reference'
  internal_label: boolean
  choices?: { value: string; title: string }[]
}

export interface DomainModel {
  label: string
  fields: DomainField[]
}

export interface Domain {
  code: DomainCode
  title: string
  emoji: string
  owner_name: string
  role: Role
  is_mine: boolean
  models: DomainModel[]
}

export interface DomainMeta {
  role: Role
  role_title: string
  my_domain: DomainCode | null
  domains: Domain[]
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}
