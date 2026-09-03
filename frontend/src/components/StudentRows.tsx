/**
 * Дочерние строки ученика на его карточке: вузы, попытки, активности,
 * соревнования, контакты родителей, задачи и эссе.
 *
 * Здесь их заводят, правят и убирают. Право на всё три действия — одно
 * и то же: владелец домена (инвариант №1). До фазы 30 половина таблиц
 * умела только показывать и удалять, а завести строку было нечем.
 */
import { useState, type ReactNode } from 'react'
import {
  useActivityRows,
  useAttemptRows,
  useCompetitionRows,
  useContactRows,
  useContacts,
  useDirectoryEntries,
  useProgramsOf,
  useStudentRows,
  useDirectory,
  useEssayRows,
  useStudentUniversityRows,
  useTaskRows,
  type ParentContact,
} from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import DeleteButton from './DeleteButton'
import RowComments from './RowComments'
import RowForm, { type FieldDef, type RowValues } from './RowForm'
import { DataCard, ErrorNote, Loading } from './ui'
import { t } from '../i18n'
import { SelectField } from './SelectField'
import { Button } from './ui/button'
import RowMenu, { RowMenuItem, RowMenuSeparator } from './RowMenu'

/** Кто ведёт строки этой таблицы. Совпадает с реестром доменов. */
const OWNER: Record<string, string[]> = {
  'universities.StudentUniversity': ['director_admission'],
  'students.ExamAttempt': ['director_exam'],
  'students.Activity': ['director_talent'],
  'students.Competition': ['director_sport'],
  'students.ParentContact': ['director_behavior'],
  'roadmap.Task': [
    'director_behavior',
    'director_admission',
    'director_exam',
    'director_talent',
    'director_sport',
  ],
  'roadmap.Essay': [
    'director_behavior',
    'director_admission',
    'director_exam',
    'director_talent',
    'director_sport',
  ],
}

const TIER_OPTIONS = [
  { value: 'reach', title: 'Reach — вуз мечты' },
  { value: 'target', title: 'Target — реалистичный' },
  { value: 'safety', title: 'Safety — запасной' },
]

const APPLICATION_STATUS: Record<string, string> = {
  not_started: 'не начата',
  in_progress: 'в работе',
  ready: 'готова',
  submitted: 'подана',
  accepted: 'принят',
  rejected: 'отказ',
  waitlist: 'лист ожидания',
}

const EXAM_TYPES = ['IELTS', 'TOEFL', 'SAT', 'ACT'].map((value) => ({ value, title: value }))

const ATTEMPT_FORMATS = [
  { value: 'mock', title: 'Пробный' },
  { value: 'official', title: 'Официальный' },
]

/** Категории активности — те же, что в модели. */
const ACTIVITY_CATEGORY = [
  { value: 'olympiad', title: 'Олимпиада' },
  { value: 'project', title: 'Проект' },
  { value: 'research', title: 'Исследование' },
  { value: 'startup', title: 'Стартап' },
  { value: 'leadership', title: 'Лидерство' },
  { value: 'volunteering', title: 'Волонтёрство' },
  { value: 'competition', title: 'Конкурс' },
  { value: 'award', title: 'Награда' },
]

export const RELATION_OPTIONS = [
  { value: 'mother', title: 'Мама' },
  { value: 'father', title: 'Папа' },
  { value: 'guardian', title: 'Опекун' },
  { value: 'grandparent', title: 'Бабушка или дедушка' },
  { value: 'relative', title: 'Другой родственник' },
  { value: 'other', title: 'Другое' },
]

export const CHANNEL_OPTIONS = [
  { value: 'phone', title: 'Звонок' },
  { value: 'whatsapp', title: 'WhatsApp' },
  { value: 'telegram', title: 'Telegram' },
  { value: 'email', title: 'Почта' },
]

/** Поля формы контакта родителя — их же использует отдельный список. */
export const CONTACT_FIELDS: FieldDef[] = [
  { name: 'full_name', label: 'ФИО', kind: 'text', required: true },
  { name: 'relation', label: 'Кем приходится', kind: 'select', options: RELATION_OPTIONS, required: true },
  { name: 'phone', label: 'Телефон', kind: 'text', placeholder: '+7 …' },
  { name: 'email', label: 'Почта', kind: 'text' },
  { name: 'preferred_channel', label: 'Как связываться', kind: 'select', options: CHANNEL_OPTIONS },
  { name: 'note', label: 'Примечание', kind: 'textarea' },
  { name: 'is_primary', label: 'Основной контакт', kind: 'checkbox' },
]

const TASK_CATEGORY = [
  { value: 'test', title: 'Тест' },
  { value: 'essay', title: 'Эссе' },
  { value: 'documents', title: 'Документы' },
  { value: 'university', title: 'Вузы' },
  { value: 'portfolio', title: 'Портфолио' },
  { value: 'finance', title: 'Финансы' },
]

const TASK_PRIORITY = [
  { value: 'high', title: 'Высокий' },
  { value: 'medium', title: 'Средний' },
  { value: 'low', title: 'Низкий' },
]

const ESSAY_TYPE = [
  { value: 'personal_statement', title: 'Personal Statement' },
  { value: 'supplemental', title: 'Дополнительное эссе' },
  { value: 'motivation', title: 'Мотивационное письмо' },
  { value: 'scholarship', title: 'Для стипендии' },
]

const TASK_STATUS: Record<string, string> = {
  todo: 'сделать',
  in_progress: 'в работе',
  review: 'на проверке',
  done: 'готово',
}

const ESSAY_STATUS: Record<string, string> = {
  draft: 'черновик',
  review: 'на проверке',
  revision: 'на доработке',
  done: 'готово',
}

interface Row {
  id: number
  label: string
  note?: string
  /** значения для формы правки; пусто — строку правят на своём экране */
  values?: RowValues
}

function Section({
  title,
  note,
  hint,
  model,
  path,
  role,
  rows,
  empty,
  fields,
  onCreate,
  onUpdate,
  busy,
  addLabel,
  elsewhere,
  comments,
}: {
  title: string
  note?: string
  hint?: string
  model: string
  path: string
  role: string
  rows: Row[]
  empty: string
  /** состав формы; без него строка только показывается и удаляется */
  fields?: FieldDef[]
  onCreate?: (values: RowValues) => void
  onUpdate?: (id: number, values: RowValues) => void
  busy?: boolean
  addLabel?: string
  /** где строка правится, если не здесь */
  elsewhere?: string
  /** вид обсуждения под строкой: задача или эссе */
  comments?: 'task' | 'essay'
}) {
  const mine = (OWNER[model] ?? []).includes(role)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [talking, setTalking] = useState<number | null>(null)
  const canEdit = mine && fields !== undefined && onUpdate !== undefined

  return (
    <DataCard
      title={title}
      note={note}
      hint={hint}
      count={rows.length}
      right={
        mine && fields && onCreate ? (
          <Button variant="outline" size="sm" onClick={() => setAdding(!adding)}>
            {adding ? t('Отмена') : (addLabel ?? t('Добавить'))}
          </Button>
        ) : undefined
      }
    >
      {adding && fields && onCreate && (
        <RowForm
          fields={fields}
          busy={busy}
          submitLabel={t('Добавить')}
          onCancel={() => setAdding(false)}
          onSubmit={(values) => {
            onCreate(values)
            setAdding(false)
          }}
        />
      )}

      {rows.length === 0 && !adding && <p className="muted rows__empty">{empty}</p>}

      <ul className="rows__list">
        {rows.map((row) => (
          <li key={row.id} className="rows__item">
            <div className="rows__body">
              <div>
                <span className="rows__label">{row.label}</span>
                {row.note && <span className="muted rows__note"> · {row.note}</span>}
              </div>
              <div className="rows__actions">
                {/* обсуждение остаётся кнопкой: оно не действие над строкой,
                    а её вторая половина. Правка и удаление — в меню */}
                {comments && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setTalking(talking === row.id ? null : row.id)}
                  >
                    {talking === row.id ? t('Скрыть') : t('Обсуждение')}
                  </Button>
                )}
                {((canEdit && row.values) || mine) && (
                  <RowMenu>
                    {canEdit && row.values && (
                      <RowMenuItem onClick={() => setEditing(editing === row.id ? null : row.id)}>
                        {editing === row.id ? t('Закрыть') : t('Изменить')}
                      </RowMenuItem>
                    )}
                    {mine && canEdit && row.values && <RowMenuSeparator />}
                    {mine && (
                      <RowMenuItem risk keepOpen>
                        <DeleteButton
                          inMenu
                          model={model}
                          id={row.id}
                          path={path}
                          invalidate={[['student-rows'], ['students'], ['match'], ['contacts']]}
                        />
                      </RowMenuItem>
                    )}
                  </RowMenu>
                )}
              </div>
            </div>
            {comments && talking === row.id && <RowComments kind={comments} id={row.id} />}
            {canEdit && editing === row.id && row.values && fields && (
              <RowForm
                fields={fields}
                row={row.values}
                busy={busy}
                submitLabel={t('Сохранить')}
                onCancel={() => setEditing(null)}
                onSubmit={(values) => {
                  onUpdate?.(row.id, values)
                  setEditing(null)
                }}
              />
            )}
          </li>
        ))}
      </ul>

      {!mine && rows.length > 0 && (
        <p className="muted rows__empty">{t('Эти строки ведёт другой директор')}</p>
      )}
      {mine && elsewhere && <p className="muted rows__empty">{elsewhere}</p>}
    </DataCard>
  )
}

export default function StudentRows({ studentId }: { studentId: number }) {
  const { me } = useAuth()
  const data = useStudentRows(studentId)
  const contacts = useContacts({ student: studentId })
  const subjects = useDirectoryEntries('subjects')
  const universities = useDirectory()
  const [university, setUniversity] = useState<number | null>(null)
  const programs = useProgramsOf(university)

  const attempts = useAttemptRows()
  const activities = useActivityRows()
  const competitions = useCompetitionRows()
  const studentUniversities = useStudentUniversityRows()
  const contactRows = useContactRows()
  const tasks = useTaskRows()
  const essays = useEssayRows()

  const role = me?.role ?? ''

  if (data.isLoading) return <Loading kind="table" />
  if (data.isError) return <ErrorNote error={data.error} />
  if (!data.data) return null
  const bundle = data.data

  const subjectOptions = (subjects.data?.results ?? [])
    .filter((row) => row.is_active)
    .map((row) => ({ value: String(row.id), title: row.name }))

  const programOptions = (programs.data?.results ?? []).map((row) => ({
    value: String(row.id),
    title: `${row.university_name} — ${row.name}`,
  }))

  const attemptFields: FieldDef[] = [
    { name: 'exam_type', label: 'Экзамен', kind: 'select', options: EXAM_TYPES, required: true },
    { name: 'attempt_format', label: 'Формат', kind: 'select', options: ATTEMPT_FORMATS, required: true },
    { name: 'date', label: 'Дата сдачи', kind: 'date', required: true },
    { name: 'total_score', label: 'Общий балл', kind: 'number' },
  ]

  const activityFields: FieldDef[] = [
    { name: 'category', label: 'Категория', kind: 'select', options: ACTIVITY_CATEGORY, required: true },
    { name: 'title', label: 'Название', kind: 'text', required: true },
    { name: 'subject', label: 'Предмет олимпиады', kind: 'select', options: subjectOptions },
    { name: 'date', label: 'Дата', kind: 'date' },
    { name: 'proof_url', label: 'Ссылка на подтверждение', kind: 'text' },
    { name: 'is_confirmed', label: 'Подтверждена', kind: 'checkbox' },
  ]

  const competitionFields: FieldDef[] = [
    { name: 'name', label: 'Соревнование', kind: 'text', required: true },
    { name: 'date', label: 'Дата', kind: 'date' },
    { name: 'result', label: 'Результат', kind: 'text' },
    { name: 'has_certificate', label: 'Есть сертификат', kind: 'checkbox' },
  ]

  const universityFields: FieldDef[] = [
    { name: 'program', label: 'Программа', kind: 'select', options: programOptions, required: true },
    { name: 'tier', label: 'Категория', kind: 'select', options: TIER_OPTIONS, required: true },
    {
      name: 'application_status',
      label: 'Статус заявки',
      kind: 'select',
      options: Object.entries(APPLICATION_STATUS).map(([value, title]) => ({ value, title })),
    },
    { name: 'note', label: 'Примечание', kind: 'textarea' },
  ]

  const taskFields: FieldDef[] = [
    { name: 'title', label: 'Название задачи', kind: 'text', required: true },
    { name: 'category', label: 'Категория', kind: 'select', options: TASK_CATEGORY, required: true },
    { name: 'priority', label: 'Важность', kind: 'select', options: TASK_PRIORITY, required: true },
    {
      name: 'status',
      label: 'Статус',
      kind: 'select',
      options: Object.entries(TASK_STATUS).map(([value, title]) => ({ value, title })),
    },
    { name: 'due_date', label: 'Срок', kind: 'date' },
    { name: 'description', label: 'Описание', kind: 'textarea' },
  ]

  const essayFields: FieldDef[] = [
    { name: 'title', label: 'Название эссе', kind: 'text', required: true },
    { name: 'essay_type', label: 'Вид эссе', kind: 'select', options: ESSAY_TYPE, required: true },
    {
      name: 'status',
      label: 'Статус',
      kind: 'select',
      options: Object.entries(ESSAY_STATUS).map(([value, title]) => ({ value, title })),
    },
  ]

  const picker: ReactNode = role === 'director_admission' && (
    <label className="rows__picker">
      <span className="rowform__label">{t('Сначала выберите вуз')}</span>
      <SelectField
        value={university === null ? '' : String(university)}
        onChange={(event) => setUniversity(event.target.value ? Number(event.target.value) : null)}
      >
        <option value="">{t('— вуз не выбран —')}</option>
        {(universities.data?.results ?? []).map((row) => (
          <option key={row.id} value={row.id}>
            {row.name}
          </option>
        ))}
      </SelectField>
    </label>
  )

  return (
    <div className="grid grid--two">
      <div>
        {picker}
        <Section
          title={t('Вузы в списке ученика')}
          note={t('Программы, куда он подаётся')}
          model="universities.StudentUniversity"
          path="/student-universities/"
          role={role}
          empty={t('Программ в списке пока нет')}
          fields={university === null ? undefined : universityFields}
          elsewhere={university === null ? t('Выберите вуз выше, чтобы добавить его программу') : undefined}
          addLabel={t('Добавить программу')}
          busy={studentUniversities.create.isPending || studentUniversities.update.isPending}
          onCreate={(values) =>
            studentUniversities.create.mutate({
              student: studentId,
              program: Number(values.program),
              tier: String(values.tier ?? 'target'),
              application_status: String(values.application_status ?? 'not_started'),
              note: String(values.note ?? ''),
            })
          }
          onUpdate={(id, values) =>
            studentUniversities.update.mutate({
              id,
              tier: String(values.tier ?? 'target'),
              application_status: String(values.application_status ?? 'not_started'),
              note: String(values.note ?? ''),
            })
          }
          rows={bundle.universities.map((row) => ({
            id: row.id,
            label: `${row.university_name} — ${row.program_name}`,
            note: `${row.tier}${row.added_by === 'student' ? ' · добавил ученик' : ''} · ${
              APPLICATION_STATUS[row.application_status] ?? row.application_status
            }`,
            values: { tier: row.tier, application_status: row.application_status, note: '' },
          }))}
        />
      </div>

      <Section
        title={t('Сданные экзамены и пробные')}
        note={t('Из них строится динамика баллов')}
        model="students.ExamAttempt"
        path="/attempts/"
        role={role}
        empty={t('Попыток пока нет')}
        fields={attemptFields}
        addLabel={t('Добавить попытку')}
        busy={attempts.create.isPending || attempts.update.isPending}
        onCreate={(values) =>
          attempts.create.mutate({
            student: studentId,
            exam_type: String(values.exam_type),
            attempt_format: String(values.attempt_format),
            date: String(values.date),
            total_score: values.total_score === null ? null : Number(values.total_score),
          })
        }
        onUpdate={(id, values) =>
          attempts.update.mutate({
            id,
            exam_type: String(values.exam_type),
            attempt_format: String(values.attempt_format),
            date: String(values.date),
            total_score: values.total_score === null ? null : Number(values.total_score),
          })
        }
        rows={bundle.attempts.map((row) => ({
          id: row.id,
          label: `${row.exam_type} ${row.total_score ?? '—'}`,
          note: `${new Date(row.date).toLocaleDateString('ru')} · ${
            row.attempt_format === 'mock' ? 'пробный' : 'официальный'
          }`,
          values: {
            exam_type: row.exam_type,
            attempt_format: row.attempt_format,
            date: row.date,
            total_score: row.total_score ?? '',
          },
        }))}
      />

      <Section
        title={t('Активности портфолио')}
        note={t('Олимпиады, проекты, волонтёрство')}
        model="students.Activity"
        path="/activities/"
        role={role}
        empty={t('Активностей пока нет')}
        fields={activityFields}
        addLabel={t('Добавить активность')}
        busy={activities.create.isPending || activities.update.isPending}
        onCreate={(values) =>
          activities.create.mutate({
            student: studentId,
            category: String(values.category),
            title: String(values.title),
            subject: values.subject ? Number(values.subject) : null,
            date: values.date ? String(values.date) : null,
            proof_url: String(values.proof_url ?? ''),
            is_confirmed: Boolean(values.is_confirmed),
          })
        }
        onUpdate={(id, values) =>
          activities.update.mutate({
            id,
            category: String(values.category),
            title: String(values.title),
            subject: values.subject ? Number(values.subject) : null,
            date: values.date ? String(values.date) : null,
            proof_url: String(values.proof_url ?? ''),
            is_confirmed: Boolean(values.is_confirmed),
          })
        }
        rows={bundle.activities.map((row) => ({
          id: row.id,
          label: row.title,
          note: [row.subject_name, row.is_confirmed ? 'подтверждена' : 'ждёт подтверждения']
            .filter(Boolean)
            .join(' · '),
          values: {
            category: row.category,
            title: row.title,
            subject: row.subject === null ? '' : String(row.subject),
            date: row.date ?? '',
            proof_url: '',
            is_confirmed: row.is_confirmed,
          },
        }))}
      />

      <Section
        title={t('Спортивные соревнования')}
        note={t('Выступления и результаты')}
        model="students.Competition"
        path="/competitions/"
        role={role}
        empty={t('Соревнований пока нет')}
        fields={competitionFields}
        addLabel={t('Добавить соревнование')}
        busy={competitions.create.isPending || competitions.update.isPending}
        onCreate={(values) =>
          competitions.create.mutate({
            student: studentId,
            name: String(values.name),
            date: values.date ? String(values.date) : null,
            result: String(values.result ?? ''),
            has_certificate: Boolean(values.has_certificate),
          })
        }
        onUpdate={(id, values) =>
          competitions.update.mutate({
            id,
            name: String(values.name),
            date: values.date ? String(values.date) : null,
            result: String(values.result ?? ''),
            has_certificate: Boolean(values.has_certificate),
          })
        }
        rows={bundle.competitions.map((row) => ({
          id: row.id,
          label: row.name,
          note: row.result || undefined,
          values: {
            name: row.name,
            date: row.date ?? '',
            result: row.result,
            has_certificate: false,
          },
        }))}
      />

      <Section
        title={t('Контакты родителей')}
        note={t('Кому звонить по этому ученику')}
        hint={t(
          'Основной контакт помечается отдельно — его набирают первым. Ведёт контакты директор школы, ученику они видны, остальным директорам — только на чтение.',
        )}
        model="students.ParentContact"
        path="/contacts/"
        role={role}
        empty={t('Контактов пока нет')}
        fields={CONTACT_FIELDS}
        addLabel={t('Добавить контакт')}
        busy={contactRows.create.isPending || contactRows.update.isPending}
        onCreate={(values) => contactRows.create.mutate({ student: studentId, ...contactBody(values) })}
        onUpdate={(id, values) => contactRows.update.mutate({ id, ...contactBody(values) })}
        rows={(contacts.data?.results ?? []).map(contactRow)}
      />

      <Section
        title={t('Задачи плана')}
        note={t('Что ученику делать дальше')}
        hint={t(
          'Задачу вправе поставить любой директор — владельца-домена у задач нет. Срок из дедлайна вуза здесь не правится: он живёт в справочнике и сдвигается у всех сразу.',
        )}
        model="roadmap.Task"
        path="/tasks/"
        role={role}
        comments="task"
        empty={t('Задач пока нет')}
        fields={taskFields}
        addLabel={t('Поставить задачу')}
        busy={tasks.create.isPending || tasks.update.isPending}
        onCreate={(values) =>
          tasks.create.mutate({
            student: studentId,
            title: String(values.title),
            category: String(values.category),
            priority: String(values.priority ?? 'medium'),
            due_date: values.due_date ? String(values.due_date) : null,
            description: String(values.description ?? ''),
          })
        }
        onUpdate={(id, values) =>
          tasks.update.mutate({
            id,
            title: String(values.title),
            category: String(values.category),
            priority: String(values.priority ?? 'medium'),
            status: String(values.status ?? 'todo'),
            due_date: values.due_date ? String(values.due_date) : null,
            description: String(values.description ?? ''),
          })
        }
        rows={bundle.tasks.map((row) => ({
          id: row.id,
          label: row.title,
          note: TASK_STATUS[row.status] ?? row.status,
          values: {
            title: row.title,
            category: row.category,
            priority: row.priority,
            status: row.status,
            due_date: row.due_date ?? '',
            description: '',
          },
        }))}
      />

      <Section
        title={t('Эссе')}
        note={t('Заводит куратор, текст пишет ученик')}
        model="roadmap.Essay"
        path="/essays/"
        role={role}
        comments="essay"
        empty={t('Эссе пока нет')}
        fields={essayFields}
        addLabel={t('Завести эссе')}
        elsewhere={t('Сам текст ученик пишет у себя на экране эссе')}
        busy={essays.create.isPending || essays.update.isPending}
        onCreate={(values) =>
          essays.create.mutate({
            student: studentId,
            title: String(values.title),
            essay_type: String(values.essay_type),
          })
        }
        onUpdate={(id, values) =>
          essays.update.mutate({
            id,
            title: String(values.title),
            essay_type: String(values.essay_type),
            status: String(values.status ?? 'draft'),
          })
        }
        rows={bundle.essays.map((row) => ({
          id: row.id,
          label: row.title,
          note: ESSAY_STATUS[row.status] ?? row.status,
          values: { title: row.title, essay_type: row.essay_type, status: row.status },
        }))}
      />
    </div>
  )
}

/** Строка контакта в списке: имя, родство и то, чем с ним связаться. */
export function contactRow(row: ParentContact): Row {
  return {
    id: row.id,
    label: row.full_name + (row.is_primary ? ' · основной' : ''),
    note: [row.relation_title, row.phone, row.email, row.channel_title].filter(Boolean).join(' · '),
    values: {
      full_name: row.full_name,
      relation: row.relation,
      phone: row.phone,
      email: row.email,
      preferred_channel: row.preferred_channel,
      note: row.note,
      is_primary: row.is_primary,
    },
  }
}

/** Тело запроса контакта: пустые поля уходят строкой, а не null. */
export function contactBody(values: RowValues) {
  return {
    full_name: String(values.full_name ?? ''),
    relation: String(values.relation ?? 'other'),
    phone: String(values.phone ?? ''),
    email: String(values.email ?? ''),
    preferred_channel: String(values.preferred_channel ?? ''),
    note: String(values.note ?? ''),
    is_primary: Boolean(values.is_primary),
  }
}
