/**
 * Конструктор эссе (фаза 43).
 *
 * Ученик создаёт эссе: выбирает тип документа, проходит обучающий гайд,
 * отвечает на три вопроса быстрой проверки, попадает в редактор. Сбоку —
 * чат с помощником, который **задаёт вопросы, но не пишет текст за ученика**
 * (кнопок «улучшить» и «переписать» нет вовсе). Вся переписка видна куратору.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  useAddEssayVersion,
  useAskEssay,
  useCreateEssay,
  useEssayAssistLog,
  useEssayDocType,
  useEssayDocTypes,
  useEssayRequirements,
  useMyEssays,
  useReadingOfDay,
  useSubmitEssay,
  type Essay,
  type EssayDocType,
} from '../api/hooks'
import Empty from '../components/Empty'
import { Row, Rows, Tile } from '../components/patterns'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import { NativeSelect } from '../components/ui/native-select'
import { t } from '../i18n'
import { Textarea } from '../components/ui/textarea'
import { Input } from '../components/ui/input'
import { Button } from '../components/ui/button'
import { Badge, type BadgeVariant } from '../components/ui/badge'

const STATUS_TONE: Record<string, BadgeVariant> = {
  draft: 'mute',
  review: 'warn',
  revision: 'risk',
  done: 'ok',
}
const STATUS_TITLE: Record<string, string> = {
  draft: 'Черновик',
  review: 'На проверке',
  revision: 'Правки',
  done: 'Готово',
}
const GUIDE_SKIPPED = 'essay.guide.seen'

function lines(text: string): string[] {
  return text.split('\n').filter((l) => l.trim())
}

/** Строка «Чтение дня» сверху раздела. */
function ReadingOfDay() {
  const { data } = useReadingOfDay()
  const example = data?.example
  if (!example) return null
  return (
    <div className="card card-pad essay__reading">
      <Rows>
        <Row
          icon="openbook"
          tone="indigo"
          title={
            <>
              <span className="essay__readinglabel">{t('Чтение дня')}</span>
              {example.title}
            </>
          }
          note={
            example.doc_type_name
              ? `${example.doc_type_name}${example.body ? ` · ${example.body.slice(0, 90)}` : ''}`
              : example.body?.slice(0, 120)
          }
          onOpen={() => (example.source_url ? window.open(example.source_url) : undefined)}
          openLabel={t('Открыть пример')}
        />
      </Rows>
    </div>
  )
}

/** Обучающий гайд из четырёх шагов перед первым эссе этого типа. */
function Guide({ docType, onDone }: { docType: EssayDocType; onDone: () => void }) {
  const [step, setStep] = useState(0)
  const guide = docType.guide
  const steps = [
    { title: 'Что это за документ', body: guide?.what_is ? [guide.what_is] : [] },
    { title: 'Какие бывают вопросы', body: lines(guide?.prompts ?? '') },
    { title: 'Частые ошибки', body: lines(guide?.mistakes ?? '') },
    { title: 'Советы', body: lines(guide?.tips ?? '') },
  ]
  const current = steps[step]
  // гайд по типу ещё не заполнен: четыре шага подряд со словами «куратор
  // ещё не заполнил этот шаг» — это не обучение, а четыре лишних нажатия.
  // Пропускаем его целиком (фаза 47)
  const empty = steps.every((row) => row.body.length === 0)
  const skipped = useRef(false)
  useEffect(() => {
    if (empty && !skipped.current) {
      skipped.current = true
      onDone()
    }
  }, [empty, onDone])
  if (empty) return <Loading />

  return (
    <div className="card card-pad">
      <div className="row-between">
        <span className="eyebrow">
          {t('Гайд')}: {docType.name} · {step + 1}/4
        </span>
        <Button variant="ghost" size="sm" onClick={onDone}>
          {t('Пропустить гайд')}
        </Button>
      </div>
      <h3 className="essay__steptitle">{t(current.title)}</h3>
      {current.body.length === 0 ? (
        <p className="muted essay__note">{t('Куратор ещё не заполнил этот шаг.')}</p>
      ) : (
        <ul className="essay__list">
          {current.body.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      )}
      <div className="propose__actions">
        {step > 0 && (
          <Button variant="outline" size="sm" onClick={() => setStep(step - 1)}>
            {t('Назад')}
          </Button>
        )}
        {step < 3 ? (
          <Button size="sm" onClick={() => setStep(step + 1)}>
            {t('Дальше')}
          </Button>
        ) : (
          <Button size="sm" onClick={onDone}>
            {t('К быстрой проверке')}
          </Button>
        )}
      </div>
    </div>
  )
}

/** Быстрая проверка: три вопроса, ответ подсвечивается сразу с объяснением. */
function QuickCheck({ docType, onDone }: { docType: EssayDocType; onDone: () => void }) {
  const questions = docType.check_questions.slice(0, 3)
  const [picked, setPicked] = useState<Record<number, string>>({})

  // Проверка по типу не заведена — сразу редактор. Побочное действие живёт
  // в эффекте, а не в отрисовке: вызов `onDone()` прямо в render React
  // отбрасывает, и на пустом справочнике ученик застревал на шаге,
  // с которого некуда нажать (найдено сквозным прогоном фазы 47)
  const jumped = useRef(false)
  useEffect(() => {
    if (questions.length === 0 && !jumped.current) {
      jumped.current = true
      onDone()
    }
  }, [questions.length, onDone])
  if (questions.length === 0) return <Loading />

  const options = (q: (typeof questions)[number]) =>
    [
      ['A', q.option_a],
      ['B', q.option_b],
      ['C', q.option_c],
      ['D', q.option_d],
    ].filter(([, text]) => text) as [string, string][]

  return (
    <div className="card card-pad">
      <span className="eyebrow">{t('Быстрая проверка')}</span>
      <p className="muted essay__note">{t('Это закрепление, а не оценка — результат никуда не идёт.')}</p>
      {questions.map((q) => {
        const chosen = picked[q.id]
        return (
          <div key={q.id} className="essay__check">
            <p className="essay__q">{q.text}</p>
            <div className="essay__options">
              {options(q).map(([letter, text]) => {
                const isChosen = chosen === letter
                const cls = chosen
                  ? letter === q.correct
                    ? ' essay__opt--right'
                    : isChosen
                      ? ' essay__opt--wrong'
                      : ''
                  : ''
                return (
                  <button
                    key={letter}
                    className={`essay__opt${cls}`}
                    disabled={!!chosen}
                    onClick={() => setPicked((prev) => ({ ...prev, [q.id]: letter }))}
                  >
                    <b>{letter}.</b> {text}
                  </button>
                )
              })}
            </div>
            {chosen && q.explanation && <p className="muted essay__note">{q.explanation}</p>}
          </div>
        )
      })}
      <div className="propose__actions">
        <Button size="sm" onClick={onDone}>
          {t('К редактору')}
        </Button>
      </div>
    </div>
  )
}

/** Чат с помощником: задаёт вопросы, текст эссе не пишет. */
function AssistChat({ essay }: { essay: Essay }) {
  const log = useEssayAssistLog(essay.id)
  const ask = useAskEssay()
  const [prompt, setPrompt] = useState('')

  return (
    <div className="card card-pad essay__chat">
      <span className="eyebrow">{t('Помощник по эссе')}</span>
      <p className="muted essay__note">
        {t('Помощник задаёт вопросы, чтобы раскрыть вашу историю. Текст эссе он не пишет.')}
      </p>
      <div className="essay__chatlog">
        {(log.data?.results ?? []).map((entry) => (
          <div key={entry.id} className="essay__chatentry">
            <p className="essay__chatprompt">{entry.prompt}</p>
            <ul className="essay__list">
              {entry.questions.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <Textarea
        rows={2}
        value={prompt}
        placeholder={t('Расскажите о своей истории — помощник задаст вопросы')}
        onChange={(e) => setPrompt(e.target.value)}
      />
      <div className="propose__actions">
        <Button
          size="sm"
          disabled={ask.isPending || prompt.trim() === ''}
          onClick={() =>
            ask.mutate(
              { essay: essay.id, prompt },
              {
                onSuccess: () => {
                  setPrompt('')
                  setTimeout(() => log.refetch(), 1500)
                },
                onError: (error) => toast.error(error.message),
              },
            )
          }
        >
          {t('Спросить помощника')}
        </Button>
      </div>
    </div>
  )
}

/** Редактор: автосохранение, счётчик слов с лимитом, статусы, чат. */
function Editor({ essay }: { essay: Essay }) {
  const current = essay.versions[0]
  const [text, setText] = useState(current?.text ?? '')
  const addVersion = useAddEssayVersion()
  const submit = useSubmitEssay()
  const words = text.trim() ? text.trim().split(/\s+/).length : 0
  const limit = essay.effective_word_limit
  const [savedText, setSavedText] = useState(current?.text ?? '')

  // автосохранение: снимок уходит через паузу после последней правки
  useEffect(() => {
    if (text === savedText || text.trim() === '') return
    const timer = window.setTimeout(() => {
      addVersion.mutate({ id: essay.id, text }, { onSuccess: () => setSavedText(text) })
    }, 2500)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text])

  return (
    <div className="essay__editorgrid">
      <div className="card card-pad">
        <Textarea
          className="essay__editor"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={16}
          placeholder={t('Пишите здесь. Текст сохраняется автоматически, прежние версии остаются в истории.')}
        />
        <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
          <Badge variant={words > limit ? 'risk' : 'mute'} className="num">
            {words} / {limit} {t('слов')}
          </Badge>
          <span className="muted essay__note">
            {text === savedText ? t('сохранено') : addVersion.isPending ? t('сохраняю…') : t('черновик')}
          </span>
          <span className="toolbar__spacer" />
          <Button
            variant="outline"
            size="sm"
            disabled={addVersion.isPending || text.trim() === ''}
            onClick={() => addVersion.mutate({ id: essay.id, text }, { onSuccess: () => setSavedText(text) })}
          >
            {t('Сохранить версию')}
          </Button>
          <Button
            size="sm"
            disabled={submit.isPending || essay.status === 'review'}
            onClick={() =>
              submit.mutate(essay.id, {
                onSuccess: () => toast.success(t('Отправлено куратору')),
                onError: (error) => toast.error(error.message),
              })
            }
          >
            {t('Отправить куратору')}
          </Button>
        </div>

        {essay.comments.length > 0 && (
          <div style={{ marginTop: 18, paddingTop: 16, borderTop: '1px solid var(--line)' }}>
            <span className="eyebrow">{t('Комментарии куратора')}</span>
            {essay.comments.map((comment) => (
              <div key={comment.id} style={{ marginTop: 12, fontSize: 13 }}>
                <b>{comment.author_name}</b>{' '}
                <span className="muted" style={{ fontSize: 12 }}>
                  {new Date(comment.created_at).toLocaleDateString('ru')}
                </span>
                <p style={{ margin: '4px 0 0' }}>{comment.text}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <AssistChat essay={essay} />
    </div>
  )
}

/** Создание эссе: выбор типа плитками + требования вузов. */
function TypePicker({ onCreated }: { onCreated: (essay: Essay) => void }) {
  const types = useEssayDocTypes()
  const requirements = useEssayRequirements()
  const create = useCreateEssay()
  const [query, setQuery] = useState('')
  const [title, setTitle] = useState('')

  const filtered = (types.data?.results ?? []).filter((row) =>
    row.name.toLowerCase().includes(query.toLowerCase()),
  )

  const pick = (docType: EssayDocType) => {
    create.mutate(
      {
        essay_type: docType.code === 'no_type' ? 'personal_statement' : docType.code.slice(0, 24),
        doc_type: docType.id,
        title: title.trim() || docType.name,
      },
      { onSuccess: onCreated, onError: (error) => toast.error(error.message) },
    )
  }

  return (
    <div>
      {requirements.data && (
        <div className="card card-pad essay__requirements">
          <span className="eyebrow">{t('Требования вашим университетам')}</span>
          {requirements.data.has_data ? (
            <ul className="essay__list">
              {requirements.data.requirements.slice(0, 6).map((r, i) => (
                <li key={i}>
                  <b>{r.university}</b> · {r.program} — <span className="muted">{r.note}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted essay__note">{t('Список вузов пуст — выберите тип вручную ниже.')}</p>
          )}
        </div>
      )}

      <div className="card card-pad">
        <span className="eyebrow">{t('Новое эссе')}</span>
        <div className="toolbar" style={{ marginTop: 12 }}>
          <Input placeholder={t('Название эссе')} value={title} onChange={(e) => setTitle(e.target.value)} />
          <Input placeholder={t('Поиск по типу')} value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="essay__types">
          {filtered.map((docType) => (
            <button
              key={docType.id}
              className="essay__type"
              disabled={create.isPending}
              onClick={() => pick(docType)}
            >
              <b>{docType.name}</b>
              <span className="muted">{docType.description}</span>
              <span className="muted num">
                {t('лимит')} {docType.default_word_limit} {t('слов')}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

/** Поток создания: тип → гайд → проверка → редактор. */
function NewEssay({ onOpen }: { onOpen: (id: number) => void }) {
  const [stage, setStage] = useState<'type' | 'guide' | 'check'>('type')
  const [essayId, setEssayId] = useState<number | null>(null)
  const [docTypeId, setDocTypeId] = useState<number | null>(null)
  const docType = useEssayDocType(docTypeId)

  const created = (essay: Essay) => {
    setEssayId(essay.id)
    setDocTypeId(essay.doc_type)
    // гайд показывается один раз на тип; иначе сразу к проверке
    const seen = JSON.parse(localStorage.getItem(GUIDE_SKIPPED) ?? '[]') as number[]
    setStage(essay.doc_type && seen.includes(essay.doc_type) ? 'check' : 'guide')
  }

  const markGuideSeen = () => {
    if (docTypeId) {
      const seen = new Set(JSON.parse(localStorage.getItem(GUIDE_SKIPPED) ?? '[]') as number[])
      seen.add(docTypeId)
      localStorage.setItem(GUIDE_SKIPPED, JSON.stringify([...seen]))
    }
    setStage('check')
  }

  if (stage === 'type') return <TypePicker onCreated={created} />
  if (!docType.data) return <Loading />
  if (stage === 'guide') return <Guide docType={docType.data} onDone={markGuideSeen} />
  return <QuickCheck docType={docType.data} onDone={() => essayId && onOpen(essayId)} />
}

export default function Essays() {
  const { data, isLoading, error } = useMyEssays()
  const [openId, setOpenId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  const essays = useMemo(() => data?.results ?? [], [data])
  // типы берём из самих эссе: справочник ведёт директор, и список
  // здесь — то, что у ученика реально есть
  const essayTypes = useMemo(
    () => [...new Set(essays.map((essay) => essay.doc_type_name).filter(Boolean))] as string[],
    [essays],
  )
  const shown = essays.filter(
    (essay) =>
      (!statusFilter || essay.status === statusFilter) && (!typeFilter || essay.doc_type_name === typeFilter),
  )

  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />

  if (creating) {
    return (
      <div>
        <ScreenHead
          title={t('Новое эссе')}
          subtitle={t('Выберите тип, пройдите гайд и быструю проверку — потом редактор.')}
          actions={
            <Button variant="outline" size="sm" onClick={() => setCreating(false)}>
              {t('Отмена')}
            </Button>
          }
        />
        <NewEssay
          onOpen={(id) => {
            setCreating(false)
            setOpenId(id)
          }}
        />
      </div>
    )
  }

  return (
    <div>
      <ScreenHead
        title={t('Эссе')}
        subtitle={t('Черновики, версии и замечания куратора.')}
        actions={
          <>
            <NativeSelect
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              aria-label={t('Статус')}
            >
              <option value="">{t('Любой статус')}</option>
              {Object.entries(STATUS_TITLE).map(([value, title]) => (
                <option key={value} value={value}>
                  {t(title)}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value)}
              aria-label={t('Тип документа')}
            >
              <option value="">{t('Любой тип')}</option>
              {essayTypes.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </NativeSelect>
            <Button onClick={() => setCreating(true)}>{t('Новое эссе')}</Button>
          </>
        }
      />

      <ReadingOfDay />

      {essays.length === 0 && (
        <Empty
          icon="doc"
          title={t('Эссе ещё не заведены')}
          what={t('Создайте эссе: выберите тип, пройдите гайд — и пишите.')}
          action={t('Новое эссе')}
          onAction={() => setCreating(true)}
        />
      )}

      {/* Карточка эссе: иконка, название, тип серым, чип статуса справа;
          через тонкую линию — дата слева и счётчик слов справа */}
      <div className="essay__list">
        {shown.map((essay) => {
          const last = essay.versions[essay.versions.length - 1]
          return (
            <section key={essay.id} className="essay__item">
              <button
                className={`card essay__card${openId === essay.id ? ' essay__card--open' : ''}`}
                onClick={() => setOpenId(openId === essay.id ? null : essay.id)}
              >
                <span className="essay__cardhead">
                  <Tile icon="doc" tone="brand" size="lg" />
                  <span className="essay__cardtext">
                    <b>{essay.title}</b>
                    <span className="muted">
                      {essay.doc_type_name ?? essay.program_name ?? t('Общее эссе')}
                    </span>
                  </span>
                  <Badge variant={STATUS_TONE[essay.status]}>{t(STATUS_TITLE[essay.status])}</Badge>
                </span>
                <span className="essay__cardfoot">
                  <span className="muted">
                    {last ? new Date(last.created_at).toLocaleDateString('ru') : t('без версий')}
                  </span>
                  <span className="muted num">
                    {last ? `${last.word_count} / ${essay.effective_word_limit} ${t('слов')}` : '—'}
                  </span>
                </span>
              </button>
              {openId === essay.id && <Editor essay={essay} />}
            </section>
          )
        })}
      </div>
    </div>
  )
}
