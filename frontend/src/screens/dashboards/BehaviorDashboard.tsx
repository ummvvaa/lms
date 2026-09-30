/**
 * Кабинет Салтанат — школа (фаза 49).
 *
 * Первым идёт «Кому позвонить сегодня»: ученик, причина одной фразой,
 * чип срочности и телефон родителя прямо в строке — иначе звонок
 * откладывается до поисков контакта. Список собирается из пропусков,
 * моков, активности и дедлайнов, правила лежат справочником.
 *
 * Посещаемость и замечания она по-прежнему вносит сама: этого ученик
 * про себя не рассказывает.
 */
import { useNavigate } from 'react-router-dom'
import { useCabinet } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import OnboardingQueue from '../../components/OnboardingQueue'
import PendingQueue from '../../components/PendingQueue'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard, EmptyNote, ErrorNote, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'
import { CabinetColumns, CabinetStats } from './cabinet'
import './student.css'

interface BehaviorCabinet {
  title: string
  owner: string
  stats: Parameters<typeof CabinetStats>[0]['stats']
  calls: {
    student_id: number
    student: string
    group: string
    urgency: string
    urgency_title: string
    reason: string
    contact: { name: string; phone: string } | null
  }[]
  groups: { id: number; code: string; students_count: number; risk: number }[]
  talks: { written: number; waiting: number }
}

const URGENCY: Record<string, Tone> = { now: 'bad', today: 'warn', week: 'neutral' }

export default function BehaviorDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useCabinet()
  const schoolIsEmpty = useSchoolIsEmpty()

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Школа')}
        hint={t('Здесь появится список тех, кому стоит позвонить')}
        what={t('Он собирается из пропусков, Mock Test, активности и дедлайнов.')}
        detail={t('Правила и пороги вы ведёте сами в разделе «Правила обзвона».')}
        guide
      />
    )

  const cabinet = data as unknown as BehaviorCabinet

  return (
    <div>
      <ScreenHead
        title={t(cabinet.title)}
        subtitle={t(cabinet.owner)}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate('/contacts')}>
              {t('Контакты родителей')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => navigate('/call-rules')}>
              {t('Правила обзвона')}
            </Button>
            {/* посещаемость вносит куратор; директор школы её читает —
                журналом группы за месяц и листом за день */}
            <Button size="sm" onClick={() => navigate('/attendance?view=journal')}>
              {t('Журнал посещаемости')}
            </Button>
          </>
        }
      />

      <GettingStarted />

      {/* сетка — как у остальных директоров: показатели полосой сверху,
          ниже основная колонка и узкая правая */}
      <CabinetStats stats={cabinet.stats} />

      <CabinetColumns
        main={
          <DataCard
            title={t('Кому позвонить сегодня')}
            count={cabinet.calls.length}
          >
            {cabinet.calls.length === 0 && (
              <p className="muted rows__empty">
                {t('Сегодня звонить некому — ни одно правило не сработало.')}
              </p>
            )}
            {cabinet.calls.map((call) => (
              <div key={call.student_id} className="cabinet__row">
                <span className="cabinet__rowtext">
                  <b>
                    {call.student}
                    {call.group ? ` · ${call.group}` : ''}
                  </b>
                  <span className="muted">{t(call.reason)}</span>
                </span>
                <Chip tone={URGENCY[call.urgency] ?? 'neutral'}>{t(call.urgency_title)}</Chip>
                {call.contact ? (
                  <Button variant="outline" size="sm" nativeButton={false} render={<a href={`tel:${call.contact.phone}`} />}>
                    {call.contact.name} · {call.contact.phone}
                  </Button>
                ) : (
                  <Button variant="ghost" size="sm" onClick={() => navigate('/contacts')}>
                    {t('Контакта нет')}
                  </Button>
                )}
              </div>
            ))}
          </DataCard>
        }
        aside={
          <>
            <PendingQueue note={tk('Контакты родителей и то, что ученики рассказали о себе.')} />
            {/* анкета первого входа — ниже очереди и отдельно: она уже в профиле
                и решения не ждёт (D16) */}
            <OnboardingQueue />

            {/* группы — в правой колонке под очередью: левая с обзвоном длинная,
                и правая раньше кончалась на середине экрана */}
            <DataCard title={t('Учебные группы')}>
              {cabinet.groups.length === 0 && <EmptyNote what={tk('групп пока нет')} who={tk('заводит администратор')} />}
              <Rows>
                {cabinet.groups.map((group) => (
                  <Row
                    key={group.id}
                    lead={<b className="stu__slot">{group.code.slice(0, 2)}</b>}
                    title={group.code}
                    note={tn(group.students_count, '{n} ученик|{n} ученика|{n} учеников')}
                    right={
                      <Chip tone={group.risk === 0 ? 'good' : 'bad'} size="sm" className="num">
                        {t('{n} в риске', { n: group.risk })}
                      </Chip>
                    }
                    to={`/table?group=${encodeURIComponent(group.code)}`}
                  />
                ))}
              </Rows>
            </DataCard>

            <DataCard title={t('Разговоры за неделю')}>
              <Rows>
                <Row title={t('Записано')} note={tn(cabinet.talks.written, '{n} разговор|{n} разговора|{n} разговоров')} />
                <Row
                  title={t('Ждут вашего ответа')}
                  note={tn(cabinet.talks.waiting, '{n} вопрос от учеников|{n} вопроса от учеников|{n} вопросов от учеников')}
                  onOpen={() => navigate('/roadmap')}
                  openLabel={t('Открыть')}
                />
              </Rows>
            </DataCard>
          </>
        }
      />
    </div>
  )
}
