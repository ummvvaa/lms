/**
 * Карточка ученика глазами куратора (фаза 61).
 *
 * Пять вкладок: обзор, экзамены, вузы, портфолио, задачи. Всё, кроме
 * решений по очереди и задач, — на чтение, и у каждого чужого блока
 * стоит имя владельца: список вузов ведёт Асем, портфолио — Арман
 * и Нурлыбек, контакты — Салтанат. Куратор видит их целиком, чтобы
 * говорить с родителями предметно, но не правит.
 *
 * Вкладка живёт в адресе (`?tab=exams`), «Назад» возвращает туда,
 * откуда пришли: из таблицы, из очереди или с главной.
 *
 * Вкладки «Документы» и «Заметки», звонок родителю и передача владельцу
 * домена — фаза 62; секции IELTS — 63. Заглушек здесь нет.
 */
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  useAssignTask,
  useCuratorCard,
  useCuratorTaskStatus,
  type CuratorCard as Card,
} from '../../api/hooks'
import { QueueRow } from '../../components/StudentQueue'
import { Row, Rows, StatCard, StatRow } from '../../components/patterns'
import { DataCard, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import TaskDialog from './TaskDialog'
import { CallDialog, EscalateStudentDialog } from './Dialogs'
import DocumentPreview, { STATE_TITLE, STATE_TONE, type PreviewTarget } from './DocumentPreview'
import { useState } from 'react'
import { toast } from 'sonner'
import { useCuratorNotes, useRemindDocuments, type DocumentCell } from '../../api/hooks'
import { Textarea } from '../../components/ui/textarea'
import './curator.css'

type Tab = 'overview' | 'exams' | 'documents' | 'unis' | 'portfolio' | 'tasks' | 'notes'

const TABS: { value: Tab; label: string }[] = [
  { value: 'overview', label: 'Обзор' },
  { value: 'exams', label: 'Экзамены' },
  { value: 'documents', label: 'Документы' },
  { value: 'unis', label: 'Вузы' },
  { value: 'portfolio', label: 'Портфолио' },
  { value: 'tasks', label: 'Задачи' },
  { value: 'notes', label: 'Заметки' },
]

/** Срок задачи-напоминания — неделя, как у «напомнить всем». */
function inAWeek(): string {
  const date = new Date()
  date.setDate(date.getDate() + 7)
  return date.toISOString().slice(0, 10)
}

/**
 * Вкладка «Документы» карточки (фаза 62): пять типов со статусом, причиной
 * отклонения и действиями. Решение — тем же предпросмотром, что в матрице.
 */
function DocumentsTab({ card }: { card: Card }) {
  const [preview, setPreview] = useState<PreviewTarget | null>(null)
  const remind = useRemindDocuments()
  const assign = useAssignTask()
  const open = (cell: DocumentCell) => {
    if (!cell.document) return
    setPreview({
      id: cell.document,
      title: cell.title ?? cell.code,
      studentName: card.full_name,
      fileName: cell.file_name,
      contentType: cell.content_type,
      state: cell.state,
      expiresAt: cell.expires_at,
      rejectReason: cell.reject_reason,
      suggestion: cell.suggestion,
    })
  }
  const remindOne = (title: string) =>
    assign.mutate(
      { student: card.id, title: `${t('Загрузить:')} ${t(title)}`, due_date: inAWeek() },
      {
        onSuccess: () => toast.success(`${t('Задача ученику:')} ${t(title)}`),
        onError: (e) => toast.error(e.message),
      },
    )

  return (
    <DataCard
      title={t('Документы')}
      note={`${card.documents.collected} ${t('из')} ${card.documents.total} ${t('собрано')}`}
      right={
        <Button
          variant="outline"
          size="sm"
          disabled={remind.isPending || card.documents.missing.length === 0}
          onClick={() =>
            remind.mutate(
              { student: card.id },
              {
                onSuccess: () => toast.success(t('Задача ученику: недостающие документы')),
                onError: (e) => toast.error(e.message),
              },
            )
          }
        >
          {t('Напомнить о недостающих')}
        </Button>
      }
    >
      <Rows>
        {card.documents.rows.map((cell) => (
          <Row
            key={cell.code}
            icon="doc"
            tone={STATE_TONE[cell.state] ?? 'mute'}
            title={t(cell.title ?? cell.code)}
            note={
              cell.state === 'rejected'
                ? `${t('Причина:')} ${cell.reject_reason}`
                : cell.state === 'none'
                  ? t('файл не загружен')
                  : cell.expires_at
                    ? `${cell.file_name} · ${t('до')} ${new Date(cell.expires_at).toLocaleDateString('ru')}`
                    : cell.file_name
            }
            right={
              <span className="ctasks__acts">
                <Badge variant={STATE_TONE[cell.state] ?? 'mute'}>{t(STATE_TITLE[cell.state])}</Badge>
                {cell.document && (
                  <Button variant="outline" size="sm" onClick={() => open(cell)}>
                    {t('Открыть')}
                  </Button>
                )}
                {(cell.state === 'none' || cell.state === 'rejected') && (
                  <Button variant="ghost" size="sm" onClick={() => remindOne(cell.title ?? cell.code)}>
                    {t('Напомнить')}
                  </Button>
                )}
              </span>
            }
          />
        ))}
      </Rows>
      <p className="muted cnote__small">
        {t('Ученик загружает файлы сам. Файлы открываются только после входа, прямых ссылок нет.')}
      </p>
      {preview && <DocumentPreview target={preview} onClose={() => setPreview(null)} />}
    </DataCard>
  )
}

/** Вкладка «Заметки»: текст, кто, когда. Ученик не видит — чип напоминает об этом. */
function NotesTab({ card }: { card: Card }) {
  const { list, add, remove } = useCuratorNotes(card.id)
  const [text, setText] = useState('')
  const rows = list.data?.results ?? []

  return (
    <div className="cgrid">
      <div className="cgrid__main">
        <DataCard
          title={t('Заметки куратора')}
          right={<Badge variant="warn">{t('ученик не видит')}</Badge>}
          count={rows.length}
        >
          {rows.length === 0 && <p className="muted">{t('Заметок пока нет')}</p>}
          <Rows>
            {rows.map((note) => (
              <Row
                key={note.id}
                icon="doc"
                title={note.text}
                note={`${note.author_name} · ${new Date(note.created_at).toLocaleString('ru')}`}
                right={
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={remove.isPending}
                    onClick={() =>
                      remove.mutate(note.id, {
                        onSuccess: () => toast.success(t('Заметка в архиве')),
                        onError: (e) => toast.error(e.message),
                      })
                    }
                  >
                    {t('В архив')}
                  </Button>
                }
              />
            ))}
          </Rows>
          <div className="cnotes__form">
            <Textarea
              rows={3}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={t('Что важно помнить про ученика — для вас, Кымбат и Салтанат')}
              aria-label={t('Новая заметка')}
            />
            <div className="ctask__actions">
              <Button
                disabled={add.isPending || !text.trim()}
                onClick={() =>
                  add.mutate(text, {
                    onSuccess: () => {
                      toast.success(t('Заметка сохранена'))
                      setText('')
                    },
                    onError: (e) => toast.error(e.message),
                  })
                }
              >
                {t('Сохранить заметку')}
              </Button>
            </div>
          </div>
        </DataCard>
      </div>
      <div className="cgrid__side">
        <p className="cnote">
          {t('Заметки видят куратор, Кымбат и Салтанат. В карточку ученика они не попадают.')}
        </p>
      </div>
    </div>
  )
}

const dateOf = (value: string | null) => (value ? new Date(value).toLocaleDateString('ru') : '—')

/**
 * Искра: как менялся балл от пробника к пробнику.
 *
 * Не график — линия высотой в строку рядом с числами: куратору важно
 * направление, а не значения по осям. Одна точка не рисуется вовсе:
 * прямая из одного значения показывала бы динамику там, где её нет.
 */
function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return <span className="muted">{t('мало данных')}</span>
  const low = Math.min(...values)
  const high = Math.max(...values)
  const points = values.map((value, index) => {
    const x = 2 + (index * 116) / (values.length - 1)
    const y = high === low ? 16 : 28 - ((value - low) / (high - low)) * 24
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const [lastX, lastY] = points[points.length - 1].split(',')
  return (
    <svg className="cspark" viewBox="0 0 120 32" role="img" aria-label={t('Динамика пробников')}>
      <polyline points={points.join(' ')} />
      <circle cx={lastX} cy={lastY} r="2.5" />
    </svg>
  )
}

/** Строки задач — одинаковые в карточке и на экране задач. */
export function TaskLine({
  task,
  onStatus,
}: {
  task: Card['tasks'][number]
  onStatus?: (status: 'done' | 'cancelled' | 'todo') => void
}) {
  const closed = task.status === 'done' || task.status === 'cancelled'
  return (
    <Row
      icon="checklist"
      tone={task.is_overdue ? 'risk' : closed ? 'mute' : 'brand'}
      title={task.title}
      note={`${task.origin_title} · ${task.due_date ? `${t('срок')} ${dateOf(task.due_date)}` : t('без срока')}`}
      muted={closed}
      right={
        <span className="ctasks__acts">
          <Badge variant={task.is_overdue ? 'risk' : closed ? 'mute' : 'warn'}>
            {task.status === 'done'
              ? t('сделано')
              : task.status === 'cancelled'
                ? t('отменена')
                : task.is_overdue
                  ? t('просрочена')
                  : task.status_title}
          </Badge>
          {onStatus && !closed && (
            <>
              <Button variant="outline" size="sm" onClick={() => onStatus('done')}>
                {t('Сделано')}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => onStatus('cancelled')}>
                {t('Отменить')}
              </Button>
            </>
          )}
          {onStatus && closed && (
            <Button variant="ghost" size="sm" onClick={() => onStatus('todo')}>
              {t('Вернуть')}
            </Button>
          )}
        </span>
      }
    />
  )
}

export default function CuratorCard() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const studentId = Number(id)
  const { data, isLoading, error } = useCuratorCard(Number.isFinite(studentId) ? studentId : null)
  const move = useCuratorTaskStatus()

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const tab = (params.get('tab') as Tab) || 'overview'
  const setTab = (next: Tab) => {
    const updated = new URLSearchParams(params)
    updated.set('tab', next)
    setParams(updated, { replace: true })
  }

  const exams = data.exams
  const openTasks = data.tasks.filter((task) => task.status !== 'done' && task.status !== 'cancelled')

  return (
    <div>
      <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
        {t('← Назад')}
      </Button>

      <ScreenHead
        title={data.full_name}
        subtitle={`${data.grade} ${t('класс')} · ${t('группа')} ${data.group} · ${t('куратор')} ${data.curator}`}
        actions={
          <>
            {data.status_title && <Badge variant="mute">{data.status_title}</Badge>}
            <CallDialog card={data} />
            <TaskDialog groups={[]} student={data.id} studentName={data.full_name} />
            <EscalateStudentDialog card={data} />
          </>
        }
      />

      <ScreenTabs
        value={tab}
        onChange={setTab}
        items={TABS.map((item) => ({ ...item, label: t(item.label) }))}
      />

      {tab === 'overview' && (
        <div className="cgrid">
          <div className="cgrid__main">
            {data.queue.length > 0 && (
              <DataCard title={t('Ждёт вашего подтверждения')} accent="brand">
                {data.queue.map((row) => (
                  <QueueRow key={row.id} row={row} />
                ))}
              </DataCard>
            )}

            <StatRow>
              <StatCard
                icon="book"
                tone="brand"
                label="IELTS"
                value={exams.ielts_current ?? '—'}
                note={`${t('цель')} ${exams.ielts_target ?? t('не поставлена')}`}
              />
              <StatCard
                icon="target"
                tone="teal"
                label="SAT"
                value={exams.sat_current ?? '—'}
                note={`${t('цель')} ${exams.sat_target ?? t('не поставлена')}`}
              />
              <StatCard
                icon="clock"
                tone="indigo"
                label={t('Пробники')}
                value={exams.mocks_total}
                note={
                  exams.last_mock_date ? `${t('последний')} ${dateOf(exams.last_mock_date)}` : t('не было')
                }
              />
              <StatCard
                icon="doc"
                tone={data.documents.missing.length ? 'risk' : 'ok'}
                label={t('Документы')}
                value={`${data.documents.collected} / ${data.documents.total}`}
                note={data.documents.missing.length ? t('есть недостающие') : t('собраны')}
                onClick={() => setTab('documents')}
              />
            </StatRow>

            <DataCard
              title={t('Открытые задачи')}
              right={<TaskDialog groups={[]} student={data.id} studentName={data.full_name} />}
            >
              {openTasks.length === 0 && <p className="muted">{t('Задач нет')}</p>}
              <Rows>
                {openTasks.map((task) => (
                  <TaskLine
                    key={task.id}
                    task={task}
                    onStatus={(status) => move.mutate({ id: task.id, status })}
                  />
                ))}
              </Rows>
            </DataCard>
          </div>

          <div className="cgrid__side">
            <DataCard title={t('Что требует внимания')}>
              {data.buckets.length === 0 && <p className="muted">{t('Всё в порядке')}</p>}
              <Rows>
                {data.buckets.map((bucket) => (
                  <Row key={bucket.code} icon="alert" tone={bucket.tone as 'warn'} title={t(bucket.title)} />
                ))}
              </Rows>
            </DataCard>

            <DataCard title={t('Контакты')} note={t('Ведёт директор школы — Салтанат')}>
              {data.contacts.length === 0 && <p className="muted">{t('Контактов пока нет')}</p>}
              <Rows>
                {data.contacts.map((contact) => (
                  <Row
                    key={contact.id}
                    icon="person"
                    title={contact.full_name}
                    note={`${contact.relation_title} · ${contact.phone || contact.email}`}
                  />
                ))}
              </Rows>
            </DataCard>
          </div>
        </div>
      )}

      {tab === 'exams' && (
        <div className="cgrid">
          <div className="cgrid__main">
            <p className="cnote">
              {t(
                'Официальный балл вносит ученик, вы подтверждаете. Пробники загружаются файлом от учителя — ученик их не предлагает. Это две разные строки, они друг друга не перекрывают.',
              )}
            </p>

            <DataCard title="IELTS">
              <dl className="ckv">
                <dt>{t('Официальный балл')}</dt>
                <dd className="num">{exams.ielts_current ?? '—'}</dd>
                <dt>{t('Цель')}</dt>
                <dd className="num">{exams.ielts_target ?? t('не поставлена')}</dd>
                <dt>{t('Дата экзамена')}</dt>
                <dd>{dateOf(exams.ielts_exam_date)}</dd>
              </dl>
            </DataCard>

            <DataCard title="SAT">
              <dl className="ckv">
                <dt>{t('Официальный балл')}</dt>
                <dd className="num">{exams.sat_current ?? '—'}</dd>
                <dt>{t('Цель')}</dt>
                <dd className="num">{exams.sat_target ?? t('не поставлена')}</dd>
                <dt>{t('Дата экзамена')}</dt>
                <dd>{dateOf(exams.sat_exam_date)}</dd>
              </dl>
            </DataCard>
          </div>

          <div className="cgrid__side">
            <DataCard title={t('История пробников')} count={data.mocks.length}>
              {data.mocks.length === 0 && <p className="muted">{t('Пробников ещё не было')}</p>}
              {/* сначала направление по каждому экзамену, потом сами попытки */}
              <Rows>
                {['IELTS', 'SAT'].map((exam) => {
                  const scores = data.mocks
                    .filter((mock) => mock.exam === exam && mock.score !== null)
                    .map((mock) => mock.score as number)
                  if (scores.length === 0) return null
                  return (
                    <Row
                      key={exam}
                      title={exam}
                      note={scores.join(' · ')}
                      right={<Spark values={scores} />}
                    />
                  )
                })}
              </Rows>
              <Rows>
                {[...data.mocks].reverse().map((mock) => (
                  <Row
                    key={mock.id}
                    icon="target"
                    title={`${mock.exam} · ${mock.score ?? '—'}`}
                    note={`${dateOf(mock.date)} · ${mock.source_title}`}
                  />
                ))}
              </Rows>
            </DataCard>

            {exams.ielts_target === null && exams.sat_target === null && (
              <DataCard title={t('Целей нет')} note={t('Поставить может только ученик — напомните ему')}>
                <TaskDialog
                  groups={[]}
                  student={data.id}
                  studentName={data.full_name}
                  label={t('Напомнить задачей')}
                />
              </DataCard>
            )}
          </div>
        </div>
      )}

      {tab === 'documents' && <DocumentsTab card={data} />}
      {tab === 'notes' && <NotesTab card={data} />}

      {tab === 'unis' && (
        <DataCard
          title={t('Список вузов')}
          note={t('Только чтение — ведёт директор по поступлению')}
          count={data.universities.length}
        >
          {data.universities.length === 0 && <p className="muted">{t('Вузов в списке пока нет')}</p>}
          <Rows>
            {data.universities.map((row) => (
              <Row
                key={row.id}
                icon="cap"
                title={`${row.university} — ${row.program}`}
                note={row.deadline ? `${t('дедлайн')} ${dateOf(row.deadline)}` : t('дедлайн не задан')}
                right={row.tier_title ? <Badge variant="mute">{row.tier_title}</Badge> : undefined}
              />
            ))}
          </Rows>
          <p className="muted cnote__small">
            {t(
              'Подбор показывает соответствие требованиям вуза. Вопросы по списку — к директору по поступлению.',
            )}
          </p>
        </DataCard>
      )}

      {tab === 'portfolio' && (
        <DataCard
          title={t('Портфолио')}
          note={t('Только чтение — ведут директор талантов и директор спорта')}
        >
          <p className="cportfolio__percent">
            {t('Заполнено на')} <b className="num">{data.portfolio.percent}%</b>
          </p>
          <Rows>
            {data.portfolio.sections.map((section) => (
              <Row
                key={section.code}
                icon="layers"
                title={t(section.title)}
                note={section.next}
                right={<b className="num">{Math.round(section.value * 100)}%</b>}
              />
            ))}
          </Rows>
        </DataCard>
      )}

      {tab === 'tasks' && (
        <DataCard
          title={t('Задачи ученику')}
          count={data.tasks.length}
          right={<TaskDialog groups={[]} student={data.id} studentName={data.full_name} />}
        >
          {data.tasks.length === 0 && <p className="muted">{t('Задач не было')}</p>}
          <Rows>
            {data.tasks.map((task) => (
              <TaskLine
                key={task.id}
                task={task}
                onStatus={(status) => move.mutate({ id: task.id, status })}
              />
            ))}
          </Rows>
        </DataCard>
      )}
    </div>
  )
}
