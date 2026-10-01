/**
 * Данные «Портфолио» без разметки: подписи значений, поиск модели в реестре,
 * отправленные и ждущие решения предложения. Читают кабинет 11 («Портфолио»)
 * и разделы 8–10 «Олимпиады» и «Спорт» — один код, а не две копии.
 */
import type { MyProposal } from '../api/hooks'
import type { DomainField, DomainMeta, DomainModel } from '../api/types'
import { t, tk } from '../i18n'

/** Что видно в карточке: значение с подписью поля. */
export function shown(profile: Record<string, unknown> | undefined, field: DomainField): string {
  if (field.type === 'reference') return String(profile?.[`${field.name}_name`] || t('нет'))
  const value = profile?.[field.name]
  if (value === null || value === undefined || value === '') return t('нет')
  if (typeof value === 'boolean') return value ? t('Да') : t('Нет')
  const choice = field.choices?.find((c) => c.value === value)
  return choice ? choice.title : String(value)
}

/** Подписи доменов — ключи перевода: показываются через `t()`. */
export const DOMAIN_TITLE: Record<string, string> = {
  behavior: tk('Учёба и посещаемость'),
  admission: tk('Профиль поступления'),
  exam: tk('Ваши баллы'),
  talent: tk('Портфолио и таланты'),
  sport: tk('Спорт'),
}


/** Модель по метке — из реестра, который отдаёт сервер. */
export function modelOf(meta: DomainMeta | undefined, label: string): DomainModel | undefined {
  for (const domain of meta?.domains ?? []) {
    const found = domain.models.find((m) => m.label === label)
    if (found) return found
  }
  return undefined
}

/** Значения, отправленные и ждущие решения директора — по полям профилей. */
export function pendingByField(proposals: MyProposal[]): Record<string, string> {
  const out: Record<string, string> = {}
  for (const proposal of proposals) {
    if (proposal.status !== 'pending') continue
    for (const change of proposal.changes) {
      if (change.new_object_key) continue
      out[`${change.model}.${change.field}`] = change.new_value
    }
  }
  return out
}

/** Новые записи (достижения, соревнования), ждущие решения. */
export function pendingNewRows(proposals: MyProposal[], model: string): Record<string, string>[] {
  const groups: Record<string, Record<string, string>> = {}
  for (const proposal of proposals) {
    if (proposal.status !== 'pending') continue
    for (const change of proposal.changes) {
      if (!change.new_object_key || change.model !== model) continue
      const key = `${proposal.id}:${change.new_object_key}`
      groups[key] = { ...groups[key], [change.field]: change.new_value }
    }
  }
  return Object.values(groups)
}

/** Секции IELTS, которые ученик может внести с сертификата (фаза 63). */
export const CERT_SECTIONS = ['listening', 'reading', 'writing', 'speaking'] as const

export const SECTION_LABELS: Record<string, string> = {
  listening: 'Listening',
  reading: 'Reading',
  writing: 'Writing',
  speaking: 'Speaking',
}
