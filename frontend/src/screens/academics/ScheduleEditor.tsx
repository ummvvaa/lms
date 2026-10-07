/**
 * Расписание у Кымбат и администратора: неделя по группе, учителю или
 * кабинету с правкой уроков, накладки, просьбы учителей, замены и отмены,
 * последние изменения.
 *
 * Образец — `route(['kymbat', 'admin'], '/schedule')` референса.
 */
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { useAcadMeta, useDecideRequest, useScheduleWeek, type AcadConflict, type AcadLesson, type ScheduleWeek } from '../../api/academics'
import { useAuth } from '../../auth/AuthContext'
import EditDrawer from '../../components/EditDrawer'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows, Segmented, ShowAll, StatRow } from '../../components/patterns'
import { counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tn } from '../../i18n'
import LessonDrawer, { LessonForm, SlotField } from './LessonDrawer'
import ScheduleImport from './ScheduleImport'
import { dateWords, useWeekStart, WeekGrid, WeekNav, weekStart } from './shared'
import { formatDateTime } from '../../lib/format'
import { shiftDay } from '../../lib/dates'

type View = 'group' | 'teacher' | 'room'

const VIEWS: View[] = ['group', 'teacher', 'room']

/** Урок, кабинет, учитель, группа накладки — одной строкой для карточки над неделей. */
function clashOf(conflicts: AcadConflict[], clash: string): AcadConflict | null {
  const [lesson, other] = clash.split(',').map((part) => Number(part) || null)
  if (!lesson) return null
  return conflicts.find((c) => c.lesson === lesson && (c.other ?? null) === other) ?? conflicts.find((c) => c.lesson === lesson || c.other === lesson) ?? null
}

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
  const decide = useDecideRequest()
  const [date, setDate] = useState(request.lesson.date)
  const [slot, setSlot] = useState(String(request.lesson.slot))
  const [force, setForce] = useState(false)
  const [error, setError] = useState('')
  return (
    <Modal title={t('Одобрить перенос')} note={`${request.teacher.full_name}: ${request.wanted || t('на свободное время')} · ${request.reason}`} onClose={onClose}>
      <Field.Row>
        <Field kind="date" name="date" label={t('Новая дата')} value={date} onChange={setDate} />
        <SlotField cohort={request.lesson.cohort.id} value={slot} onChange={setSlot} />
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
  // вид, ключ и разбираемая накладка живут в адресе рядом с неделей (`?from=`):
  // «Разобрать» у накладки и ссылка из дайджеста открывают нужную неделю в нужном виде
  const [params, setParams] = useSearchParams()
  const view: View = VIEWS.find((item) => item === params.get('view')) ?? 'group'
  const key = params.get('key') ?? ''
  const clash = params.get('clash') ?? ''
  const patch = (changes: Record<string, string | null>) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        Object.entries(changes).forEach(([name, value]) => (value ? next.set(name, value) : next.delete(name)))
        return next
      },
      { replace: true },
    )
  const setView = (next: View) => patch({ view: next === 'group' ? null : next, key: null, clash: null })
  const setKey = (next: string) => patch({ key: next || null, clash: null })
  const from = start || (today ? weekStart(today) : '')
  const week = useScheduleWeek({ from: from || undefined, view, key: key || undefined })
  const clashing = week.data ? clashOf(week.data.conflicts, clash) : null
  const clashIds = clashing ? [clashing.lesson, clashing.other].filter((id): id is number => id !== null) : []
  useEffect(() => {
    // накладку убрали (перенесли, отменили урок) — подсветка уходит сама
    if (clash && week.data && !week.isPlaceholderData && !clashing) patch({ clash: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clash, clashing, week.data, week.isPlaceholderData])
  const [opened, setOpened] = useState<AcadLesson | null>(null)
  // ряд недели — время; номер урока известен, если в это время он один
  const [adding, setAdding] = useState<{ date: string; slot?: number; starts?: string } | null>(null)
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
        subtitle={`${tn(data.series_total, '{n} урок в неделю|{n} урока в неделю|{n} уроков в неделю')} · ${counted(data.teachers_total, 'учитель|учителя|учителей')} · ${counted(data.groups_total, 'группа|группы|групп')}`}
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
          <WeekGrid week={data} perspective="edit" onOpen={setOpened} onAdd={(date, row) => setAdding({ date, slot: row.slot ?? undefined, starts: row.starts })} fill />
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
              note={data.next_week_conflicts ? t('на следующей неделе: {count}', { count: data.next_week_conflicts }) : t('учитель, кабинет, ученики')}
              action={!data.conflicts.length && data.next_week_conflicts ? { label: t('Показать'), onClick: () => setStart(weekStart(today) === from ? addWeek(from) : from) } : undefined}
            />
            <Kpi label={t('Замены и переносы')} value={data.changes.length || null} none={t('нет')} note={t('на этой неделе')} />
            <Kpi label={t('Просьбы учителей')} value={data.requests.length || null} none={t('нет')} tone={data.requests.length ? 'warn' : undefined} />
          </StatRow>
          <div className="wknav">
            <div className="wknav__group">
              <Segmented
                value={view}
                onChange={setView}
                label={t('Вид')}
                items={[
                  { value: 'group', label: t('По группе') },
                  { value: 'teacher', label: t('По учителю') },
                  { value: 'room', label: t('По кабинету') },
                ]}
              />
              <Field usageFilter kind="select" name="key" label={view === 'group' ? t('Группа') : view === 'teacher' ? t('Учитель') : t('Кабинет')} value={key || data.key} onChange={setKey} options={keyOptions} />
            </div>
            <WeekNav start={from} today={today} onChange={setStart} />
          </div>
          {clashing && (
            <div className="card card-pad acad__nobells">
              <Rows>
                <Row
                  icon="alert"
                  tone="bad"
                  title={clashing.text}
                  note={`${clashing.date ? dateWords(clashing.date) : ''}${clashing.time ? `, ${clashing.time}` : ''} · ${t('Уроки накладки выделены в неделе. Нажмите урок, чтобы перенести, отменить или поставить замену')}`}
                  acts={
                    <Button variant="outline" size="sm" onClick={() => patch({ clash: null })}>
                      {t('Снять выделение')}
                    </Button>
                  }
                />
              </Rows>
            </div>
          )}
          <WeekGrid
            week={data}
            perspective="edit"
            onOpen={setOpened}
            onAdd={(date, row) => setAdding({ date, slot: row.slot ?? undefined, starts: row.starts })}
            conflictIds={data.conflict_ids}
            clashIds={clashIds}
            focus={clashing?.date}
            fill
          />
          <div className="acad__cols acad__cols--even">
            <div className="acad__stack">
              <DataCard title={t('Накладки')} count={data.conflicts.length || undefined} empty={data.conflicts.length === 0 && (data.next_week_conflicts ? t('на этой неделе нет, на следующей — {count}', { count: data.next_week_conflicts }) : t('на этой неделе нет'))}>
                <Rows>
                  {data.conflicts.map((c, i) => (
                    <Row
                      key={`${c.lesson}-${c.other}-${i}`}
                      icon="alert"
                      tone="bad"
                      title={c.text}
                      note={`${c.date ? dateWords(c.date) : ''}, ${c.time ?? t('{slot} урок', { slot: c.slot })}`}
                      acts={
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() =>
                            // неделя накладки в том виде, где видны оба её урока
                            // (учитель, кабинет или группа — `where` с сервера)
                            patch({
                              from: c.date ? weekStart(c.date) : null,
                              view: c.where && c.where.view !== 'group' ? c.where.view : null,
                              key: c.where?.key || null,
                              clash: [c.lesson, c.other].filter((id) => id !== null).join(','),
                            })
                          }
                        >
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
                      title={`${r.teacher.short}: ${t('перенести {subject} {date}', { subject: r.lesson.subject.short_title.toLowerCase(), date: dateWords(r.lesson.date) })}`}
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
                        note={`${lesson.weekday}, ${dateWords(lesson.date)}, ${t('{slot} урок', { slot: lesson.slot })} · ${lesson.substitute ? t('замена: {teacher}', { teacher: lesson.substitute.short }) : lesson.status_title}${lesson.reason ? ` · ${lesson.reason}` : ''}`}
                        onOpen={() => setOpened(lesson)}
                      />
                    ))}
                  </ShowAll>
                </Rows>
              </DataCard>
              <DataCard title={t('Последние изменения')} count={data.log.length || undefined} empty={data.log.length === 0 && t('пока не было')}>
                <Rows>
                  {data.log.map((row) => (
                    <Row key={row.id} icon="clock" title={row.text} note={`${formatDateTime(row.when)} · ${row.who}`} />
                  ))}
                </Rows>
              </DataCard>
            </div>
          </div>
        </>
      )}
      {opened && <LessonDrawer lesson={opened} conflicts={openedConflicts} onClose={() => setOpened(null)} />}
      {adding && (
        <LessonForm
          date={adding.date}
          slot={adding.slot}
          starts={adding.starts}
          // открытая неделя подставляется в новый урок: её учитель, группа или кабинет
          teacher={view === 'teacher' && data.key ? Number(data.key) : undefined}
          group={view === 'group' ? data.key || undefined : undefined}
          room={view === 'room' ? data.key || undefined : undefined}
          onClose={() => setAdding(null)}
        />
      )}
      {reject !== null && <RejectDialog id={reject} onClose={() => setReject(null)} />}
      {approve && <ApproveDialog request={approve} onClose={() => setApprove(null)} />}
      <EditDrawer open={importing} onClose={() => setImporting(false)} title={t('Импорт расписания')} className="drawer--wide">
        {importing && <ScheduleImport />}
      </EditDrawer>
    </div>
  )
}

function addWeek(iso: string): string {
  return shiftDay(iso, 7)
}
