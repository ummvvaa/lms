/**
 * Помощник в углу: круглая кнопка справа внизу и панель диалога.
 *
 * Быстрые кнопки на правилах работают без ключа модели; свободный ввод
 * без ключа получает честный отказ. Любое изменение данных приходит
 * предложением — карточка предпросмотра показывается прямо в панели,
 * применяет человек (инвариант №3).
 */
import { useEffect, useRef, useState } from 'react'
import { Chip, counted, EmptyNote } from './ui'
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
import './assistant-widget.css'
import { Input } from './ui/input'
import { Button } from './ui/button'
import Icon from '../layout/icons'
import { Row, Rows } from './patterns'

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
        <Chip tone="mute" className="badge--line">
          {data.status_title}
        </Chip>
      ) : (
        <div className="aw__cardactions">
          <Button
            size="sm"
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
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={reject.isPending}
            onClick={() => reject.mutate(id, { onSuccess: () => setNote(t('Отклонено')) })}
          >
            {t('Отклонить')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigate(`/suggestions/${id}`)}>
            {t('Выбрать строки')}
          </Button>
        </div>
      )}
      {note && (
        <Chip tone="ok" className="badge--line">
          {note}
        </Chip>
      )}
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
      <Input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="aw__file"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) parse.mutate({ file, student: studentId, kind }, { onSuccess: (r) => setTaskId(r.task) })
        }}
      />
      <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}>
        {t('Выбрать изображение')}
      </Button>
      {taskId && !result && <p className="muted aw__hint">{t('Обрабатываю…')}</p>}
      {result && !result.suggestion && <p className="muted aw__hint">{result.detail}</p>}
      {result?.suggestion && <SuggestionCard id={result.suggestion} affected={0} />}
    </div>
  )
}

export default function AssistantWidget({
  open,
  onOpenChange: setOpen,
  fab = true,
}: {
  /** открыт ли — состояние у каркаса: на телефоне его открывает кнопка шапки (фаза 76) */
  open: boolean
  onOpenChange: (open: boolean) => void
  /** рисовать плавающую кнопку; на телефоне — нет */
  fab?: boolean
}) {
  const { me } = useAuth()
  const location = useLocation()
  const { students } = useAssistantScreen()
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
    if (!fab) return null
    return (
      <Button size="icon-lg" className="aw__fab" aria-label={t('Открыть помощника')} onClick={() => setOpen(true)}>
        <img src={LOGO.assistant} alt="" />
      </Button>
    )
  }

  return (
    <div className={`aw${full ? ' aw--full' : ''}`}>
      <div className="aw__head">
        <img className="aw__logo" src={LOGO.assistant} alt="" />
        <b className="aw__title">{t('Помощник')}</b>
        <div className="aw__tools">
          <Button variant="ghost" size="sm" className="aw__tool" onClick={newDialog}>
            {t('Новый')}
          </Button>
          <Button variant="ghost" size="sm" className="aw__tool" aria-pressed={view === 'history'} onClick={() => setView(view === 'history' ? 'chat' : 'history')}>
            {t('История')}
          </Button>
          <Button variant="ghost" size="sm" className="aw__tool" onClick={() => setFull((v) => !v)}>
            {full ? t('Обычный размер') : t('Развернуть')}
          </Button>
          <Button variant="ghost" size="icon-sm" className="aw__tool" aria-label={t('Свернуть')} onClick={() => setOpen(false)}>
            <Icon name="close" size={14} />
          </Button>
        </div>
      </div>

      {view === 'history' ? (
        <div className="aw__body">
          {(threads.data ?? []).length === 0 && <EmptyNote what="диалогов пока нет" />}
          <Rows>
            {(threads.data ?? []).map((row) => (
              <Row
                key={row.id}
                icon="news"
                title={row.title || t('Диалог')}
                note={new Date(row.updated_at).toLocaleDateString('ru')}
                onOpen={() => {
                  setThreadId(row.id)
                  setView('chat')
                }}
                openLabel={t('Открыть')}
              />
            ))}
          </Rows>
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
              <Button key={button.code} variant="outline" size="sm" className="aw__quickbtn" title={button.hint} disabled={ask.isPending} onClick={() => press(button)}>
                {button.title}
              </Button>
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
          {problem && (
            <Chip tone="risk" className="badge--line">
              {problem}
            </Chip>
          )}
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
          <Input
            className="aw__field"
            value={input}
            placeholder={pending ? pending.hint || pending.title : t('Напишите вопрос…')}
            onChange={(event) => setInput(event.target.value)}
          />
          <Button size="sm" type="submit" disabled={ask.isPending}>
            {t('Отправить')}
          </Button>
          {pending && (
            <Button variant="outline" size="sm" type="button" onClick={() => setPending(null)}>
              {t('Отмена')}
            </Button>
          )}
        </form>
      )}
    </div>
  )
}
