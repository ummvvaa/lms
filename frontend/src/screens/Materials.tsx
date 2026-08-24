/**
 * Раздел материалов олимпиадников.
 *
 * Библиотека, свои загрузки, запросы, подборки и — у директора талантов —
 * очередь проверки. Ученик вне олимпиадной группы сюда не попадает: сервер
 * отвечает 404 на всё, а маршрут закрыт в `App.tsx` (фаза 19).
 */
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  useCollections,
  useDirectoryEntries,
  useMaterialActions,
  useMaterialQueue,
  useMaterialRequests,
  useMaterials,
  useMaterialsState,
  type Material,
} from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import Empty from '../components/Empty'
import MaterialCard from '../components/MaterialCard'
import { counted, ErrorNote, Loading, ScreenHead } from '../components/ui'
import './materials.css'

const SOURCE_KIND = [
  { value: 'own_solution', title: 'Моё решение' },
  { value: 'own_analysis', title: 'Мой разбор' },
  { value: 'third_party', title: 'Чужой материал' },
]

type Tab = 'library' | 'mine' | 'requests' | 'collections' | 'queue'

export default function Materials() {
  const { id } = useParams()
  const navigate = useNavigate()
  const state = useMaterialsState()
  const isCurator = state.data?.is_curator ?? false

  const [tab, setTab] = useState<Tab>('library')
  const [query, setQuery] = useState('')
  const [subject, setSubject] = useState('')
  const [flash, setFlash] = useState<string | null>(null)

  const subjects = useDirectoryEntries('subjects')
  const library = useMaterials({
    status: 'approved',
    search: query || undefined,
    subject: subject || undefined,
  })
  const queue = useMaterialQueue(isCurator)

  const openId = id ? Number(id) : null
  if (openId !== null) {
    return <MaterialCard id={openId} onBack={() => navigate('/materials')} />
  }

  if (state.isLoading) return <Loading />
  if (state.isError) return <ErrorNote error={state.error} />

  // ученик вне олимпиадной группы: раздела для него нет. Сервер отвечает
  // на всё 404, интерфейс говорит то же самое и не намекает на большее
  if (!state.data?.has_access) {
    return (
      <Empty
        title="Страница не найдена"
        what="Такого раздела у вас нет. Если считаете, что это ошибка, напишите куратору."
        action="На главную"
        to="/dashboard"
      />
    )
  }

  const tabs: { key: Tab; title: string }[] = [
    { key: 'library', title: 'Библиотека' },
    { key: 'mine', title: 'Мои материалы' },
    { key: 'requests', title: 'Запросы' },
    { key: 'collections', title: 'Подборки' },
    ...(isCurator ? [{ key: 'queue' as Tab, title: 'На проверке' }] : []),
  ]

  return (
    <div>
      <ScreenHead
        title="Материалы олимпиадников"
        subtitle={
          isCurator
            ? 'Разборы и решения, которыми делятся ребята из олимпиадной группы. Каждый проходит через вас.'
            : 'Разборы и решения ваших. Свой материал появится в библиотеке после проверки директора талантов.'
        }
      />

      {flash && <p className="chip chip-ok mat__flash">{flash}</p>}

      <div className="toolbar mat__tabs">
        {tabs.map((item) => (
          <button
            key={item.key}
            className={`btn btn-sm ${tab === item.key ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setTab(item.key)}
          >
            {item.title}
            {item.key === 'queue' && (queue.data?.pending.length ?? 0) > 0 && (
              <span className="chip chip-warn num mat__badge">{queue.data?.pending.length}</span>
            )}
          </button>
        ))}
      </div>

      {tab === 'library' && (
        <>
          <div className="card card-pad mat__filters">
            <input
              className="input"
              placeholder="Поиск по названию и теме"
              value={query}
              aria-label="Поиск материалов"
              onChange={(event) => setQuery(event.target.value)}
            />
            <select
              className="input"
              value={subject}
              aria-label="Предмет"
              onChange={(event) => setSubject(event.target.value)}
            >
              <option value="">все предметы</option>
              {(subjects.data?.results ?? []).map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </div>
          <MaterialGrid
            rows={library.data?.results ?? []}
            loading={library.isLoading}
            onOpen={(row) => navigate(`/materials/${row.id}`)}
            empty={
              <Empty
                title="Библиотека пуста"
                what={
                  'Здесь появятся разборы и решения, которые ребята выложили и которые прошли проверку. ' +
                  'Начните со своего: то, что вы разобрали для себя, обычно нужно ещё пятерым.'
                }
                action="Выложить материал"
                onAction={() => setTab('mine')}
              />
            }
          />
        </>
      )}

      {tab === 'mine' && (
        <MyMaterials
          onDone={(text) => {
            setFlash(text)
            setTab('mine')
          }}
          onOpen={(row) => navigate(`/materials/${row.id}`)}
        />
      )}

      {tab === 'requests' && <Requests />}

      {tab === 'collections' && (
        <Collections isCurator={isCurator} onOpen={(row) => navigate(`/materials/${row.id}`)} />
      )}

      {tab === 'queue' && isCurator && (
        <ReviewQueue onFlash={setFlash} onOpen={(row) => navigate(`/materials/${row.id}`)} />
      )}
    </div>
  )
}

function MaterialGrid({
  rows,
  loading,
  onOpen,
  empty,
}: {
  rows: Material[]
  loading?: boolean
  onOpen: (row: Material) => void
  empty: React.ReactNode
}) {
  if (loading) return <Loading />
  if (rows.length === 0) return <>{empty}</>
  return (
    <div className="grid grid--two">
      {rows.map((row) => (
        <button key={row.id} className="card card-pad mat__item" onClick={() => onOpen(row)}>
          <span className="eyebrow">
            {row.subject_name} · {row.topic}
          </span>
          <b className="mat__title">{row.title}</b>
          {row.description && <p className="muted mat__desc">{row.description}</p>}
          <span className="mat__meta">
            <span className="chip chip-mute">{row.author_name}</span>
            <span className="chip chip-mute">{row.source_kind_title}</span>
            {row.files.length > 0 && (
              <span className="chip chip-mute num">
                {counted(row.files.length, ['файл', 'файла', 'файлов'])}
              </span>
            )}
            {row.helpful_count > 0 && <span className="chip chip-ok num">полезно: {row.helpful_count}</span>}
            {row.status !== 'approved' && <span className="chip chip-warn">{row.status_title}</span>}
          </span>
        </button>
      ))}
    </div>
  )
}

/** Свои материалы и форма загрузки. */
function MyMaterials({
  onDone,
  onOpen,
}: {
  onDone: (text: string) => void
  onOpen: (row: Material) => void
}) {
  const { me } = useAuth()
  const isStudent = me?.role === 'student'
  const state = useMaterialsState()
  const subjects = useDirectoryEntries('subjects')
  const actions = useMaterialActions()
  const all = useMaterials(isStudent ? { mine: 'true' } : {})
  const requests = useMaterialRequests()
  const openRequests = (requests.data?.results ?? []).filter((row) => row.status === 'open')
  const [form, setForm] = useState({
    subject: '',
    topic: '',
    title: '',
    description: '',
    source_kind: 'own_analysis',
    request: '',
    rights: false,
  })
  const [files, setFiles] = useState<File[]>([])
  const [problem, setProblem] = useState<string | null>(null)

  const rows = all.data?.results ?? []

  function submit() {
    if (!form.subject) return setProblem('Выберите предмет — по нему материал ищут остальные')
    if (!form.title.trim()) return setProblem('Без названия материал не найти в библиотеке')
    if (!form.rights) {
      return setProblem(
        'Поставьте галочку о праве на публикацию. Если это чужой материал и права нет — не выкладывайте его',
      )
    }
    const body = new FormData()
    body.set('subject', form.subject)
    body.set('topic', form.topic.trim())
    body.set('title', form.title.trim())
    body.set('description', form.description.trim())
    body.set('source_kind', form.source_kind)
    body.set('rights_confirmed', 'true')
    if (form.request) body.set('request', form.request)
    files.forEach((file) => body.append('files', file))

    actions.upload.mutate(body, {
      onSuccess: () => {
        setForm({
          subject: '',
          topic: '',
          title: '',
          description: '',
          source_kind: 'own_analysis',
          request: '',
          rights: false,
        })
        setFiles([])
        setProblem(null)
        onDone('Материал отправлен на проверку. Как только его одобрят, он появится в библиотеке')
      },
      onError: (error) => setProblem(String((error as Error).message)),
    })
  }

  return (
    <div>
      {isStudent && (
        <div className="card card-pad mat__form">
          <span className="eyebrow">Выложить материал</span>
          <p className="muted mat__hint">{state.data?.limits.hint}</p>
          <div className="mat__fields">
            <label className="mat__field">
              Предмет
              <select
                className="input"
                value={form.subject}
                onChange={(event) => setForm({ ...form, subject: event.target.value })}
              >
                <option value="">выберите</option>
                {(subjects.data?.results ?? [])
                  .filter((row) => row.is_active)
                  .map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
              </select>
            </label>
            <label className="mat__field">
              Тема
              <input
                className="input"
                placeholder="Механика"
                value={form.topic}
                onChange={(event) => setForm({ ...form, topic: event.target.value })}
              />
            </label>
            <label className="mat__field mat__field--wide">
              Название
              <input
                className="input"
                placeholder="Разбор задач областного этапа"
                value={form.title}
                onChange={(event) => setForm({ ...form, title: event.target.value })}
              />
            </label>
            <label className="mat__field mat__field--wide">
              Описание
              <input
                className="input"
                placeholder="Что внутри и кому пригодится"
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
            </label>
            <label className="mat__field">
              Что это за материал
              <select
                className="input"
                value={form.source_kind}
                onChange={(event) => setForm({ ...form, source_kind: event.target.value })}
              >
                {SOURCE_KIND.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.title}
                  </option>
                ))}
              </select>
            </label>
            <label className="mat__field">
              Закрывает запрос
              <select
                className="input"
                value={form.request}
                onChange={(event) => setForm({ ...form, request: event.target.value })}
              >
                <option value="">ничей запрос</option>
                {openRequests.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.subject_name}: {row.topic}
                  </option>
                ))}
              </select>
            </label>
            <label className="mat__field">
              Файлы
              <span className="mat__file">
                <input
                  type="file"
                  multiple
                  accept=".pdf,.jpg,.jpeg,.png"
                  aria-label="Файлы материала"
                  onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                />
                <span className="btn btn-ghost btn-sm">Выбрать файлы</span>
                <span className="muted">
                  {files.length === 0
                    ? 'ничего не выбрано'
                    : counted(files.length, ['файл', 'файла', 'файлов'])}
                </span>
              </span>
            </label>
          </div>

          <label className="mat__rights">
            <input
              type="checkbox"
              checked={form.rights}
              onChange={(event) => setForm({ ...form, rights: event.target.checked })}
            />
            <span>
              Подтверждаю, что имею право это публиковать. Официальные задания, которые ещё не опубликованы, и
              сканы чужих учебников выкладывать нельзя — претензии придут школе.
            </span>
          </label>

          {problem && <p className="chip chip-risk">{problem}</p>}
          <button className="btn btn-primary btn-sm" disabled={actions.upload.isPending} onClick={submit}>
            {actions.upload.isPending ? 'Отправляем…' : 'Отправить на проверку'}
          </button>
        </div>
      )}

      <h2 className="section">Загруженное</h2>
      <MaterialGrid
        rows={rows}
        loading={all.isLoading}
        onOpen={onOpen}
        empty={
          <Empty
            title="Вы ещё ничего не выкладывали"
            what={
              'Здесь будут ваши разборы и решения — и те, что ждут проверки, и те, что её не прошли, ' +
              'вместе с причиной.'
            }
          />
        }
      />
    </div>
  )
}

/** Запросы: «нужен разбор по такой-то теме». */
function Requests() {
  const { me } = useAuth()
  const list = useMaterialRequests()
  const subjects = useDirectoryEntries('subjects')
  const actions = useMaterialActions()
  const [form, setForm] = useState({ subject: '', topic: '', text: '' })
  const [problem, setProblem] = useState<string | null>(null)
  const rows = list.data?.results ?? []

  return (
    <div>
      {me?.role === 'student' && (
        <div className="card card-pad mat__form">
          <span className="eyebrow">Попросить разбор</span>
          <p className="muted mat__hint">
            Запрос увидят все в группе. Откликнуться может любой — загрузкой материала.
          </p>
          <div className="mat__fields">
            <label className="mat__field">
              Предмет
              <select
                className="input"
                value={form.subject}
                onChange={(event) => setForm({ ...form, subject: event.target.value })}
              >
                <option value="">выберите</option>
                {(subjects.data?.results ?? [])
                  .filter((row) => row.is_active)
                  .map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
              </select>
            </label>
            <label className="mat__field mat__field--wide">
              Тема
              <input
                className="input"
                placeholder="Термодинамика: второе начало"
                value={form.topic}
                onChange={(event) => setForm({ ...form, topic: event.target.value })}
              />
            </label>
            <label className="mat__field mat__field--wide">
              Что именно нужно
              <input
                className="input"
                value={form.text}
                onChange={(event) => setForm({ ...form, text: event.target.value })}
              />
            </label>
          </div>
          {problem && <p className="chip chip-risk">{problem}</p>}
          <button
            className="btn btn-primary btn-sm"
            onClick={() => {
              if (!form.subject || !form.topic.trim()) {
                setProblem('Укажите предмет и тему — иначе непонятно, что искать')
                return
              }
              actions.ask.mutate(
                { subject: Number(form.subject), topic: form.topic.trim(), text: form.text.trim() },
                {
                  onSuccess: () => {
                    setForm({ subject: '', topic: '', text: '' })
                    setProblem(null)
                  },
                  onError: (error) => setProblem(String((error as Error).message)),
                },
              )
            }}
          >
            Попросить
          </button>
        </div>
      )}

      {rows.length === 0 ? (
        <Empty
          title="Запросов пока нет"
          what="Если по какой-то теме не хватает разбора — попросите. Кто-нибудь из группы наверняка её уже разбирал."
        />
      ) : (
        <div className="card card-pad">
          <ul className="rows__list">
            {rows.map((row) => (
              <li key={row.id} className="rows__item">
                <div>
                  <span className="rows__label">{row.topic}</span>
                  <span className="muted rows__note">
                    {' '}
                    · {row.subject_name} · просит {row.author_name}
                    {row.text ? ` · ${row.text}` : ''}
                  </span>
                </div>
                <span className={`chip ${row.status === 'open' ? 'chip-warn' : 'chip-ok'}`}>
                  {row.status_title}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="muted mat__note" hidden={rows.length === 0}>
        Чтобы закрыть запрос, выложите материал и укажите его в поле «Закрывает запрос» — запрос закроется,
        когда материал пройдёт проверку.
      </p>
    </div>
  )
}

/** Подборки: собирает их директор талантов. */
function Collections({ isCurator, onOpen }: { isCurator: boolean; onOpen: (row: Material) => void }) {
  const list = useCollections()
  const subjects = useDirectoryEntries('subjects')
  const library = useMaterials({ status: 'approved' })
  const actions = useMaterialActions()
  const [form, setForm] = useState({ name: '', description: '', subject: '' })
  const [picked, setPicked] = useState<Record<number, string>>({})
  const rows = list.data?.results ?? []

  return (
    <div>
      {isCurator && (
        <div className="card card-pad mat__form">
          <span className="eyebrow">Собрать подборку</span>
          <div className="mat__fields">
            <label className="mat__field mat__field--wide">
              Название
              <input
                className="input"
                placeholder="Подготовка к республиканскому этапу по физике"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </label>
            <label className="mat__field">
              Предмет
              <select
                className="input"
                value={form.subject}
                onChange={(event) => setForm({ ...form, subject: event.target.value })}
              >
                <option value="">без предмета</option>
                {(subjects.data?.results ?? []).map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="mat__field mat__field--wide">
              Описание
              <input
                className="input"
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
            </label>
          </div>
          <button
            className="btn btn-primary btn-sm"
            disabled={!form.name.trim()}
            onClick={() =>
              actions.createCollection.mutate(
                {
                  name: form.name.trim(),
                  description: form.description.trim(),
                  subject: form.subject ? Number(form.subject) : null,
                },
                { onSuccess: () => setForm({ name: '', description: '', subject: '' }) },
              )
            }
          >
            Создать
          </button>
        </div>
      )}

      {rows.length === 0 ? (
        <Empty
          title="Подборок пока нет"
          what={
            isCurator
              ? 'Подборка — это маршрут: несколько материалов в нужном порядке. «Подготовка к республиканскому этапу по физике» полезнее, чем двадцать разрозненных файлов.'
              : 'Директор талантов соберёт материалы в тематические наборы — тогда они появятся здесь.'
          }
        />
      ) : (
        rows.map((collection) => (
          <div key={collection.id} className="card card-pad mat__collection">
            <span className="eyebrow">
              {collection.name}
              {collection.subject_name ? ` · ${collection.subject_name}` : ''}
            </span>
            {collection.description && <p className="muted">{collection.description}</p>}
            <ul className="rows__list">
              {collection.items.map((item) => (
                <li key={item.id} className="rows__item">
                  <button className="link" onClick={() => onOpen({ id: item.material } as Material)}>
                    {item.title}
                  </button>
                  <span className="muted rows__note">
                    {item.author_name} · {item.subject_name}
                  </span>
                </li>
              ))}
            </ul>
            {collection.items.length === 0 && <p className="muted rows__empty">Пока пусто</p>}
            {isCurator && (
              <div className="toolbar">
                <select
                  className="input"
                  aria-label="Материал для подборки"
                  value={picked[collection.id] ?? ''}
                  onChange={(event) => setPicked({ ...picked, [collection.id]: event.target.value })}
                >
                  <option value="">выберите материал</option>
                  {(library.data?.results ?? []).map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.title}
                    </option>
                  ))}
                </select>
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={!picked[collection.id]}
                  onClick={() =>
                    actions.addToCollection.mutate({
                      id: collection.id,
                      material: Number(picked[collection.id]),
                      position: (collection.items.length + 1) * 10,
                    })
                  }
                >
                  Добавить в подборку
                </button>
              </div>
            )}
          </div>
        ))
      )}
    </div>
  )
}

/** Очередь проверки у директора талантов. */
function ReviewQueue({
  onFlash,
  onOpen,
}: {
  onFlash: (text: string) => void
  onOpen: (row: Material) => void
}) {
  const queue = useMaterialQueue(true)
  const actions = useMaterialActions()
  const [reason, setReason] = useState<Record<number, string>>({})

  if (queue.isLoading) return <Loading />
  if (queue.isError) return <ErrorNote error={queue.error} />

  const pending = queue.data?.pending ?? []
  const reports = queue.data?.reports ?? []

  return (
    <div>
      <p className="chip chip-mute mat__flash">{queue.data?.summary}</p>

      {pending.length === 0 && reports.length === 0 && (
        <Empty
          title="Очередь пуста"
          what="Новые материалы и жалобы будут появляться здесь. Пока разбирать нечего."
        />
      )}

      {pending.map((row) => (
        <div key={row.id} className="card card-pad mat__review">
          <span className="eyebrow">
            {row.subject_name} · {row.topic}
          </span>
          <button className="link mat__title" onClick={() => onOpen(row)}>
            {row.title}
          </button>
          <p className="muted">{row.description || 'Без описания'}</p>
          <div className="mat__meta">
            <span className="chip chip-mute">{row.author_name}</span>
            <span className={`chip ${row.source_kind === 'third_party' ? 'chip-warn' : 'chip-mute'}`}>
              {row.source_kind_title}
            </span>
            <span className={`chip ${row.rights_confirmed ? 'chip-ok' : 'chip-risk'}`}>
              {row.rights_confirmed ? 'право на публикацию подтверждено' : 'право не подтверждено'}
            </span>
          </div>
          <ul className="rows__list">
            {row.files.map((file) => (
              <li key={file.id} className="rows__item">
                <a className="link" href={file.url} target="_blank" rel="noreferrer">
                  {file.original_name}
                </a>
                <span className="muted rows__note">{file.size_human}</span>
              </li>
            ))}
          </ul>
          {row.files.length === 0 && <p className="muted rows__empty">Файлов нет — только текст</p>}

          <div className="toolbar">
            <button
              className="btn btn-primary btn-sm"
              onClick={() =>
                actions.review.mutate(
                  { id: row.id, decision: 'approve' },
                  { onSuccess: (answer) => onFlash(answer.detail) },
                )
              }
            >
              Одобрить
            </button>
            <input
              className="input"
              placeholder="Причина отклонения"
              aria-label={`Причина отклонения материала «${row.title}»`}
              value={reason[row.id] ?? ''}
              onChange={(event) => setReason({ ...reason, [row.id]: event.target.value })}
            />
            <button
              className="btn btn-danger btn-sm"
              disabled={!(reason[row.id] ?? '').trim()}
              onClick={() =>
                actions.review.mutate(
                  { id: row.id, decision: 'reject', reason: reason[row.id] },
                  { onSuccess: (answer) => onFlash(answer.detail) },
                )
              }
            >
              Отклонить
            </button>
          </div>
        </div>
      ))}

      {reports.length > 0 && (
        <>
          <h2 className="section">Жалобы</h2>
          {reports.map((row) => (
            <div key={row.id} className="card card-pad mat__review">
              <span className="eyebrow">Пожаловался {row.reporter_name}</span>
              <p>{row.reason}</p>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() =>
                  actions.resolveReport.mutate(
                    { id: row.id, resolution: 'Разобрано' },
                    { onSuccess: (answer) => onFlash(answer.detail) },
                  )
                }
              >
                Пометить разобранной
              </button>
            </div>
          ))}
        </>
      )}
    </div>
  )
}
