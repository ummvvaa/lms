/**
 * «Олимпиады» — раздел ученика 8–10 (у 11 это вкладка «Портфолио»).
 *
 * Ученик вносит участие сам: название, предмет, дату, описание и скан
 * диплома. Запись уходит предложением директору талантов и до его решения
 * в карточке не появляется — в списке она стоит с пометкой «ждёт проверки».
 */
import { useMemo } from 'react'
import { useAchievementRows, useDomainMeta, useMyProposals } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { AddRowForm } from '../components/PortfolioForms'
import { DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../components/ui'
import { EntryList, Medal, waitingState } from './PortfolioEntries'
import { t } from '../i18n'
import { todayAlmaty } from '../lib/dates'
import { modelOf, pendingNewRows } from './portfolioData'
import { formatMonthYear } from '../lib/format'
import './portfolio.css'
import './portfolio-layout.css'

/** «март 2026» — месяц и год участия. */
const monthOf = (value: string | null) =>
  value ? formatMonthYear(value) : ''

export default function Olympiads() {
  const { me } = useAuth()
  const meta = useDomainMeta()
  const rows = useAchievementRows(me?.student_id ?? null)
  const proposals = useMyProposals()
  const myProposals = useMemo(() => proposals.data?.results ?? [], [proposals.data])

  if (meta.isLoading || rows.isLoading) return <Loading kind="cards" />
  if (rows.error) return <ErrorNote error={rows.error} />

  const owner = meta.data?.domains.find((domain) => domain.code === 'talent')?.owner_name ?? ''
  const activityModel = modelOf(meta.data, 'students.Activity')
  const today = todayAlmaty()
  const olympiads = rows.data?.activities ?? []
  const waiting = pendingNewRows(myProposals, 'students.Activity').filter((row) => row.category === 'olympiad')

  const confirmed = olympiads.filter((row) => row.is_confirmed).length
  // ждут решения: и отправленные предложения, и записи без отметки директора
  const unconfirmed = olympiads.filter((row) => !row.is_confirmed && !(row.date && row.date > today)).length
  const waitingCount = waiting.length + unconfirmed

  return (
    <div className="lay-screen">
      <ScreenHead title={t('Олимпиады')} subtitle={owner ? t('Вносите сами, подтверждает {owner}', { owner }) : t('Вносите сами')} />
      <div className="lay-3">
        <div className="pfl-beam card--beam">
          <Kpi label={t('Участий')} value={olympiads.length + waiting.length || null} none={t('нет')} note={t('даже школьный этап считается')} />
        </div>
        <Kpi label={t('Подтверждено')} value={confirmed || null} none={t('нет')} />
        <Kpi
          label={t('Ждут подтверждения')}
          value={waitingCount || null}
          none={t('нет')}
          chip={waitingCount > 0 ? { label: t('на проверке у директора'), tone: 'warn' } : undefined}
        />
      </div>
      <DataCard title={t('Мои участия')} count={olympiads.length + waiting.length}>
        <EntryList
          rows={[
            ...waiting.map((row, index) => ({
              key: `pending-${index}`,
              title: row.title ?? '',
              meta: monthOf(row.date ?? null),
              lead: <Medal />,
              state: waitingState(),
            })),
            ...olympiads.map((row) => ({
              key: row.id,
              title: row.title,
              meta: [monthOf(row.date), row.subject_name].filter(Boolean).join(' · '),
              lead: <Medal on={row.is_confirmed} />,
              byCurator: (row.entered_by_curator ?? []).length > 0,
              state:
                row.date && row.date > today
                  ? { label: t('скоро'), tone: 'info' as const }
                  : row.is_confirmed
                    ? { label: t('подтверждено'), tone: 'good' as const }
                    : { label: t('ждёт подтверждения'), tone: 'warn' as const },
            })),
          ]}
          empty={t('Олимпиад пока нет — даже школьный этап считается')}
        />
        <p className="muted t-note pfl-addnote">
          {t('Название, предмет, дата и скан диплома. После подтверждения запись попадёт в карточку.')}
        </p>
        {activityModel && (
          <AddRowForm
            model="students.Activity"
            fields={activityModel.fields.filter(
              (f) => f.student_proposable && !['category', 'proof_url'].includes(f.name),
            )}
            fixed={{ category: 'olympiad' }}
            submitLabel={t('Добавить олимпиаду')}
            withFile
          />
        )}
      </DataCard>
    </div>
  )
}
