/**
 * Реестровая карточка ученика: кто это, группа, почта, телефон, выпуск.
 *
 * Здесь только чтение: ФИО, группа и почта правятся на «Пользователях» —
 * одно место о человеке (решение владельца, 11.10.2026), второе место для
 * тех же полей разошлось бы с первым. Доменных полей здесь нет и быть
 * не может — их правят директора у себя (инвариант №1).
 */
import { useNavigate } from 'react-router'
import type { StudentCard } from '../api/hooks'
import { DataCard, Kpi } from './ui'
import { StatRow } from './patterns'
import { t } from '../i18n'
import { Button } from './ui/button'

export default function StudentRegistryCard({
  card,
  canEdit,
  className,
}: {
  card: StudentCard
  canEdit: boolean
  /** место карточки в раскладке экрана (фаза 77) */
  className?: string
}) {
  const navigate = useNavigate()
  const contacts = [card.email, card.phone].filter(Boolean).join(' · ')
  const target = `/users?search=${encodeURIComponent(card.full_name)}${card.user ? `&edit=${card.user}` : ''}`
  return (
    <DataCard
      title={t('Кто это')}
      note={t('Реестровая карточка школы')}
      className={className}
      hint={t(
        'Имя, группа, почта и телефон правятся на «Пользователях». Доменные данные — баллы, посещаемость, портфолио — ведут директора у себя, здесь их нет.',
      )}
      right={
        canEdit ? (
          <Button variant="outline" size="sm" onClick={() => navigate(target)}>
            {t('Изменить на «Пользователях»')}
          </Button>
        ) : undefined
      }
    >
      <StatRow>
        <Kpi value={card.group_code} label={t('Учебная группа')} />
        <Kpi value={card.graduation_year} label={t('Год выпуска')} />
      </StatRow>
      <p className="muted rows__empty">{contacts || t('почты и телефона нет')}</p>
    </DataCard>
  )
}
