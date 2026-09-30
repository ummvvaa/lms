/**
 * «Спорт» — раздел ученика 8–10 (у 11 это вкладка «Портфолио»).
 *
 * Соревнования ученик вносит сам, вид спорта и уровень — предложением
 * в профиле спорта. Всё уходит на проверку директору спорта и до решения
 * стоит с пометкой «ждёт проверки».
 */
import { useMemo } from 'react'
import { useAchievementRows, useDomainMeta, useMyProfile, useMyProposals } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { AddRowForm, ProfileCard, RowsList } from '../components/PortfolioForms'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'
import { modelOf, pendingByField, pendingNewRows } from './portfolioData'
import { formatMonthYear } from '../lib/format'
import './portfolio.css'

const monthOf = (value: string | null) =>
  value ? formatMonthYear(value) : ''

export default function Sport() {
  const { me } = useAuth()
  const meta = useDomainMeta()
  const profile = useMyProfile()
  const rows = useAchievementRows(me?.student_id ?? null)
  const proposals = useMyProposals()
  const myProposals = useMemo(() => proposals.data?.results ?? [], [proposals.data])

  if (meta.isLoading || rows.isLoading || profile.isLoading) return <Loading kind="cards" />
  if (rows.error) return <ErrorNote error={rows.error} />

  const domains = meta.data?.domains ?? []
  const owner = domains.find((domain) => domain.code === 'sport')?.owner_name ?? ''
  const card = (profile.data ?? {}) as unknown as Record<string, Record<string, unknown>>
  const competitionModel = modelOf(meta.data, 'students.Competition')
  const competitions = rows.data?.competitions ?? []
  const level = (value: string) =>
    competitionModel?.fields.find((f) => f.name === 'level')?.choices?.find((c) => c.value === value)?.title ?? ''

  return (
    <div>
      <ScreenHead title={t('Спорт')} subtitle={owner ? t('Вносите сами, подтверждает {owner}', { owner }) : t('Вносите сами')} />
      <div className="portfolio__two">
        <div className="portfolio__main">
          <DataCard title={t('Соревнования')} count={competitions.length}>
            <RowsList
              rows={competitions.map((row) => ({
                id: row.id,
                label: row.name,
                note: [monthOf(row.date), level(row.level), row.result].filter(Boolean).join(' · '),
                byCurator: (row.entered_by_curator ?? []).length > 0,
              }))}
              pendingRows={pendingNewRows(myProposals, 'students.Competition').map((row) => ({
                label: row.name ?? '',
                note: row.result ?? '',
              }))}
              emptyText={t('Соревнований пока нет')}
            />
            {competitionModel && (
              <AddRowForm
                model="students.Competition"
                fields={competitionModel.fields.filter((f) => f.student_proposable && f.name !== 'proof_url')}
                submitLabel={t('Добавить соревнование')}
                withFile
              />
            )}
          </DataCard>
        </div>
        <div className="portfolio__side">
          <ProfileCard code="sport" domains={domains} card={card} pending={pendingByField(myProposals)} />
        </div>
      </div>
    </div>
  )
}
