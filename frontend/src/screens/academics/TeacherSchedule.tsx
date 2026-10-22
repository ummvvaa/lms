/**
 * Расписание учителя: неделя своих уроков и замен, составы, просьбы о переносе.
 *
 * Нажатие на урок открывает отметку. «Попросить перенос» уходит Кымбат.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useAcadLessons, useAcadMeta, useRequests, useSendRequest, useTeacherProfile, type AcadLesson } from '../../api/academics'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Bar, Chip, counted, DataCard, ErrorNote, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tn } from '../../i18n'
import { dateWords, useWeekStart, WeekGrid, WeekNav, weekStart } from './shared'

const REQUEST_TONE: Record<string, Tone> = { pending: 'warn', approved: 'good', rejected: 'bad' }

/** Окно просьбы о переносе: какой урок, куда удобно, причина. */
export function RequestDialog({ lessons, initial, onClose }: { lessons: AcadLesson[]; initial?: number; onClose: () => void }) {
  const send = useSendRequest()
  const [lesson, setLesson] = useState(String(initial ?? lessons[0]?.id ?? ''))
  const [wanted, setWanted] = useState('')
  const [why, setWhy] = useState('')
  const [error, setError] = useState('')
  const submit = () => {
    if (!why.trim()) {
      setError(t('Напишите причину'))
      return
    }
    send.mutate(
      { lesson: Number(lesson), wanted, reason: why },
      {
        onSuccess: () => {
          toast.success(t('Просьба ушла Кымбат'))
          onClose()
        },
        onError: (e) => setError(e.message),
      },
    )
  }
  return (
    <Modal title={t('Попросить перенос')} note={t('Просьба уйдёт Кымбат, ответ придёт уведомлением')} onClose={onClose}>
      <Field
        kind="select"
        name="lesson"
        label={t('Какой урок')}
        value={lesson}
        onChange={setLesson}
        options={lessons.map((row) => ({ value: String(row.id), title: `${row.weekday}, ${dateWords(row.date)}, ${t('{slot} урок', { slot: row.slot })} · ${row.subject.short_title} · ${row.cohort.name}` }))}
      />
      <Field kind="text" name="wanted" label={t('Куда удобно')} value={wanted} onChange={setWanted} placeholder={t('Например: на 7 урок того же дня')} />
      <Field kind="textarea" name="why" label={t('Причина')} value={why} onChange={setWhy} rows={3} error={error || undefined} />
      <div className="acad__actions">
        <Button onClick={submit} disabled={send.isPending || !lesson}>
          {t('Отправить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

/**
 * Полоса текущего урока: идущий или следующий урок недели и кнопка отметки,
 * полоса — сколько уроков сегодня уже позади. Всё из уроков недели на экране.
 */
function NowStrip({ lessons, today, onOpen }: { lessons: AcadLesson[]; today: string; onOpen: (lesson: AcadLesson) => void }) {
  const live = lessons.filter((lesson) => lesson.is_live).sort((a, b) => a.date.localeCompare(b.date) || a.slot - b.slot)
  const todays = live.filter((lesson) => lesson.date === today)
  const now = todays.find((lesson) => lesson.state === 'now')
  const next = live.find((lesson) => lesson.date > today || (lesson.date === today && lesson.state === 'future'))
  const shown = now ?? next
  if (!shown) return null
  const done = todays.filter((lesson) => lesson.state === 'past').length
  const when = shown.date === today ? t('{slot} урок', { slot: shown.slot }) : `${shown.weekday}, ${dateWords(shown.date)}, ${t('{slot} урок', { slot: shown.slot })}`
  return (
    <section className="card card-pad card--beam stusch__now tsched__now">
      <Chip tone="accent">{now ? t('сейчас') : t('дальше')}</Chip>
      <span className="stusch__now-what">{[when, shown.subject.title, shown.cohort.name, shown.room, shown.kind !== 'fo' ? shown.kind_label : ''].filter(Boolean).join(' · ')}</span>
      {todays.length > 0 && (
        <>
          <div className="stusch__now-bar">
            <Bar percent={(done / todays.length) * 100} />
          </div>
          <span className="stusch__now-count num">{t('уроков сегодня: {done} из {total}', { done, total: todays.length })}</span>
        </>
      )}
      <Button variant={now && !now.marked ? 'default' : 'outline'} onClick={() => onOpen(shown)}>
        {now && !now.marked ? t('Отметить') : t('Открыть')}
      </Button>
    </section>
  )
}

export default function TeacherSchedule() {
  const navigate = useNavigate()
  const meta = useAcadMeta()
  const today = meta.data?.today ?? ''
  const [start, setStart] = useWeekStart()
  const from = start || (today ? weekStart(today) : '')
  const week = useAcadLessons({ from }, Boolean(from))
  const profile = useTeacherProfile()
  const requests = useRequests()
  const [asking, setAsking] = useState(false)

  if (meta.isLoading || week.isLoading || profile.isLoading) return <Loading kind="cards" />
  if (week.error) return <ErrorNote error={week.error} />
  if (!week.data || !meta.data) return null

  const teacher = profile.data?.teacher
  const upcoming = week.data.lessons.filter((lesson) => lesson.is_live && lesson.date >= today)
  const courses = profile.data
  const rows = requests.data?.rows ?? []

  if (profile.data && profile.data.journals === 0 && week.data.lessons.length === 0)
    return (
      <div className="lay-screen">
        <ScreenHead title={t('Расписание')} />
        <DataCard title={t('Уроков нет')} empty={t('вас ещё не поставили в расписание')} />
      </div>
    )

  const open = (lesson: AcadLesson) => navigate(`/lessons/${lesson.id}`)

  return (
    <div className="lay-screen stusch tsched">
      <ScreenHead
        title={t('Расписание')}
        subtitle={`${tn(profile.data?.hours ?? 0, '{n} урок в неделю|{n} урока в неделю|{n} уроков в неделю')} · ${counted(courses?.journals ?? 0, 'журнал|журнала|журналов')} · ${teacher?.room ? t('кабинет {room}', { room: teacher.room }) : t('кабинет не закреплён')}`}
        actions={
          <>
            <WeekNav start={from} today={today} onChange={setStart} />
            <Button variant="outline" onClick={() => setAsking(true)} disabled={upcoming.length === 0}>
              {t('Попросить перенос')}
            </Button>
          </>
        }
      />
      <NowStrip lessons={week.data.lessons} today={today} onOpen={open} />
      <section className="card card-pad stusch__week">
        <WeekGrid
          week={week.data}
          perspective="teacher"
          onOpen={open}
          unmarkedIds={week.data.lessons.filter((lesson) => lesson.is_live && lesson.state === 'past' && !lesson.marked).map((lesson) => lesson.id)}
        />
        <div className="stusch__legend">
          <Chip tone="info">{t('подгруппа')}</Chip>
          <Chip tone="accent">{t('поток')}</Chip>
          <Chip tone="warn">{t('замена или перенос')}</Chip>
          <span className="t-note">{t('нажмите на урок — откроется отметка')}</span>
        </div>
      </section>
      <DataCard title={t('Просьбы о переносе')} count={rows.length || undefined} empty={rows.length === 0 && t('вы ничего не просили')}>
        <Rows>
          <ShowAll>
            {rows.map((row) => (
              <Row
                key={row.id}
                title={`${dateWords(row.lesson.date)}, ${t('{slot} урок', { slot: row.lesson.slot })} · ${row.lesson.subject.short_title}: ${row.wanted || t('на свободное время')}`}
                note={`${row.reason}${row.answer ? ` · ${t('ответ:')} ${row.answer}` : ''}`}
                right={<Chip tone={REQUEST_TONE[row.status] ?? 'neutral'}>{t(row.status_title)}</Chip>}
              />
            ))}
          </ShowAll>
        </Rows>
      </DataCard>
      {asking && <RequestDialog lessons={upcoming} onClose={() => setAsking(false)} />}
    </div>
  )
}
