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
import { AddRowForm, ProfileCard } from '../components/PortfolioForms'
import { DateTile, EntryList, waitingState } from './PortfolioEntries'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'
import { modelOf, pendingByField, pendingNewRows } from './portfolioData'
import { formatMonthYear } from '../lib/format'
import StudentSport from './directors/StudentSport'
import './portfolio.css'
import './portfolio-layout.css'

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

  const waiting = pendingNewRows(myProposals, 'students.Competition')

  return (
    <div className="lay-screen">
      <ScreenHead title={t('Спорт')} subtitle={t('соревнования и мероприятия школы · записывайся участвовать или смотреть')} />
      {/* мероприятия школы и свои заявки — сверху, как в макете (24.10.2026) */}
      <StudentSport />
      <div className="lay-3 pfl-top">
        {/* вид спорта и уровень — главная карточка раздела, со светом по рамке */}
        <div className="pfl-beam pfl-beam--card card--beam">
          <ProfileCard code="sport" domains={domains} card={card} pending={pendingByField(myProposals)} />
        </div>
        <div className="lay-span2">
          <DataCard title={t('Мои соревнования')} note={owner ? t('Вносите сами, подтверждает {owner}', { owner }) : t('Вносите сами')} count={competitions.length + waiting.length}>
            <EntryList
              rows={[
                ...waiting.map((row, index) => ({
                  key: `pending-${index}`,
                  title: row.name ?? '',
                  meta: level(row.level ?? ''),
                  result: row.result ?? '',
                  lead: <DateTile value={row.date ?? null} />,
                  state: waitingState(),
                })),
                ...competitions.map((row) => ({
                  key: row.id,
                  title: row.name,
                  meta: [monthOf(row.date), level(row.level)].filter(Boolean).join(' · '),
                  result: row.result,
                  lead: <DateTile value={row.date} />,
                  byCurator: (row.entered_by_curator ?? []).length > 0,
                })),
              ]}
              empty={t('Соревнований пока нет')}
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
      </div>
    </div>
  )
}
