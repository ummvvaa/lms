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
import { AddRowForm, RowsList } from '../components/PortfolioForms'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'
import { todayAlmaty } from '../lib/dates'
import { modelOf, pendingNewRows } from './portfolioData'
import { formatMonthYear } from '../lib/format'
import './portfolio.css'

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

  return (
    <div>
      <ScreenHead title={t('Олимпиады')} subtitle={`${t('Вносите сами, подтверждает')} ${owner}`.trim()} />
      <div className="portfolio__two">
        <div className="portfolio__main">
          <DataCard title={t('Мои участия')} count={olympiads.length}>
            <RowsList
              rows={olympiads.map((row) => ({
                id: row.id,
                label: row.title,
                note: [
                  monthOf(row.date),
                  row.subject_name,
                  row.date && row.date > today
                    ? t('скоро')
                    : row.is_confirmed
                      ? t('подтверждено')
                      : t('ждёт подтверждения'),
                ]
                  .filter(Boolean)
                  .join(' · '),
                byCurator: (row.entered_by_curator ?? []).length > 0,
              }))}
              pendingRows={waiting.map((row) => ({ label: row.title ?? '', note: monthOf(row.date ?? null) }))}
              emptyText={t('Олимпиад пока нет — даже школьный этап считается')}
            />
          </DataCard>
        </div>
        <div className="portfolio__side">
          <DataCard title={t('Добавить')}>
            <p className="muted t-note">
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
      </div>
    </div>
  )
}
