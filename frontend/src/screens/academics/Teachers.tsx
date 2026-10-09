/**
 * Учителя: нагрузка, журналы, заполнение за неделю, напоминания, предметы
 * и кабинет, смена учителя журнала. Учётку заводит администратор — здесь же,
 * форма та же, что в «Пользователях» (ссылка на пароль уходит на почту).
 *
 * Две вкладки (решение владельца, 09.10.2026): «Ведут в LMS» — те, у кого есть
 * журнал предмета, который ведётся в LMS, или ещё нет расписания; «Только
 * расписание» — учителя предметов Kundelik: стоят в неделе как есть, но в LMS
 * не входят — карточки и действий у них нет, администратор закрывает им вход.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useTrack } from '../../usage/context'
import { toast } from 'sonner'
import {
  useAcadMeta,
  useCloseScheduleOnly,
  useCourseReportRole,
  useReassignCourse,
  useRemindAllTeachers,
  useRemindTeacher,
  useTeacherDetail,
  useTeachers,
  useUpdateTeacher,
  type AcadCourse,
  type ScheduleOnlyTeacher,
  type TeacherRow,
} from '../../api/academics'
import ConfirmDialog from '../../components/ConfirmDialog'
import { useCreateUser } from '../../api/hooks'
import DataTable, { type Column } from '../../components/DataTable'
import EditDrawer from '../../components/EditDrawer'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows, StatRow } from '../../components/patterns'
import Progress from '../../components/Progress'
import {
  Chip,
  counted,
  DataCard,
  EmptyNote,
  ErrorNote,
  Kpi,
  Loading,
  ScreenHead,
  ScreenTabs,
} from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'
import { usePhone } from '../../phone'
import { todayAlmaty } from '../../lib/dates'
import { dateShort, dateWords } from './shared'

type Filter = 'all' | 'unmarked' | 'free'
type Tab = 'lms' | 'schedule'

function ReassignDialog({
  course,
  teachers,
  onClose,
}: {
  course: AcadCourse
  teachers: TeacherRow[]
  onClose: () => void
}) {
  const reassign = useReassignCourse()
  const pool = teachers.filter((row) => row.id !== course.teacher?.id)
  const [teacher, setTeacher] = useState(
    String((pool.find((row) => row.subjects.some((s) => s.id === course.subject.id)) ?? pool[0])?.id ?? ''),
  )
  const [since, setSince] = useState(todayAlmaty())
  const [error, setError] = useState('')
  return (
    <Modal title={t('Сменить учителя')} note={course.title} onClose={onClose}>
      <Field
        kind="select"
        name="teacher"
        label={t('Новый учитель')}
        value={teacher}
        onChange={setTeacher}
        options={pool.map((row) => ({
          value: String(row.id),
          title: `${row.full_name}${row.subjects.some((s) => s.id === course.subject.id) ? ` · ${t('ведёт этот предмет')}` : ''}`,
        }))}
      />
      <Field
        kind="date"
        name="since"
        label={t('С даты')}
        value={since}
        onChange={setSince}
        error={error || undefined}
      />
      <p className="acad__note">
        {t(
          'Уроки с этой даты перейдут к новому учителю. Журнал общий: прежние оценки новый учитель видит, но править их не может.',
        )}
      </p>
      <div className="acad__actions">
        <Button
          onClick={() =>
            reassign.mutate(
              { course: course.id, teacher: Number(teacher), since },
              {
                onSuccess: () => {
                  toast.success(t('С {date} ведёт другой учитель', { date: dateWords(since) }))
                  onClose()
                },
                onError: (e) => setError(e.message),
              },
            )
          }
          disabled={!teacher || reassign.isPending}
        >
          {t('Сменить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

function NewTeacherDialog({ onClose }: { onClose: () => void }) {
  const create = useCreateUser()
  const [last, setLast] = useState('')
  const [first, setFirst] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  return (
    <Modal title={t('Завести учителя')} note={t('Учётная запись с ролью «Учитель»')} onClose={onClose}>
      <Field.Row>
        <Field kind="text" name="last" label={t('Фамилия')} value={last} onChange={setLast} autoFocus />
        <Field kind="text" name="first" label={t('Имя')} value={first} onChange={setFirst} />
      </Field.Row>
      <Field
        kind="text"
        name="email"
        label={t('Почта')}
        value={email}
        onChange={setEmail}
        placeholder="imya_familiya@bhs.kz"
        error={error || undefined}
      />
      <p className="acad__note">
        {t(
          'Учитель получит ссылку, чтобы задать пароль. Предметы и кабинет — в карточке учителя, уроки — в расписании.',
        )}
      </p>
      <div className="acad__actions">
        <Button
          onClick={() => {
            if (!last.trim() || !first.trim()) {
              setError(t('Нужны фамилия и имя'))
              return
            }
            create.mutate(
              { email, full_name: `${last.trim()} ${first.trim()}`, role: 'teacher' },
              {
                onSuccess: () => {
                  toast.success(t('Учитель заведён, ссылка на пароль ушла на почту'))
                  onClose()
                },
                onError: (e) => setError(e.message),
              },
            )
          }}
          disabled={create.isPending}
        >
          {t('Завести')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

const reportRoles = () => [
  { value: '', title: t('в отчёт не идёт отдельно') },
  { value: 'eep', title: 'GE / EEP' },
  { value: 'sat_verbal', title: 'SAT Verbal' },
  { value: 'sat_math', title: 'SAT Math' },
]

/** Раздел отчёта родителям у журнала: SAT — один предмет, Verbal и Math ведут разные учителя. */
function ReportRolePick({ course }: { course: AcadCourse }) {
  const save = useCourseReportRole()
  return (
    <Field
      kind="select"
      name={`role-${course.id}`}
      label={t('Раздел отчёта')}
      value={course.report_role ?? ''}
      disabled={save.isPending}
      onChange={(value) =>
        save.mutate({ course: course.id, report_role: value }, { onError: (e) => toast.error(e.message) })
      }
      options={reportRoles()}
    />
  )
}

function TeacherDrawer({
  id,
  teachers,
  onClose,
}: {
  id: number
  teachers: TeacherRow[]
  onClose: () => void
}) {
  const meta = useAcadMeta()
  const detail = useTeacherDetail(id)
  const update = useUpdateTeacher()
  const remind = useRemindTeacher()
  const [room, setRoom] = useState('')
  const [subjects, setSubjects] = useState<Set<number>>(new Set())
  const [reassign, setReassign] = useState<AcadCourse | null>(null)
  useEffect(() => {
    if (detail.data) {
      setRoom(detail.data.room)
      setSubjects(new Set(detail.data.subjects.map((s) => s.id)))
    }
  }, [detail.data])
  const data = detail.data
  return (
    <>
      <EditDrawer
        open={reassign === null}
        onClose={onClose}
        title={data?.full_name ?? t('Учитель')}
        sub={data ? `${data.subject_titles || t('предметы не назначены')} · ${data.email}` : undefined}
        footer={
          <>
            <Button
              onClick={() =>
                update.mutate(
                  { id, room, subjects: [...subjects] },
                  { onSuccess: () => toast.success(t('Сохранено')), onError: (e) => toast.error(e.message) },
                )
              }
              disabled={update.isPending}
            >
              {t('Сохранить')}
            </Button>
            {data?.unmarked.length ? (
              <Button
                variant="outline"
                onClick={() =>
                  remind.mutate(id, {
                    onSuccess: (r) =>
                      toast.success(`${t('Напоминание ушло:')} ${counted(r.reminded, 'урок|урока|уроков')}`),
                    onError: (e) => toast.error(e.message),
                  })
                }
              >
                {t('Напомнить')}
              </Button>
            ) : null}
          </>
        }
      >
        {!data ? (
          <Loading />
        ) : (
          <>
            <StatRow>
              <Kpi label={t('Уроков в неделю')} value={data.hours || null} none={t('нет')} />
              <Kpi
                label={t('Отмечено')}
                value={data.fill !== null ? `${data.fill} %` : null}
                none={t('уроков не было')}
              />
            </StatRow>
            <Field
              kind="text"
              name="room"
              label={t('Кабинет')}
              value={room}
              onChange={setRoom}
              placeholder={t('например, 305')}
            />
            <span className="t-caps">{t('Предметы')}</span>
            {(meta.data?.subjects ?? []).length === 0 && (
              <EmptyNote
                what={tk('предметов с галочкой «Показывать в списках» нет')}
                who={tk('ведёт Кымбат в «Учебном годе»')}
              />
            )}
            <div className="acad__checklist">
              {(meta.data?.subjects ?? []).map((s) => (
                <Field
                  key={s.id}
                  kind="checkbox"
                  name={`subj${s.id}`}
                  label={s.title}
                  checked={subjects.has(s.id)}
                  onChange={(on) => {
                    const next = new Set(subjects)
                    if (on) next.add(s.id)
                    else next.delete(s.id)
                    setSubjects(next)
                  }}
                />
              ))}
            </div>
            <DataCard
              title={t('Журналы')}
              count={data.courses?.length || undefined}
              empty={!data.courses?.length && t('уроков нет')}
            >
              {/* название и подпись — во всю ширину, действия строкой ниже:
                  в узкой панели выбор и кнопка справа отжимали название в столбик по букве */}
              {(data.courses ?? []).map((course) => (
                <div key={course.id} className="tdrawer__course">
                  <Rows>
                    <Row
                      icon="book"
                      title={course.title}
                      note={`${t('{hours} ч в неделю', { hours: course.hours })} · ${counted(course.students, 'ученик|ученика|учеников')} · ${course.cohort.kind_title}`}
                    />
                  </Rows>
                  <div className="tdrawer__acts">
                    <ReportRolePick course={course} />
                    <Button variant="secondary" size="sm" onClick={() => setReassign(course)}>
                      {t('Сменить учителя')}
                    </Button>
                  </div>
                </div>
              ))}
            </DataCard>
            <DataCard
              title={t('Не отмечено за неделю')}
              count={data.unmarked.length || undefined}
              empty={data.unmarked.length === 0 && t('всё отмечено')}
            >
              <Rows>
                {data.unmarked.map((lesson) => (
                  <Row
                    key={lesson.id}
                    icon="alert"
                    tone="warn"
                    title={lesson.title}
                    note={`${lesson.weekday}, ${dateWords(lesson.date)}, ${t('{slot} урок', { slot: lesson.slot })}`}
                    to={`/lessons/${lesson.id}`}
                  />
                ))}
              </Rows>
            </DataCard>
          </>
        )}
      </EditDrawer>
      {reassign && <ReassignDialog course={reassign} teachers={teachers} onClose={() => setReassign(null)} />}
    </>
  )
}

/** Вкладка «Только расписание»: учителя предметов Kundelik — без карточки и действий. */
function ScheduleOnlyTab({ rows, mayClose }: { rows: ScheduleOnlyTeacher[]; mayClose: boolean }) {
  const phone = usePhone()
  const close = useCloseScheduleOnly()
  const [closing, setClosing] = useState(false)
  const open = rows.filter((row) => row.is_active).length
  const accessChip = (row: ScheduleOnlyTeacher) =>
    row.is_active ? (
      <Chip size="sm" tone="warn">
        {t('вход открыт')}
      </Chip>
    ) : (
      <Chip size="sm">{t('вход закрыт')}</Chip>
    )
  const columns: Column<ScheduleOnlyTeacher>[] = [
    {
      key: 'name',
      title: t('Учитель'),
      width: 'auto',
      phone: 'head',
      cell: (row) => (
        <span>
          <b>{row.full_name}</b>
          <br />
          <span className="t-note">{row.subject_titles || t('предметы не назначены')}</span>
        </span>
      ),
      sortBy: (row) => row.full_name,
    },
    {
      key: 'cohorts',
      title: t('Составы'),
      width: '28%',
      cell: (row) =>
        row.cohorts.length ? row.cohorts.join(', ') : <span className="t-note">{t('нет')}</span>,
    },
    {
      key: 'hours',
      title: t('Уроков'),
      hint: t('Уроков в неделю'),
      width: '112px',
      align: 'right',
      cell: (row) =>
        row.hours ? <b className="num">{row.hours}</b> : <span className="t-note">{t('нет')}</span>,
      sortBy: (row) => row.hours,
    },
    {
      key: 'access',
      title: t('Вход в LMS'),
      width: '136px',
      cell: accessChip,
      sortBy: (row) => (row.is_active ? 0 : 1),
    },
  ]
  return (
    <>
      <div className="acad__toolbar">
        <span className="t-note">
          {t(
            'Журнал этих предметов ведётся в Kundelik: уроки стоят в расписании как есть, карточки и действий в LMS у учителей нет.',
          )}
        </span>
        {mayClose && open > 0 && (
          <Button variant="outline" size="sm" onClick={() => setClosing(true)}>
            {t('Закрыть вход всем в списке')} <Chip size="sm">{open}</Chip>
          </Button>
        )}
      </div>
      {rows.length === 0 ? (
        <DataCard title={t('Только расписание')} empty={t('все учителя с уроками ведут предметы LMS')} />
      ) : phone ? (
        <DataCard title={t('Только расписание')} count={rows.length}>
          <Rows>
            {rows.map((row) => (
              <Row
                key={row.id}
                avatar={row.full_name}
                title={row.full_name}
                note={[
                  row.subject_titles,
                  row.cohorts.join(', '),
                  row.hours ? t('{hours} ч в неделю', { hours: row.hours }) : '',
                ]
                  .filter(Boolean)
                  .join(' · ')}
                right={accessChip(row)}
              />
            ))}
          </Rows>
        </DataCard>
      ) : (
        <div className="card">
          <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} fit />
        </div>
      )}
      <ConfirmDialog
        open={closing}
        title={t('Закрыть вход учителям только расписания?')}
        what={tn(
          open,
          '{n} учётная запись выключится|{n} учётные записи выключатся|{n} учётных записей выключатся',
        )}
        consequences={[
          t('уроки, замены и фамилии в расписании остаются как есть'),
          t('вернуть вход можно в «Пользователях» по одному'),
        ]}
        confirmWord={String(open)}
        confirmLabel={t('Закрыть вход')}
        busy={close.isPending}
        onCancel={() => setClosing(false)}
        onConfirm={() =>
          close.mutate(undefined, {
            onSuccess: (r) => {
              toast.success(
                tn(
                  r.closed,
                  'Вход закрыт: {n} учётная запись|Вход закрыт: {n} учётные записи|Вход закрыт: {n} учётных записей',
                ),
              )
              setClosing(false)
            },
            onError: (e) => toast.error(e.message),
          })
        }
      />
    </>
  )
}

export default function Teachers() {
  const trackFilter = useTrack('filter.change')
  const [params, setParams] = useSearchParams()
  const tab: Tab = params.get('tab') === 'schedule' ? 'schedule' : 'lms'
  const setTab = (next: Tab) => {
    const copy = new URLSearchParams(params)
    copy.set('tab', next)
    setParams(copy, { replace: true })
  }
  const { data, isLoading, error } = useTeachers()
  const remindAll = useRemindAllTeachers()
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const [opened, setOpened] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const unmarkedAll = data.rows.filter((row) => row.unmarked.length)
  const rows = data.rows.filter(
    (row) =>
      (filter === 'all' ||
        (filter === 'unmarked' && row.unmarked.length) ||
        (filter === 'free' && !row.hours)) &&
      (!search || row.full_name.toLowerCase().includes(search.toLowerCase())),
  )
  // таблица в ширину карточки: числа и кнопка — колонками числом, имя
  // и полоса отметок делят остаток; с шириной 880 px «Открыть» уходила за край
  const columns: Column<TeacherRow>[] = [
    {
      key: 'name',
      title: t('Учитель'),
      width: 'auto',
      cell: (row) => (
        <span>
          <b>{row.full_name}</b>
          <br />
          {/* число журналов — здесь, а не колонкой: в таблице шириной в карточку
              колонка «Журналов» отнимала место у имени */}
          <span className="t-note">
            {[
              row.subject_titles || t('предметы не назначены'),
              row.journals
                ? tn(row.journals, '{n} журнал|{n} журнала|{n} журналов').replace(' ', '\u00a0')
                : '',
            ]
              .filter(Boolean)
              .join(' · ')}
          </span>
        </span>
      ),
      sortBy: (row) => row.full_name,
    },
    {
      key: 'hours',
      title: t('Уроков'),
      hint: t('Уроков в неделю'),
      width: '112px',
      align: 'right',
      cell: (row) =>
        row.hours ? <b className="num">{row.hours}</b> : <span className="t-note">{t('нет')}</span>,
      sortBy: (row) => row.hours,
    },
    {
      key: 'fill',
      title: t('Отмечено'),
      hint: t('Отмечено за неделю'),
      width: '176px',
      cell: (row) =>
        row.fill === null ? (
          <span className="t-note">{t('уроков не было')}</span>
        ) : (
          <span>
            <Progress percent={row.fill} tone={row.fill === 100 ? 'good' : 'warn'} />
            {row.unmarked.length > 0 && (
              <span className="t-note">
                {tn(row.unmarked.length, '{n} урок без отметки|{n} урока без отметки|{n} уроков без отметки')}
              </span>
            )}
          </span>
        ),
      sortBy: (row) => row.fill,
    },
    {
      key: 'last',
      title: t('Последняя'),
      hint: t('Последняя отметка'),
      width: '136px',
      cell: (row) =>
        row.last_marked ? (
          `${dateShort(row.last_marked.date)}, ${t('{slot} урок', { slot: row.last_marked.slot })}`
        ) : (
          <span className="t-note">{t('не было')}</span>
        ),
    },
    {
      key: 'act',
      title: '',
      width: '112px',
      actions: true,
      cell: (row) => (
        <Button variant="secondary" size="sm" onClick={() => setOpened(row.id)}>
          {t('Открыть')}
        </Button>
      ),
    },
  ]
  return (
    <div>
      <ScreenHead
        title={t('Учителя')}
        actions={
          <>
            {tab === 'lms' && unmarkedAll.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  remindAll.mutate(undefined, {
                    onSuccess: (r) =>
                      toast.success(
                        `${t('Напоминания ушли:')} ${counted(r.teachers, 'учитель|учителя|учителей')}`,
                      ),
                    onError: (e) => toast.error(e.message),
                  })
                }
              >
                {t('Напомнить всем, кто не отметил')}
              </Button>
            )}
            {data.may_create && (
              <Button size="sm" onClick={() => setCreating(true)}>
                {t('Завести учителя')}
              </Button>
            )}
          </>
        }
      />
      <ScreenTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'lms', label: t('Ведут в LMS {n}', { n: data.rows.length }) },
          { value: 'schedule', label: t('Только расписание {n}', { n: data.schedule_only.length }) },
        ]}
      />
      {tab === 'schedule' && <ScheduleOnlyTab rows={data.schedule_only} mayClose={data.may_close} />}
      {tab === 'lms' && (
        <>
          <StatRow>
            <Kpi
              label={t('Учителей')}
              value={data.kpis.teachers}
              note={t('{count} с уроками', { count: data.kpis.with_lessons })}
            />
            <Kpi
              label={t('Журналов')}
              value={data.kpis.journals || null}
              none={t('нет')}
              note={t('предмет × состав')}
            />
            <Kpi
              label={t('Не отметили вовремя')}
              value={data.kpis.unmarked_teachers || null}
              none={t('все отметили')}
              tone={data.kpis.unmarked_teachers ? 'warn' : undefined}
              note={t('за эту неделю')}
            />
            <Kpi label={t('Замены на неделе')} value={data.kpis.substitutions || null} none={t('нет')} />
          </StatRow>
          <div className="acad__toolbar">
            <div className="acad__chips">
              {(
                [
                  ['all', t('Все'), data.rows.length],
                  ['unmarked', t('Не отметили'), unmarkedAll.length],
                  ['free', t('Без уроков'), data.rows.filter((row) => !row.hours).length],
                ] as [Filter, string, number][]
              ).map(([value, label, count]) => (
                <Button
                  key={value}
                  variant={filter === value ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => {
                    if (value !== filter) trackFilter()
                    setFilter(value)
                  }}
                >
                  {label} <Chip size="sm">{count}</Chip>
                </Button>
              ))}
            </div>
            <Field
              usageFilter
              kind="text"
              name="search"
              label={t('Найти учителя')}
              value={search}
              onChange={setSearch}
            />
          </div>
          <div className="acad__stack">
            <div className="card">
              <DataTable
                columns={columns}
                rows={rows}
                rowKey={(row) => row.id}
                empty={t('никого не нашлось')}
                onRowClick={(row) => setOpened(row.id)}
                fit
              />
            </div>
            {unmarkedAll.length > 0 && (
              <DataCard title={t('Не отмечено за неделю')} count={unmarkedAll.length}>
                <Rows>
                  {unmarkedAll.slice(0, 6).map((row) => (
                    <Row
                      key={row.id}
                      avatar={row.full_name}
                      tone="warn"
                      title={row.short}
                      note={row.unmarked
                        .map(
                          (lesson) =>
                            `${lesson.subject.short_title.toLowerCase()} ${lesson.cohort.short_name} ${dateShort(lesson.date)}`,
                        )
                        .join('; ')}
                      acts={
                        <Button variant="secondary" size="sm" onClick={() => setOpened(row.id)}>
                          {t('Открыть')}
                        </Button>
                      }
                    />
                  ))}
                </Rows>
              </DataCard>
            )}
          </div>
        </>
      )}
      {opened !== null && <TeacherDrawer id={opened} teachers={data.rows} onClose={() => setOpened(null)} />}
      {creating && <NewTeacherDialog onClose={() => setCreating(false)} />}
    </div>
  )
}
