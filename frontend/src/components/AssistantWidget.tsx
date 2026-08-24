/**
 * Помощник в углу: круглая кнопка справа внизу и панель диалога.
 *
 * Быстрые кнопки на правилах работают без ключа модели; свободный ввод
 * без ключа получает честный отказ. Любое изменение данных приходит
 * предложением — карточка предпросмотра показывается прямо в панели,
 * применяет человек (инвариант №3).
 */
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  useApplySuggestion,
  useAssistantAsk,
  useAssistantQuick,
  useAssistantThread,
  useAssistantThreads,
  useParseImage,
  useRejectSuggestion,
  useSuggestion,
  useTaskPolling,
  type AssistantQuickButton,
  type ParseResult,
} from '../api/hooks'
import { useAssistantScreen } from '../assistant/context'
import { useAuth } from '../auth/AuthContext'
import { LOGO } from '../branding'
import { t } from '../i18n'
import { counted } from './ui'
import './assistant-widget.css'

/** Карточка предложения в панели: что изменится, у кого, сколько записей. */
function SuggestionCard({ id, affected }: { id: number; affected: number }) {
  const navigate = useNavigate()
  const { data } = useSuggestion(id)
  const { apply } = useApplySuggestion()
  const reject = useRejectSuggestion()
  const [note, setNote] = useState<string | null>(null)

  if (!data) return null
  const students = new Set(data.changes.map((c) => c.student_name).filter(Boolean))
  const done = data.status !== 'pending' && data.status !== 'draft'

  return (
    <div className="aw__card">
      <b>{data.command_title || t('Предложение')}</b>
      <p className="muted aw__cardmeta">
        {counted(data.changes.length, [t('запись'), t('записи'), t('записей')])}
        {students.size > 0 && <> · {counted(students.size, [t('ученик'), t('ученика'), t('учеников')])}</>}
        {affected > 0 && students.size === 0 && (
          <> · {counted(affected, [t('ученик'), t('ученика'), t('учеников')])}</>
        )}
      </p>
      <ul className="aw__changes">
        {data.changes.slice(0, 4).map((change) => (
          <li key={change.id}>
            {change.student_name ? `${change.student_name}: ` : ''}
            {change.field_title} — {change.new_display || change.new_value}
          </li>
        ))}
        {data.changes.length > 4 && (
          <li className="muted">
            {t('ещё')} {data.changes.length - 4}
          </li>
        )}
      </ul>
      {done ? (
        <p className="chip chip-mute">{data.status_title}</p>
      ) : (
        <div className="aw__cardactions">
          <button
            className="btn btn-primary btn-sm"
            disabled={apply.isPending}
            onClick={() =>
              apply.mutate(
                { id },
                {
                  onSuccess: (result) => setNote(`${t('Применено строк:')} ${result.applied}`),
                  onError: (error) => setNote(String((error as Error).message)),
                },
              )
            }
          >
            {t('Применить')}
          </button>
          <button
            className="btn btn-ghost btn-sm"
            disabled={reject.isPending}
            onClick={() => reject.mutate(id, { onSuccess: () => setNote(t('Отклонено')) })}
          >
            {t('Отклонить')}
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/suggestions/${id}`)}>
            {t('Выбрать строки')}
          </button>
        </div>
      )}
      {note && <p className="chip chip-ok">{note}</p>}
    </div>
  )
}

/** Разбор изображения: грамота или скрин с баллами — через фоновую задачу. */
function ImageFlow({ kind, studentId }: { kind: 'certificate' | 'scores'; studentId: number | null }) {
  const parse = useParseImage()
  const [taskId, setTaskId] = useState<string | null>(null)
  const poll = useTaskPolling<ParseResult>(taskId)
  const fileRef = useRef<HTMLInputElement>(null)

  const result = poll.data?.state === 'SUCCESS' ? poll.data.result : null

  if (studentId === null) {
    return (
      <p className="muted aw__hint">
        {t('Сначала откройте карточку ученика или отметьте одного в таблице.')}
      </p>
    )
  }

  return (
    <div className="aw__image">
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="aw__file"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) parse.mutate({ file, student: studentId, kind }, { onSuccess: (r) => setTaskId(r.task) })
        }}
      />
      <button className="btn btn-ghost btn-sm" onClick={() => fileRef.current?.click()}>
        {t('Выбрать изображение')}
      </button>
      {taskId && !result && <p className="muted aw__hint">{t('Обрабатываю…')}</p>}
      {result && !result.suggestion && <p className="muted aw__hint">{result.detail}</p>}
      {result?.suggestion && <SuggestionCard id={result.suggestion} affected={0} />}
    </div>
  )
}

export default function AssistantWidget() {
  const { me } = useAuth()
  const location = useLocation()
  const { students } = useAssistantScreen()
  const [open, setOpen] = useState(false)
  const [full, setFull] = useState(false)
  const [view, setView] = useState<'chat' | 'history'>('chat')
  const [threadId, setThreadId] = useState<number | null>(null)
  const [input, setInput] = useState('')
  const [pending, setPending] = useState<AssistantQuickButton | null>(null)
  const [imageKind, setImageKind] = useState<'certificate' | 'scores' | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  // почему последний ответ проще обычного: ключа нет, лимит выбран
  // или модель не ответила. Молчать об этом нельзя — иначе выглядит
  // как будто помощник поглупел без причины
  const [note, setNote] = useState<string | null>(null)

  const quick = useAssistantQuick(open)
  const threads = useAssistantThreads(open && view === 'history')
  const thread = useAssistantThread(threadId)
  const ask = useAssistantAsk()
  const bottom = useRef<HTMLDivElement>(null)

  const messages = thread.data?.messages ?? []
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, open])

  if (!me) return null

  const send = (command?: AssistantQuickButton, text?: string) => {
    setProblem(null)
    setImageKind(null)
    const body = {
      thread: threadId,
      command: command?.code ?? '',
      text: (text ?? '').trim(),
      students,
      screen: location.pathname,
    }
    if (!body.command && !body.text) return
    ask.mutate(body, {
      onSuccess: (result) => {
        setThreadId(result.thread.id)
        setInput('')
        setPending(null)
        setNote(result.note || null)
      },
      onError: (error) => setProblem(String((error as Error).message)),
    })
  }

  const press = (button: AssistantQuickButton) => {
    setProblem(null)
    setNote(null)
    if (button.needs === 'image') {
      setImageKind(button.code === 'parse_certificate' ? 'certificate' : 'scores')
      return
    }
    if (button.needs === 'text') {
      setPending(button)
      setImageKind(null)
      return
    }
    send(button)
  }

  const newDialog = () => {
    setThreadId(null)
    setView('chat')
    setPending(null)
    setImageKind(null)
  }

  if (!open) {
    return (
      <button className="aw__fab" aria-label={t('Открыть помощника')} onClick={() => setOpen(true)}>
        <img src={LOGO.assistant} alt="" />
      </button>
    )
  }

  return (
    <div className={`aw${full ? ' aw--full' : ''}`}>
      <div className="aw__head">
        <img className="aw__logo" src={LOGO.assistant} alt="" />
        <b className="aw__title">{t('Помощник')}</b>
        <div className="aw__tools">
          <button className="aw__tool" title={t('Новый диалог')} onClick={newDialog}>
            +
          </button>
          <button
            className="aw__tool"
            title={t('История диалогов')}
            onClick={() => setView(view === 'history' ? 'chat' : 'history')}
          >
            ≡
          </button>
          <button
            className="aw__tool"
            title={full ? t('Обычный размер') : t('Развернуть')}
            onClick={() => setFull((v) => !v)}
          >
            ⤢
          </button>
          <button className="aw__tool" title={t('Свернуть')} onClick={() => setOpen(false)}>
            ×
          </button>
        </div>
      </div>

      {view === 'history' ? (
        <div className="aw__body">
          {(threads.data ?? []).length === 0 && <p className="muted aw__hint">{t('Диалогов пока нет.')}</p>}
          {(threads.data ?? []).map((row) => (
            <button
              key={row.id}
              className="aw__thread"
              onClick={() => {
                setThreadId(row.id)
                setView('chat')
              }}
            >
              <span className="aw__threadtitle">{row.title || t('Диалог')}</span>
              <span className="muted aw__threadwhen">
                {new Date(row.updated_at).toLocaleDateString('ru')}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <div className="aw__body">
          {messages.length === 0 && (
            <p className="aw__greeting">
              {t('Здравствуйте! Выберите быструю кнопку или напишите вопрос.')}
              {quick.data && !quick.data.model.available && (
                <span className="muted aw__hint"> {quick.data.model.detail}</span>
              )}
            </p>
          )}

          <div className="aw__quick">
            {(quick.data?.buttons ?? []).map((button) => (
              <button
                key={button.code}
                className="aw__quickbtn"
                title={button.hint}
                disabled={ask.isPending}
                onClick={() => press(button)}
              >
                {button.title}
              </button>
            ))}
          </div>

          {students.length > 0 && (
            <p className="muted aw__hint">
              {t('Контекст экрана:')} {counted(students.length, [t('ученик'), t('ученика'), t('учеников')])}
            </p>
          )}
          {imageKind && <ImageFlow kind={imageKind} studentId={students.length === 1 ? students[0] : null} />}

          {messages.map((message) => (
            <div key={message.id} className={`aw__msg aw__msg--${message.author}`}>
              <p className="aw__msgtext">{message.text}</p>
              {message.lines.length > 0 && (
                <ul className="aw__lines">
                  {message.lines.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              )}
              {message.author === 'assistant' && message.offline && (
                <span className="muted aw__offline">{t('упрощённый режим: собрано правилами')}</span>
              )}
              {message.suggestion !== null && (
                <SuggestionCard id={message.suggestion} affected={message.affected} />
              )}
            </div>
          ))}
          {note && <p className="muted aw__hint">{note}</p>}
          {ask.isPending && <p className="muted aw__hint">{t('Считаю…')}</p>}
          {problem && <p className="chip chip-risk">{problem}</p>}
          <div ref={bottom} />
        </div>
      )}

      {view === 'chat' && (
        <form
          className="aw__input"
          onSubmit={(event) => {
            event.preventDefault()
            send(pending ?? undefined, input)
          }}
        >
          <input
            className="input aw__field"
            value={input}
            placeholder={pending ? pending.hint || pending.title : t('Напишите вопрос…')}
            onChange={(event) => setInput(event.target.value)}
          />
          <button className="btn btn-primary btn-sm" type="submit" disabled={ask.isPending}>
            {t('Отправить')}
          </button>
          {pending && (
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => setPending(null)}>
              {t('Отмена')}
            </button>
          )}
        </form>
      )}
    </div>
  )
}
