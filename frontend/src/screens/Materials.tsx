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
import { counted, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import './materials.css'
import { t } from '../i18n'
import { SelectField } from '../components/SelectField'
import { Input } from '../components/ui/input'
import { Checkbox } from '../components/ui/checkbox'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'

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

  const [tab, setTab] = useState<Tab | null>(null)
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

  // до ответа сервера роль ещё неизвестна: вкладку выбираем, когда
  // выяснилось, куратор перед нами или ученик
  const current: Tab = tab ?? (isCurator ? 'queue' : 'library')

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
        icon="openbook"
        title={t('Страница не найдена')}
        what={t('Такого раздела у вас нет. Если считаете, что это ошибка, напишите куратору.')}
        action={t('На главную')}
        to="/dashboard"
      />
    )
  }

  // у Армана первой идёт очередь проверки: это его основная работа,
  // а не библиотека, которую он и так видел
  const tabs: { key: Tab; title: string }[] = [
    ...(isCurator ? [{ key: 'queue' as Tab, title: 'На проверке' }] : []),
    { key: 'library', title: 'Библиотека' },
    { key: 'mine', title: 'Мои материалы' },
    { key: 'requests', title: 'Запросы' },
    { key: 'collections', title: 'Подборки' },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Материалы олимпиадников')}
        subtitle={
          isCurator
            ? 'Разборы и решения, которыми делятся ребята из олимпиадной группы. Каждый проходит через вас.'
            : 'Разборы и решения ваших. Свой материал появится в библиотеке после проверки директора талантов.'
        }
      />

      {flash && (
        <Badge variant="ok" className="badge--line mat__flash">
          {flash}
        </Badge>
      )}

      {/* вкладки раздела — тот же ряд, что на остальных экранах,
          а не ряд кнопок: у вкладок подложка переезжает */}
      <ScreenTabs
        value={current}
        onChange={setTab}
        items={tabs.map((item) => ({
          key: item.key,
          value: item.key,
          label: (
            <>
              {item.title}
              {item.key === 'queue' && (queue.data?.pending.length ?? 0) > 0 && (
                <Badge variant="warn" className="num mat__badge">
                  {queue.data?.pending.length}
                </Badge>
              )}
            </>
          ),
        }))}
      />

      {current === 'library' && (
        <>
          <div className="card card-pad mat__filters">
            <Input
              placeholder={t('Поиск по названию и теме')}
              value={query}
              aria-label={t('Поиск материалов')}
              onChange={(event) => setQuery(event.target.value)}
            />
            <SelectField
              value={subject}
              aria-label={t('Предмет')}
              onChange={(event) => setSubject(event.target.value)}
            >
              <option value="">{t('все предметы')}</option>
              {(subjects.data?.results ?? []).map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </SelectField>
          </div>
          <MaterialGrid
            rows={library.data?.results ?? []}
            loading={library.isLoading}
            onOpen={(row) => navigate(`/materials/${row.id}`)}
            empty={
              <Empty
                icon="openbook"
                title={t('Библиотека пуста')}
                what={
                  'Здесь появятся разборы и решения, которые ребята выложили и которые прошли проверку. ' +
                  'Начните со своего: то, что вы разобрали для себя, обычно нужно ещё пятерым.'
                }
                action={t('Выложить материал')}
                onAction={() => setTab('mine')}
              />
            }
          />
        </>
      )}

      {current === 'mine' && (
        <MyMaterials
          onDone={(text) => {
            setFlash(text)
            setTab('mine')
          }}
          onOpen={(row) => navigate(`/materials/${row.id}`)}
        />
      )}

      {current === 'requests' && <Requests />}

      {current === 'collections' && (
        <Collections isCurator={isCurator} onOpen={(row) => navigate(`/materials/${row.id}`)} />
      )}

      {current === 'queue' && isCurator && (
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
            <Badge variant="mute">{row.author_name}</Badge>
            <Badge variant="mute">{row.source_kind_title}</Badge>
            {row.files.length > 0 && (
              <Badge variant="mute" className="num">
                {counted(row.files.length, ['файл', 'файла', 'файлов'])}
              </Badge>
            )}
            {row.helpful_count > 0 && (
              <Badge variant="ok" className="num">
                полезно: {row.helpful_count}
              </Badge>
            )}
            {row.status !== 'approved' && <Badge variant="warn">{row.status_title}</Badge>}
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
  // «свои» — и у ученика, и у директора талантов: сервер сам понимает,
  // чьи это материалы. Раньше Арману сюда приезжала вся библиотека
  const all = useMaterials({ mine: 'true' })
  // форма нужна обоим: раздел ведёт Арман, и свои разборы он кладёт
  // туда же. Его материалы модерации не требуют — он и есть проверка
  const [open, setOpen] = useState(false)
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
        setOpen(false)
        onDone(
          isStudent
            ? 'Материал отправлен на проверку. Как только его одобрят, он появится в библиотеке'
            : 'Материал выложен и уже в библиотеке',
        )
      },
      onError: (error) => setProblem(String((error as Error).message)),
    })
  }

  return (
    <div>
      <div className="toolbar">
        <span className="muted">
          {isStudent
            ? t('Ваши разборы — и те, что ждут проверки, и те, что её не прошли')
            : t('Ваши разборы: они попадают в библиотеку сразу, без очереди')}
        </span>
        <span className="toolbar__spacer" />
        <Button size="sm" onClick={() => setOpen(!open)}>
          {open ? t('Отмена') : t('Выложить материал')}
        </Button>
      </div>

      {open && (
        <div className="card card-pad mat__form">
          <span className="eyebrow">{t('Выложить материал')}</span>
          <p className="muted mat__hint">{state.data?.limits.hint}</p>
          <div className="mat__fields">
            <label className="mat__field">
              {t('Предмет')}
              <SelectField
                value={form.subject}
                onChange={(event) => setForm({ ...form, subject: event.target.value })}
              >
                <option value="">{t('выберите')}</option>
                {(subjects.data?.results ?? [])
                  .filter((row) => row.is_active)
                  .map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
              </SelectField>
            </label>
            <label className="mat__field">
              {t('Тема')}
              <Input
                placeholder={t('Механика')}
                value={form.topic}
                onChange={(event) => setForm({ ...form, topic: event.target.value })}
              />
            </label>
            <label className="mat__field mat__field--wide">
              {t('Название')}
              <Input
                placeholder={t('Разбор задач областного этапа')}
                value={form.title}
                onChange={(event) => setForm({ ...form, title: event.target.value })}
              />
            </label>
            <label className="mat__field mat__field--wide">
              {t('Описание')}
              <Input
                placeholder={t('Что внутри и кому пригодится')}
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
            </label>
            <label className="mat__field">
              {t('Что это за материал')}
              <SelectField
                value={form.source_kind}
                onChange={(event) => setForm({ ...form, source_kind: event.target.value })}
              >
                {SOURCE_KIND.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.title}
                  </option>
                ))}
              </SelectField>
            </label>
            <label className="mat__field">
              {t('Закрывает запрос')}
              <SelectField
                value={form.request}
                onChange={(event) => setForm({ ...form, request: event.target.value })}
              >
                <option value="">{t('ничей запрос')}</option>
                {openRequests.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.subject_name}: {row.topic}
                  </option>
                ))}
              </SelectField>
            </label>
            <label className="mat__field">
              {t('Файлы')}
              <span className="mat__file">
                <input
                  type="file"
                  multiple
                  accept=".pdf,.jpg,.jpeg,.png"
                  aria-label={t('Файлы материала')}
                  onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                />
                <Button variant="outline" size="sm" nativeButton={false} render={<span />}>
                  {t('Выбрать файлы')}
                </Button>
                <span className="muted">
                  {files.length === 0
                    ? 'ничего не выбрано'
                    : counted(files.length, ['файл', 'файла', 'файлов'])}
                </span>
              </span>
            </label>
          </div>

          <label className="mat__rights">
            <Checkbox checked={form.rights} onCheckedChange={(on) => setForm({ ...form, rights: on })} />
            <span>
              {t(
                'Подтверждаю, что имею право это публиковать. Официальные задания, которые ещё не опубликованы, и сканы чужих учебников выкладывать нельзя — претензии придут школе.',
              )}
            </span>
          </label>

          {problem && (
            <Badge variant="risk" className="badge--line">
              {problem}
            </Badge>
          )}
          <Button size="sm" disabled={actions.upload.isPending} onClick={submit}>
            {actions.upload.isPending ? 'Отправляем…' : isStudent ? 'Отправить на проверку' : 'Выложить'}
          </Button>
        </div>
      )}

      <h2 className="section">{t('Загруженное')}</h2>
      {rows.length > 0 && (
        <ul className="rows__list mat__own">
          {rows.map((row) => (
            <li key={row.id} className="rows__item">
              <div className="rows__body">
                <button className="cell cell-link" onClick={() => onOpen(row)}>
                  {row.title}
                </button>
                <span className="rows__actions">
                  <Badge variant="mute">{row.status_title}</Badge>
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={actions.removeMaterial.isPending}
                    onClick={() => actions.removeMaterial.mutate(row.id)}
                  >
                    {t('Убрать')}
                  </Button>
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
      {all.isLoading && <Loading />}
      {rows.length === 0 && !all.isLoading && (
        <Empty
          icon="openbook"
          title={t('Вы ещё ничего не выкладывали')}
          what={t('Выложите первый разбор — то, что разобрали для себя, обычно нужно ещё пятерым.')}
          hint={t(
            'Здесь будут ваши материалы: и те, что ждут проверки, и те, что её не прошли — вместе с причиной.',
          )}
          action={t('Выложить материал')}
          onAction={() => setOpen(true)}
        />
      )}
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
          <span className="eyebrow">{t('Попросить разбор')}</span>
          <p className="muted mat__hint">
            {t('Запрос увидят все в группе. Откликнуться может любой — загрузкой материала.')}
          </p>
          <div className="mat__fields">
            <label className="mat__field">
              {t('Предмет')}
              <SelectField
                value={form.subject}
                onChange={(event) => setForm({ ...form, subject: event.target.value })}
              >
                <option value="">{t('выберите')}</option>
                {(subjects.data?.results ?? [])
                  .filter((row) => row.is_active)
                  .map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
              </SelectField>
            </label>
            <label className="mat__field mat__field--wide">
              {t('Тема')}
              <Input
                placeholder={t('Термодинамика: второе начало')}
                value={form.topic}
                onChange={(event) => setForm({ ...form, topic: event.target.value })}
              />
            </label>
            <label className="mat__field mat__field--wide">
              {t('Что именно нужно')}
              <Input value={form.text} onChange={(event) => setForm({ ...form, text: event.target.value })} />
            </label>
          </div>
          {problem && (
            <Badge variant="risk" className="badge--line">
              {problem}
            </Badge>
          )}
          <Button
            size="sm"
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
            {t('Попросить')}
          </Button>
        </div>
      )}

      {rows.length === 0 ? (
        <Empty
          icon="openbook"
          title={t('Запросов пока нет')}
          what={t(
            'Если по какой-то теме не хватает разбора — попросите. Кто-нибудь из группы наверняка её уже разбирал.',
          )}
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
                <Badge variant={row.status === 'open' ? 'warn' : 'ok'}>{row.status_title}</Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="muted mat__note" hidden={rows.length === 0}>
        {t(
          'Чтобы закрыть запрос, выложите материал и укажите его в поле «Закрывает запрос» — запрос закроется, когда материал пройдёт проверку.',
        )}
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
          <span className="eyebrow">{t('Собрать подборку')}</span>
          <div className="mat__fields">
            <label className="mat__field mat__field--wide">
              {t('Название')}
              <Input
                placeholder={t('Подготовка к республиканскому этапу по физике')}
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </label>
            <label className="mat__field">
              {t('Предмет')}
              <SelectField
                value={form.subject}
                onChange={(event) => setForm({ ...form, subject: event.target.value })}
              >
                <option value="">{t('без предмета')}</option>
                {(subjects.data?.results ?? []).map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </SelectField>
            </label>
            <label className="mat__field mat__field--wide">
              {t('Описание')}
              <Input
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
            </label>
          </div>
          <Button
            size="sm"
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
            {t('Создать')}
          </Button>
        </div>
      )}

      {rows.length === 0 ? (
        <Empty
          icon="openbook"
          title={t('Подборок пока нет')}
          what={
            isCurator
              ? 'Подборка — это маршрут: несколько материалов в нужном порядке. «Подготовка к республиканскому этапу по физике» полезнее, чем двадцать разрозненных файлов.'
              : 'Директор талантов соберёт материалы в тематические наборы — тогда они появятся здесь.'
          }
        />
      ) : (
        rows.map((collection) => (
          <div key={collection.id} className="card card-pad mat__collection">
            <div className="row-between">
              <span className="eyebrow">
                {collection.name}
                {collection.subject_name ? ` · ${collection.subject_name}` : ''}
              </span>
              {isCurator && (
                <span className="rows__actions">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const name = window.prompt('Новое название подборки', collection.name)
                      if (name && name.trim())
                        actions.updateCollection.mutate({
                          id: collection.id,
                          name: name.trim(),
                          description: collection.description,
                        })
                    }}
                  >
                    {t('Переименовать')}
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => actions.removeCollection.mutate(collection.id)}
                  >
                    {t('Убрать подборку')}
                  </Button>
                </span>
              )}
            </div>
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
            {collection.items.length === 0 && <p className="muted rows__empty">{t('Пока пусто')}</p>}
            {isCurator && (
              <div className="toolbar">
                <SelectField
                  aria-label={t('Материал для подборки')}
                  value={picked[collection.id] ?? ''}
                  onChange={(event) => setPicked({ ...picked, [collection.id]: event.target.value })}
                >
                  <option value="">{t('выберите материал')}</option>
                  {(library.data?.results ?? []).map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.title}
                    </option>
                  ))}
                </SelectField>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!picked[collection.id]}
                  onClick={() =>
                    actions.addToCollection.mutate({
                      id: collection.id,
                      material: Number(picked[collection.id]),
                      position: (collection.items.length + 1) * 10,
                    })
                  }
                >
                  {t('Добавить в подборку')}
                </Button>
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
      <Badge variant="mute" className="badge--line mat__flash">
        {queue.data?.summary}
      </Badge>

      {pending.length === 0 && reports.length === 0 && (
        <Empty
          icon="openbook"
          title={t('Очередь пуста')}
          what={t('Новые материалы и жалобы будут появляться здесь. Пока разбирать нечего.')}
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
            <Badge variant="mute">{row.author_name}</Badge>
            <Badge variant={row.source_kind === 'third_party' ? 'warn' : 'mute'}>
              {row.source_kind_title}
            </Badge>
            <Badge variant={row.rights_confirmed ? 'ok' : 'risk'}>
              {row.rights_confirmed ? 'право на публикацию подтверждено' : 'право не подтверждено'}
            </Badge>
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
          {row.files.length === 0 && <p className="muted rows__empty">{t('Файлов нет — только текст')}</p>}

          <div className="toolbar">
            <Button
              size="sm"
              onClick={() =>
                actions.review.mutate(
                  { id: row.id, decision: 'approve' },
                  { onSuccess: (answer) => onFlash(answer.detail) },
                )
              }
            >
              {t('Одобрить')}
            </Button>
            <Input
              placeholder={t('Причина отклонения')}
              aria-label={`Причина отклонения материала «${row.title}»`}
              value={reason[row.id] ?? ''}
              onChange={(event) => setReason({ ...reason, [row.id]: event.target.value })}
            />
            <Button
              variant="destructive"
              size="sm"
              disabled={!(reason[row.id] ?? '').trim()}
              onClick={() =>
                actions.review.mutate(
                  { id: row.id, decision: 'reject', reason: reason[row.id] },
                  { onSuccess: (answer) => onFlash(answer.detail) },
                )
              }
            >
              {t('Отклонить')}
            </Button>
          </div>
        </div>
      ))}

      {reports.length > 0 && (
        <>
          <h2 className="section">{t('Жалобы')}</h2>
          {reports.map((row) => (
            <div key={row.id} className="card card-pad mat__review">
              <span className="eyebrow">Пожаловался {row.reporter_name}</span>
              <p>{row.reason}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  actions.resolveReport.mutate(
                    { id: row.id, resolution: 'Разобрано' },
                    { onSuccess: (answer) => onFlash(answer.detail) },
                  )
                }
              >
                {t('Пометить разобранной')}
              </Button>
            </div>
          ))}
        </>
      )}
    </div>
  )
}
