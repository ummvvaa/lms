/**
 * Кабинет Армана — таланты (фаза 49).
 *
 * Первым — материалы на проверке: это его основная работа. Чужой
 * материал без подтверждённых прав помечен отдельно: неопубликованные
 * задания олимпиад и сканы чужих учебников школе хранить у себя не стоит.
 */
import { useNavigate } from 'react-router-dom'
import { useCabinet } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import OnboardingQueue from '../../components/OnboardingQueue'
import PendingQueue from '../../components/PendingQueue'
import { Row, Rows } from '../../components/patterns'
import { Bar, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { CabinetColumns, CabinetStats } from './cabinet'

interface TalentCabinet {
  title: string
  owner: string
  stats: Parameters<typeof CabinetStats>[0]['stats']
  review: { id: number; title: string; author: string; source: string; files: number; rights_ok: boolean }[]
  olympiads: { title: string; date: string; students: number }[]
  by_subject: { name: string; students: number }[]
}

export default function TalentDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useCabinet()
  const schoolIsEmpty = useSchoolIsEmpty()

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Таланты')}
        hint={t('Здесь появятся материалы и олимпиады')}
        what={t('Материалы выкладывают ученики группы, проверяете их вы.')}
        detail={t('Начните с предметов и отбора в олимпиадную группу.')}
        guide
      />
    )

  const cabinet = data as unknown as TalentCabinet
  const maxSubject = Math.max(1, ...cabinet.by_subject.map((row) => row.students))

  return (
    <div>
      <ScreenHead
        title={t(cabinet.title)}
        subtitle={t(cabinet.owner)}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate('/subjects')}>
              {t('Предметы')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => navigate('/materials')}>
              {t('Библиотека')}
            </Button>
            <Button size="sm" onClick={() => navigate('/olympiad-group')}>
              {t('Олимпиадная группа')}
            </Button>
          </>
        }
      />

      <GettingStarted />
      <CabinetStats stats={cabinet.stats} />

      <CabinetColumns
        main={
          <>
            <DataCard
              title={t('Материалы на проверке')}
              note={t('Ваша основная работа — модерация')}
              accent="warn"
              count={cabinet.review.length}
            >
              {cabinet.review.length === 0 && (
                <p className="muted rows__empty">{t('Очередь пуста — всё проверено')}</p>
              )}
              {cabinet.review.map((row) => (
                <div key={row.id} className="cabinet__row">
                  <span className="cabinet__rowtext">
                    <b>{row.title}</b>
                    <span className="muted">
                      {row.author} · {t(row.source)} · {row.files} {t('файл.')}
                    </span>
                  </span>
                  {!row.rights_ok && <Badge variant="warn">{t('Проверить права')}</Badge>}
                  <Button variant="outline" size="sm" onClick={() => navigate(`/materials/${row.id}`)}>
                    {t('Открыть')}
                  </Button>
                </div>
              ))}
            </DataCard>

            <OnboardingQueue />
            <PendingQueue note="Достижения и олимпиады, которые внесли ученики." />
          </>
        }
        aside={
          <>
            <DataCard title={t('Ближайшие олимпиады')} note={t('И сколько участников')} accent="indigo">
              {cabinet.olympiads.length === 0 && (
                <p className="muted rows__empty">{t('Ближайших олимпиад не записано')}</p>
              )}
              <Rows>
                {cabinet.olympiads.map((row) => (
                  <Row
                    key={`${row.title}-${row.date}`}
                    title={row.title}
                    note={`${new Date(row.date).toLocaleDateString('ru')} · ${row.students} ${t('чел.')}`}
                  />
                ))}
              </Rows>
            </DataCard>

            <DataCard title={t('Олимпиадная группа')} note={t('По предметам')} accent="teal">
              {cabinet.by_subject.length === 0 && (
                <p className="muted rows__empty">{t('Олимпиад пока никто не отметил')}</p>
              )}
              {cabinet.by_subject.map((row) => (
                <div key={row.name} className="cabinet__barrow">
                  <div className="cabinet__barhead">
                    <span>{row.name}</span>
                    <b className="num">{row.students}</b>
                  </div>
                  <Bar percent={(row.students / maxSubject) * 100} color="var(--warn)" />
                </div>
              ))}
            </DataCard>
          </>
        }
      />
    </div>
  )
}
