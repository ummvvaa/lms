/**
 * Расписание у Кымбат и администратора: неделя по группе, учителю или
 * кабинету с правкой уроков, накладки, просьбы учителей, замены и отмены,
 * последние изменения.
 *
 * Образец — `route(['kymbat', 'admin'], '/schedule')` референса.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useAcadMeta, useDecideRequest, useScheduleWeek, type AcadLesson, type ScheduleWeek } from '../../api/academics'
import { useAuth } from '../../auth/AuthContext'
import EditDrawer from '../../components/EditDrawer'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows, Segmented, ShowAll, StatRow } from '../../components/patterns'
import { counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import LessonDrawer, { LessonForm } from './LessonDrawer'
import ScheduleImport from './ScheduleImport'
import { dateWords, useWeekStart, WeekGrid, WeekNav, weekStart } from './shared'

type View = 'group' | 'teacher' | 'room'

function RejectDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const decide = useDecideRequest()
  const [answer, setAnswer] = useState('')
  const [error, setError] = useState('')
  return (
    <Modal title={t('Отклонить просьбу')} onClose={onClose}>
      <Field kind="textarea" name="answer" label={t('Что ответить учителю')} value={answer} onChange={setAnswer} rows={3} autoFocus error={error || undefined} />
      <div className="acad__actions">
        <Button
          variant="destructive"
          onClick={() =>
            decide.mutate(
              { id, approve: false, answer },
              {
                onSuccess: () => {
                  toast.success(t('Просьба отклонена, учитель увидит ответ'))
                  onClose()
                },
                onError: (e) => setError(e.message),
              },
            )
          }
          disabled={decide.isPending}
        >
          {t('Отклонить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

function ApproveDialog({ request, onClose }: { request: ScheduleWeek['requests'][number]; onClose: () => void }) {
  const meta = useAcadMeta()
  const decide = useDecideRequest()
  const [date, setDate] = useState(request.lesson.date)
  const [slot, setSlot] = useState(String(request.lesson.slot))
  const [force, setForce] = useState(false)
  const [error, setError] = useState('')
  return (
    <Modal title={t('Одобрить перенос')} note={`${request.teacher.full_name}: ${request.wanted || t('на свободное время')} · ${request.reason}`} onClose={onClose}>
      <Field.Row>
        <Field kind="date" name="date" label={t('Новая дата')} value={date} onChange={setDate} />
        <Field kind="select" name="slot" label={t('Урок')} value={slot} onChange={setSlot} options={(meta.data?.bells ?? []).map((b) => ({ value: String(b.number), title: `${b.number} ${t('урок')} · ${b.starts.slice(0, 5)}` }))} />
      </Field.Row>
      <Field kind="checkbox" name="force" label={t('Перенести даже с накладкой')} checked={force} onChange={setForce} />
      {error && <p className="acad__note">{error}</p>}
      <div className="acad__actions">
        <Button
          onClick={() =>
            decide.mutate(
              { id: request.id, approve: true, date, slot: Number(slot), force },
              {
                onSuccess: () => {
                  toast.success(t('Одобрено: урок перенесён, учитель получит уведомление'))
                  onClose()
                },
                onError: (e) => setError(e.message),
              },
            )
          }
          disabled={decide.isPending}
        >
          {t('Одобрить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

export default function ScheduleEditor() {
  const navigate = useNavigate()
  const { me } = useAuth()
  const [importing, setImporting] = useState(false)
  const meta = useAcadMeta()
  const today = meta.data?.today ?? ''
  const [start, setStart] = useWeekStart()
  const [view, setView] = useState<View>('group')
  const [key, setKey] = useState('')
  const from = start || (today ? weekStart(today) : '')
  const week = useScheduleWeek({ from: from || undefined, view, key: key || undefined })
  const [opened, setOpened] = useState<AcadLesson | null>(null)
  const [adding, setAdding] = useState<{ date: string; slot: number } | null>(null)
  const [reject, setReject] = useState<number | null>(null)
  const [approve, setApprove] = useState<ScheduleWeek['requests'][number] | null>(null)

  if (meta.isLoading || (week.isLoading && !week.data)) return <Loading kind="cards" />
  if (week.error) return <ErrorNote error={week.error} />
  if (!week.data) return null
  const data = week.data
  const keyOptions =
    view === 'group'
      ? data.groups.map((g) => ({ value: g.code, title: g.code }))
      : view === 'teacher'
        ? data.teachers.map((row) => ({ value: String(row.id), title: row.full_name }))
        : data.rooms.map((room) => ({ value: room, title: room }))
  const openedConflicts = opened ? data.conflicts.filter((c) => c.lesson === opened.id || c.other === opened.id) : []

  return (
    <div>
      <ScreenHead
        title={t('Расписание')}
        subtitle={`${counted(data.series_total, ['урок', 'урока', 'уроков'])} ${t('в неделю')} · ${counted(data.teachers_total, ['учитель', 'учителя', 'учителей'])} · ${counted(data.groups_total, ['группа', 'группы', 'групп'])}`}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate('/cohorts')}>
              {t('Подгруппы и потоки')}
            </Button>
            {/* импорт заводит учётки сотрудников — только администратор */}
            {me?.role === 'admin' && (
              <Button variant="outline" size="sm" onClick={() => setImporting(true)}>
                {t('Импорт расписания')}
              </Button>
            )}
            <Button size="sm" onClick={() => setAdding({ date: from > today ? from : today, slot: 1 })}>
              {t('Добавить урок')}
            </Button>
          </>
        }
      />
      {data.empty ? (
        // неделя во всю ширину и высоту: без боковой колонки пятница не режется
        <div className="acad__stack">
          <DataCard title={t('Расписание пустое')} empty={t('ни одного урока ещё не заведено')} emptyAction={<Button variant="secondary" size="sm" onClick={() => setAdding({ date: today, slot: 1 })}>{t('Добавить первый урок')}</Button>} />
          <WeekGrid week={data} perspective="edit" onOpen={setOpened} onAdd={(date, slot) => setAdding({ date, slot })} fill />
        </div>
      ) : (
        <>
          <StatRow>
            <Kpi label={t('Уроков на неделе')} value={data.week_total} note={t('по всей школе')} />
            <Kpi
              label={t('Накладки')}
              value={data.conflicts.length || null}
              none={t('нет')}
              tone={data.conflicts.length ? 'bad' : undefined}
              note={data.next_week_conflicts ? `${t('на следующей неделе')} ${data.next_week_conflicts}` : t('учитель, кабинет, ученики')}
              action={!data.conflicts.length && data.next_week_conflicts ? { label: t('Показать'), onClick: () => setStart(weekStart(today) === from ? addWeek(from) : from) } : undefined}
            />
            <Kpi label={t('Замены и переносы')} value={data.changes.length || null} none={t('нет')} note={t('на этой неделе')} />
            <Kpi label={t('Просьбы учителей')} value={data.requests.length || null} none={t('нет')} tone={data.requests.length ? 'warn' : undefined} />
          </StatRow>
          <div className="wknav">
            <div className="wknav__group">
              <Segmented
                value={view}
                onChange={(next) => {
                  setView(next)
                  setKey('')
                }}
                label={t('Вид')}
                items={[
                  { value: 'group', label: t('По группе') },
                  { value: 'teacher', label: t('По учителю') },
                  { value: 'room', label: t('По кабинету') },
                ]}
              />
              <Field kind="select" name="key" label={view === 'group' ? t('Группа') : view === 'teacher' ? t('Учитель') : t('Кабинет')} value={key || data.key} onChange={setKey} options={keyOptions} />
            </div>
            <WeekNav start={from} today={today} onChange={setStart} />
          </div>
          <WeekGrid week={data} perspective="edit" onOpen={setOpened} onAdd={(date, slot) => setAdding({ date, slot })} conflictIds={data.conflict_ids} fill />
          <div className="acad__cols acad__cols--even">
            <div className="acad__stack">
              <DataCard title={t('Накладки')} count={data.conflicts.length || undefined} empty={data.conflicts.length === 0 && (data.next_week_conflicts ? `${t('на этой неделе нет, на следующей')} ${data.next_week_conflicts}` : t('на этой неделе нет'))}>
                <Rows>
                  {data.conflicts.map((c, i) => (
                    <Row
                      key={`${c.lesson}-${c.other}-${i}`}
                      icon="alert"
                      tone="bad"
                      title={c.text}
                      note={`${c.date ? dateWords(c.date) : ''}, ${c.time ?? `${c.slot} ${t('урок')}`}`}
                      acts={
                        <Button variant="secondary" size="sm" onClick={() => setOpened(data.lessons.find((l) => l.id === c.other) ?? data.lessons.find((l) => l.id === c.lesson) ?? null)}>
                          {t('Разобрать')}
                        </Button>
                      }
                    />
                  ))}
                </Rows>
              </DataCard>
              <DataCard title={t('Просьбы учителей')} count={data.requests.length || undefined} empty={data.requests.length === 0 && t('новых нет')}>
                <Rows>
                  {data.requests.map((r) => (
                    <Row
                      key={r.id}
                      avatar={r.teacher.full_name}
                      title={`${r.teacher.short}: ${t('перенести')} ${r.lesson.subject.short_title.toLowerCase()} ${dateWords(r.lesson.date)}`}
                      note={`${r.wanted || t('на свободное время')} · ${r.reason}`}
                      acts={
                        <>
                          <Button variant="outline" size="sm" onClick={() => setReject(r.id)}>
                            {t('Отклонить')}
                          </Button>
                          <Button size="sm" onClick={() => setApprove(r)}>
                            {t('Одобрить')}
                          </Button>
                        </>
                      }
                    />
                  ))}
                </Rows>
              </DataCard>
            </div>
            <div className="acad__stack">
              <DataCard title={t('Замены, отмены, переносы')} count={data.changes.length || undefined} empty={data.changes.length === 0 && t('на этой неделе всё по плану')}>
                <Rows>
                  <ShowAll>
                    {data.changes.map((lesson) => (
                      <Row
                        key={lesson.id}
                        icon="refresh"
                        tone="warn"
                        title={`${lesson.subject.short_title} · ${lesson.cohort.name}`}
                        note={`${lesson.weekday}, ${dateWords(lesson.date)}, ${lesson.slot} ${t('урок')} · ${lesson.substitute ? `${t('замена')} ${lesson.substitute.short}` : lesson.status_title}${lesson.reason ? ` · ${lesson.reason}` : ''}`}
                        onOpen={() => setOpened(lesson)}
                      />
                    ))}
                  </ShowAll>
                </Rows>
              </DataCard>
              <DataCard title={t('Последние изменения')} count={data.log.length || undefined} empty={data.log.length === 0 && t('пока не было')}>
                <Rows>
                  {data.log.map((row) => (
                    <Row key={row.id} icon="clock" title={row.text} note={`${new Date(row.when).toLocaleString('ru', { dateStyle: 'short', timeStyle: 'short' })} · ${row.who}`} />
                  ))}
                </Rows>
              </DataCard>
            </div>
          </div>
        </>
      )}
      {opened && <LessonDrawer lesson={opened} conflicts={openedConflicts} onClose={() => setOpened(null)} />}
      {adding && <LessonForm date={adding.date} slot={adding.slot} onClose={() => setAdding(null)} />}
      {reject !== null && <RejectDialog id={reject} onClose={() => setReject(null)} />}
      {approve && <ApproveDialog request={approve} onClose={() => setApprove(null)} />}
      <EditDrawer open={importing} onClose={() => setImporting(false)} title={t('Импорт расписания')} className="drawer--wide">
        {importing && <ScheduleImport />}
      </EditDrawer>
    </div>
  )
}

function addWeek(iso: string): string {
  const day = new Date(`${iso}T00:00:00`)
  day.setDate(day.getDate() + 7)
  return day.toISOString().slice(0, 10)
}
