/**
 * Учителя: нагрузка, журналы, заполнение за неделю, напоминания, предметы
 * и кабинет, смена учителя журнала. Учётку заводит администратор — здесь же,
 * форма та же, что в «Пользователях» (ссылка на пароль уходит на почту).
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
  useAcadMeta,
  useReassignCourse,
  useRemindAllTeachers,
  useRemindTeacher,
  useTeacherDetail,
  useTeachers,
  useUpdateTeacher,
  type AcadCourse,
  type TeacherRow,
} from '../../api/academics'
import { useCreateUser } from '../../api/hooks'
import DataTable, { type Column } from '../../components/DataTable'
import EditDrawer from '../../components/EditDrawer'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows, StatRow } from '../../components/patterns'
import Progress from '../../components/Progress'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { todayAlmaty } from '../../lib/dates'
import { dateShort, dateWords, NoteCard } from './shared'

type Filter = 'all' | 'unmarked' | 'free'

function ReassignDialog({ course, teachers, onClose }: { course: AcadCourse; teachers: TeacherRow[]; onClose: () => void }) {
  const reassign = useReassignCourse()
  const pool = teachers.filter((row) => row.id !== course.teacher?.id)
  const [teacher, setTeacher] = useState(String((pool.find((row) => row.subjects.some((s) => s.id === course.subject.id)) ?? pool[0])?.id ?? ''))
  const [since, setSince] = useState(todayAlmaty())
  const [error, setError] = useState('')
  return (
    <Modal title={t('Сменить учителя')} note={course.title} onClose={onClose}>
      <Field kind="select" name="teacher" label={t('Новый учитель')} value={teacher} onChange={setTeacher} options={pool.map((row) => ({ value: String(row.id), title: `${row.full_name}${row.subjects.some((s) => s.id === course.subject.id) ? ` · ${t('ведёт этот предмет')}` : ''}` }))} />
      <Field kind="date" name="since" label={t('С даты')} value={since} onChange={setSince} error={error || undefined} />
      <p className="acad__note">{t('Уроки с этой даты перейдут к новому учителю. Журнал общий: прежние оценки новый учитель видит, но править их не может.')}</p>
      <div className="acad__actions">
        <Button
          onClick={() =>
            reassign.mutate(
              { course: course.id, teacher: Number(teacher), since },
              {
                onSuccess: () => {
                  toast.success(`${t('С')} ${dateWords(since)} ${t('ведёт другой учитель')}`)
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
      <Field kind="text" name="email" label={t('Почта')} value={email} onChange={setEmail} placeholder="imya_familiya@bhs.kz" error={error || undefined} />
      <p className="acad__note">{t('Учитель получит ссылку, чтобы задать пароль. Предметы и кабинет — в карточке учителя, уроки — в расписании.')}</p>
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

function TeacherDrawer({ id, teachers, onClose }: { id: number; teachers: TeacherRow[]; onClose: () => void }) {
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
              <Button variant="outline" onClick={() => remind.mutate(id, { onSuccess: (r) => toast.success(`${t('Напоминание ушло:')} ${counted(r.reminded, ['урок', 'урока', 'уроков'])}`), onError: (e) => toast.error(e.message) })}>
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
              <Kpi label={t('Отмечено')} value={data.fill !== null ? `${data.fill} %` : null} none={t('уроков не было')} />
            </StatRow>
            <Field kind="text" name="room" label={t('Кабинет')} value={room} onChange={setRoom} placeholder={t('например, 305')} />
            <span className="t-caps">{t('Предметы')}</span>
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
            <DataCard title={t('Журналы')} count={data.courses?.length || undefined} empty={!data.courses?.length && t('уроков нет')}>
              <Rows>
                {(data.courses ?? []).map((course) => (
                  <Row
                    key={course.id}
                    icon="book"
                    title={course.title}
                    note={`${course.hours} ${t('ч в неделю')} · ${counted(course.students, ['ученик', 'ученика', 'учеников'])} · ${course.cohort.kind_title}`}
                    acts={
                      <Button variant="secondary" size="sm" onClick={() => setReassign(course)}>
                        {t('Сменить учителя')}
                      </Button>
                    }
                  />
                ))}
              </Rows>
            </DataCard>
            <DataCard title={t('Не отмечено за неделю')} count={data.unmarked.length || undefined} empty={data.unmarked.length === 0 && t('всё отмечено')}>
              <Rows>
                {data.unmarked.map((lesson) => (
                  <Row key={lesson.id} icon="alert" tone="warn" title={lesson.title} note={`${lesson.weekday}, ${dateWords(lesson.date)}, ${lesson.slot} ${t('урок')}`} to={`/lessons/${lesson.id}`} />
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

export default function Teachers() {
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
  const rows = data.rows.filter((row) => (filter === 'all' || (filter === 'unmarked' && row.unmarked.length) || (filter === 'free' && !row.hours)) && (!search || row.full_name.toLowerCase().includes(search.toLowerCase())))
  const columns: Column<TeacherRow>[] = [
    {
      key: 'name',
      title: t('Учитель'),
      width: '28%',
      cell: (row) => (
        <span>
          <b>{row.full_name}</b>
          <br />
          <span className="t-note">{row.subject_titles || t('предметы не назначены')}</span>
        </span>
      ),
      sortBy: (row) => row.full_name,
    },
    { key: 'hours', title: t('Нагрузка'), width: '12%', align: 'right', cell: (row) => (row.hours ? <b className="num">{row.hours}</b> : <span className="t-note">{t('уроков нет')}</span>), sortBy: (row) => row.hours },
    { key: 'journals', title: t('Журналы'), width: '10%', align: 'right', cell: (row) => (row.journals ? <b className="num">{row.journals}</b> : <span className="t-note">{t('нет')}</span>), sortBy: (row) => row.journals },
    {
      key: 'fill',
      title: t('Отмечено за неделю'),
      width: '24%',
      cell: (row) =>
        row.fill === null ? (
          <span className="t-note">{t('уроков не было')}</span>
        ) : (
          <span>
            <Progress percent={row.fill} tone={row.fill === 100 ? 'good' : 'warn'} />
            {row.unmarked.length > 0 && <span className="t-note">{`${counted(row.unmarked.length, ['урок', 'урока', 'уроков'])} ${t('без отметки')}`}</span>}
          </span>
        ),
      sortBy: (row) => row.fill,
    },
    { key: 'last', title: t('Последняя отметка'), width: '16%', cell: (row) => (row.last_marked ? `${dateShort(row.last_marked.date)}, ${row.last_marked.slot} ${t('урок')}` : <span className="t-note">{t('не было')}</span>) },
    {
      key: 'act',
      title: '',
      width: '10%',
      align: 'right',
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
        subtitle={t('Нагрузка и заполнение журналов. Учётные записи заводит администратор.')}
        actions={
          <>
            {unmarkedAll.length > 0 && (
              <Button variant="outline" size="sm" onClick={() => remindAll.mutate(undefined, { onSuccess: (r) => toast.success(`${t('Напоминания ушли:')} ${counted(r.teachers, ['учитель', 'учителя', 'учителей'])}`), onError: (e) => toast.error(e.message) })}>
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
      <StatRow>
        <Kpi label={t('Учителей')} value={data.kpis.teachers} note={`${data.kpis.with_lessons} ${t('с уроками')}`} />
        <Kpi label={t('Журналов')} value={data.kpis.journals || null} none={t('нет')} note={t('предмет × состав')} />
        <Kpi label={t('Не отметили вовремя')} value={data.kpis.unmarked_teachers || null} none={t('все отметили')} tone={data.kpis.unmarked_teachers ? 'warn' : undefined} note={t('за эту неделю')} />
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
            <Button key={value} variant={filter === value ? 'default' : 'outline'} size="sm" onClick={() => setFilter(value)}>
              {label} <Chip size="sm">{count}</Chip>
            </Button>
          ))}
        </div>
        <Field kind="text" name="search" label={t('Найти учителя')} value={search} onChange={setSearch} />
      </div>
      <div className="acad__cols">
        <div className="card">
          <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} empty={t('никого не нашлось')} onRowClick={(row) => setOpened(row.id)} />
        </div>
        <div className="acad__stack">
          <DataCard title={t('Не отмечено за неделю')} count={unmarkedAll.length || undefined} empty={unmarkedAll.length === 0 && t('все уроки недели отмечены')}>
            <Rows>
              {unmarkedAll.slice(0, 6).map((row) => (
                <Row key={row.id} avatar={row.full_name} tone="warn" title={row.short} note={row.unmarked.map((lesson) => `${lesson.subject.short_title.toLowerCase()} ${lesson.cohort.short_name} ${dateShort(lesson.date)}`).join('; ')} acts={<Button variant="secondary" size="sm" onClick={() => setOpened(row.id)}>{t('Открыть')}</Button>} />
              ))}
            </Rows>
          </DataCard>
          <NoteCard title={t('Как учитель работает')}>{t('Учитель видит только свои уроки и учеников своих составов. На уроке отмечает отсутствующих и ставит ФО, СОР и СОЧ. Через 10 минут после звонка неотмеченный урок напоминает о себе в колокольчик.')}</NoteCard>
        </div>
      </div>
      {opened !== null && <TeacherDrawer id={opened} teachers={data.rows} onClose={() => setOpened(null)} />}
      {creating && <NewTeacherDialog onClose={() => setCreating(false)} />}
    </div>
  )
}
