/**
 * Помощник: именованные кнопки, а не чат.
 *
 * Каждая кнопка что-то делает. Действия, которые ещё не построены, здесь
 * не рисуются вовсе: карточка без обработчика — это обещание, которое
 * интерфейс не выполняет (см. `docs/DEFECTS.md`, B4).
 */
import { useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  useApplySuggestion,
  useCommands,
  useDomainMeta,
  useExplainMatch,
  useListBalance,
  usePaste,
  usePrograms,
  useStudents,
  useTaskPolling,
  useUploadCommand,
  type Ambiguity,
  type PasteResult,
} from '../api/hooks'
import { useAssistantQuick, useLLMStatus } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import AiPanel, { AI_PANELS, type AiCode } from './AiPanels'
import SuggestionPreview from './SuggestionPreview'
import './assistant.css'
import { t } from '../i18n'
import { NativeSelect } from '../components/ui/native-select'
import { Textarea } from '../components/ui/textarea'
import { Input } from '../components/ui/input'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'

type Panel = 'paste_as_is' | 'parse_mock' | 'upload_file' | 'explain_match' | 'check_balance' | AiCode | null

/** Панели, которые можно открыть адресом: `/assistant?panel=paste_as_is` — так ведёт подсказка с экранов директора. */
const LINKABLE: Panel[] = ['paste_as_is', 'parse_mock', 'upload_file']

/** Панель с моделью? Тогда её рисует `AiPanel`. */
function isAiPanel(code: Panel): code is AiCode {
  return AI_PANELS.includes(code as AiCode)
}

const PASTE_PLACEHOLDER: Record<string, string> = {
  paste_as_is: 'Вставьте кусок переписки, например:\nСериков Дамир — 1320\nТлеубаева Жанна — 1450',
  parse_mock: 'Баллы мока строками, например:\nСериков Дамир — 6.5\nТлеубаева Жанна — 7.0',
}

function Ambiguities({
  items,
  suggestionId,
  onResolved,
}: {
  items: Ambiguity[]
  suggestionId: number
  onResolved: () => void
}) {
  const { resolve } = useApplySuggestion()
  if (items.length === 0) return null

  return (
    <div className="card card-pad amb">
      <span className="eyebrow">{t('Нужен ваш выбор')}</span>
      <p className="muted amb__note">
        {t('Эти строки не удалось сопоставить однозначно. Система не угадывает — выберите вручную.')}
      </p>
      {items.map((item) => (
        <div key={item.query} className="amb__row">
          <div className="amb__query">
            <b>{item.query}</b>
            {item.raw && <span className="muted amb__raw">{item.raw}</span>}
          </div>
          {item.is_missing ? (
            <Badge variant="risk">{t('не найден в базе')}</Badge>
          ) : (
            <div className="amb__choices">
              {item.candidates.map((candidate) => (
                <Button
                  key={candidate.student}
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    const [field, value] = Object.entries(item.values ?? {})[0] ?? []
                    if (!field) return
                    resolve.mutate(
                      {
                        id: suggestionId,
                        query: item.query,
                        student: candidate.student,
                        model:
                          field === 'sat_current' || field === 'ielts_current'
                            ? 'students.ExamProfile'
                            : 'students.BehaviorProfile',
                        field,
                        value,
                        source_quote: item.raw ?? '',
                      },
                      { onSuccess: onResolved },
                    )
                  }}
                >
                  {candidate.full_name}
                  <span className="muted amb__conf">
                    {candidate.group ?? '—'} · {Math.round(candidate.confidence * 100)}%
                  </span>
                </Button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

/** Выбор ученика — общий для действий, работающих «над выделенным». */
function StudentPicker({ value, onChange }: { value: number | null; onChange: (id: number | null) => void }) {
  const [search, setSearch] = useState('')
  const students = useStudents({ search, page_size: 50 })
  return (
    <div className="toolbar" style={{ marginBottom: 0 }}>
      <Input placeholder={t('Поиск ученика')} value={search} onChange={(e) => setSearch(e.target.value)} />
      <NativeSelect
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">{t('— выберите ученика —')}</option>
        {(students.data?.results ?? []).map((row) => (
          <option key={row.id} value={row.id}>
            {row.full_name}
          </option>
        ))}
      </NativeSelect>
    </div>
  )
}

/** «Проверить баланс списка»: сколько reach / target / safety и чего добрать. */
function BalancePanel() {
  const [student, setStudent] = useState<number | null>(null)
  const balance = useListBalance(student)

  return (
    <div className="card card-pad">
      <span className="eyebrow">{t('Баланс списка')}</span>
      <StudentPicker value={student} onChange={setStudent} />
      {balance.isLoading && student !== null && <Loading />}
      {balance.data && (
        <div style={{ marginTop: 14 }}>
          <p style={{ margin: 0 }}>{balance.data.advice}</p>
          <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
            {Object.entries(balance.data.counts).map(([tier, n]) => (
              <Badge key={tier} variant={balance.data!.gaps[tier] ? 'warn' : 'ok'} className="num">
                {tier}: {n} из {balance.data!.target[tier]}
              </Badge>
            ))}
          </div>
          <ul className="bullets">
            {balance.data.programs.map((row) => (
              <li key={row.program}>
                {row.university_name} — {row.program_name} <span className="muted">({row.tier})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** «Объясни соответствие»: ученик × программа → чего не хватает. */
function ExplainPanel() {
  const [student, setStudent] = useState<number | null>(null)
  const [program, setProgram] = useState<number | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)
  const programs = usePrograms()
  const explain = useExplainMatch()
  const task = useTaskPolling<Record<string, unknown>>(taskId)

  const result = task.data?.state === 'SUCCESS' ? task.data.result : undefined

  return (
    <div className="card card-pad">
      <span className="eyebrow">{t('Объяснение соответствия')}</span>
      <StudentPicker value={student} onChange={setStudent} />
      <div className="toolbar" style={{ marginTop: 10 }}>
        <NativeSelect
          value={program ?? ''}
          onChange={(e) => setProgram(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">{t('— выберите программу —')}</option>
          {(programs.data?.results ?? []).map((row) => (
            <option key={row.id} value={row.id}>
              {row.university_name} — {row.name}
            </option>
          ))}
        </NativeSelect>
        <Button
          size="sm"
          disabled={student === null || program === null || explain.isPending}
          onClick={() =>
            explain.mutate({ student: student!, program: program! }, { onSuccess: (r) => setTaskId(r.task) })
          }
        >
          {t('Объяснить')}
        </Button>
        {task.data?.state === 'PROGRESS' && <Badge variant="mute">{t('Считаю…')}</Badge>}
      </div>
      {(programs.data?.results ?? []).length === 0 && (
        <p className="muted">{t('В справочнике пока нет программ — объяснять нечего.')}</p>
      )}
      {result && <pre className="assistant__result">{JSON.stringify(result, null, 2)}</pre>}
    </div>
  )
}

export default function Assistant() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { me } = useAuth()
  const commands = useCommands()
  const quick = useAssistantQuick(true)
  const llm = useLLMStatus()
  const paste = usePaste()
  const upload = useUploadCommand()
  const fileInput = useRef<HTMLInputElement>(null)
  // администратор вставляет текст и грузит файл за выбранный домен (фаза 35):
  // у директора домен свой, выбирать нечего
  const isAdmin = me?.role === 'admin'
  const meta = useDomainMeta()
  const [domain, setDomain] = useState('')

  const [panel, setPanel] = useState<Panel>(() => {
    const wanted = params.get('panel') as Panel
    return LINKABLE.includes(wanted) ? wanted : 'paste_as_is'
  })
  const [text, setText] = useState('')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [suggestionId, setSuggestionId] = useState<number | null>(null)
  const [note, setNote] = useState<string | null>(null)
  // остальные действия свёрнуты: на экране четыре согласованные кнопки,
  // длинный список карточек человек всё равно не читает
  const [showRest, setShowRest] = useState(false)
  const task = useTaskPolling<PasteResult>(taskId)

  const result = task.data?.state === 'SUCCESS' ? task.data.result : undefined
  const activeSuggestion = suggestionId ?? result?.suggestion ?? null

  async function send(command: string) {
    setSuggestionId(null)
    setNote(null)
    if (isAdmin && !domain) {
      setNote(t('Сначала выберите домен — чьи данные вы вставляете'))
      return
    }
    const response = await paste.mutateAsync({ text, command, domain: isAdmin ? domain : undefined })
    setTaskId(response.task)
  }

  /** Что делает каждая кнопка. Кода без обработчика здесь быть не должно. */
  function run(code: string) {
    setNote(null)
    if (code === 'digest') {
      navigate('/digest')
      return
    }
    setPanel(code as Panel)
  }

  /** Выбор домена — только у администратора, перед вставкой и перед файлом. */
  const domainPicker = isAdmin && (
    <label className="imp__domain" style={{ marginBottom: 12 }}>
      <span className="eyebrow">{t('Домен')}</span>
      <NativeSelect aria-label={t('Домен')} value={domain} onChange={(e) => setDomain(e.target.value)}>
        <option value="">{t('— выберите домен —')}</option>
        {(meta.data?.domains ?? []).map((row) => (
          <option key={row.code} value={row.code}>
            {row.title} · {row.owner_name}
          </option>
        ))}
      </NativeSelect>
    </label>
  )

  if (commands.isLoading) return <Loading />
  if (commands.error) return <ErrorNote error={commands.error} />

  const isPastePanel = panel === 'paste_as_is' || panel === 'parse_mock'
  // главные — те же четыре кнопки, что у помощника в углу; остальное
  // остаётся доступным, но не занимает экран
  const main = (quick.data?.buttons ?? []).map((button) => button.code)
  const rest = (commands.data?.commands ?? []).filter((command) => !main.includes(command.code))

  return (
    <div>
      <ScreenHead
        title={t('Помощник')}
        subtitle={t('Именованные действия. Ничего не применяется без вашего подтверждения.')}
      />

      {llm.data && !llm.data.available && (
        <Badge variant="warn" className="badge--line assistant__state">
          {llm.data.detail}
        </Badge>
      )}

      {/* четыре кнопки роли — те же, что в помощнике в углу: состав
          согласован, и он один на оба места */}
      <div className="assistant__buttons">
        {(commands.data?.commands ?? [])
          .filter((command) => main.includes(command.code))
          .map((command) => (
            <button
              key={command.code}
              className={`card card-pad assistant__cmd${panel === command.code ? ' assistant__cmd--active' : ''}`}
              onClick={() => run(command.code)}
            >
              <b>{command.title}</b>
              <p className="muted assistant__hint">{command.hint}</p>
            </button>
          ))}
      </div>

      {rest.length > 0 && (
        <div className="assistant__more">
          <Button variant="outline" size="sm" onClick={() => setShowRest((v) => !v)}>
            {showRest ? t('Скрыть остальные действия') : `${t('Ещё действия')} · ${rest.length}`}
          </Button>
        </div>
      )}

      {showRest && (
        <div className="assistant__buttons">
          {rest.map((command) => (
            <button
              key={command.code}
              className={`card card-pad assistant__cmd${panel === command.code ? ' assistant__cmd--active' : ''}`}
              onClick={() => run(command.code)}
            >
              <b>{command.title}</b>
              <p className="muted assistant__hint">{command.hint}</p>
            </button>
          ))}
        </div>
      )}

      <input
        ref={fileInput}
        type="file"
        accept=".csv,.xlsx,.xlsm,.txt"
        style={{ display: 'none' }}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (!file) return
          setSuggestionId(null)
          upload.mutate(
            { file, domain },
            {
              onSuccess: (r) => {
                setTaskId(r.task)
                setNote(`Разбираю «${file.name}»`)
              },
              onError: (error) => setNote(error instanceof Error ? error.message : 'Файл не принят'),
            },
          )
          e.target.value = ''
        }}
      />

      {panel === 'upload_file' && (
        <div className="card card-pad">
          <span className="eyebrow">{t('Загрузить файл')}</span>
          <p className="muted assistant__hint">
            {t(
              'XLSX, CSV или текст: разбор тот же, что у вставки, — предложение, которое вы примете или отклоните.',
            )}
          </p>
          {domainPicker}
          <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
            {task.data?.state === 'PROGRESS' && (
              <Badge variant="mute">{task.data.progress?.stage ?? 'Обрабатываю…'}</Badge>
            )}
            {task.data?.state === 'FAILURE' && <Badge variant="risk">{t('Разбор не удался')}</Badge>}
            {result && (
              <Badge variant="ok" className="num">
                Разобрано строк: {result.rows}
              </Badge>
            )}
            <span className="toolbar__spacer" />
            <Button
              size="sm"
              disabled={upload.isPending || (isAdmin && !domain)}
              onClick={() => fileInput.current?.click()}
            >
              {t('Выбрать файл')}
            </Button>
          </div>
        </div>
      )}

      {note && (
        <Badge variant="mute" className="badge--line">
          {note}
        </Badge>
      )}

      {isPastePanel && (
        <div className="card card-pad">
          <span className="eyebrow">{panel === 'parse_mock' ? 'Разобрать мок' : 'Вставить как есть'}</span>
          {domainPicker}
          <Textarea
            className="assistant__input"
            rows={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={PASTE_PLACEHOLDER[panel] ?? PASTE_PLACEHOLDER.paste_as_is}
          />
          <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
            {task.data?.state === 'PROGRESS' && (
              <Badge variant="mute">{task.data.progress?.stage ?? 'Обрабатываю…'}</Badge>
            )}
            {task.data?.state === 'FAILURE' && <Badge variant="risk">{t('Разбор не удался')}</Badge>}
            {result && (
              <Badge variant="ok" className="num">
                Разобрано строк: {result.rows}
                {result.ambiguities.length > 0 && `, неоднозначных: ${result.ambiguities.length}`}
              </Badge>
            )}
            <span className="toolbar__spacer" />
            <Button
              size="sm"
              onClick={() => void send(panel)}
              disabled={paste.isPending || text.trim() === ''}
            >
              {t('Разобрать')}
            </Button>
          </div>
        </div>
      )}

      {panel === 'check_balance' && <BalancePanel />}
      {panel === 'explain_match' && <ExplainPanel />}
      {isAiPanel(panel) && <AiPanel code={panel} available={llm.data?.available ?? false} />}

      {result && activeSuggestion && (
        <>
          <Ambiguities
            items={result.ambiguities}
            suggestionId={activeSuggestion}
            onResolved={() => setSuggestionId(activeSuggestion)}
          />
          <SuggestionPreview id={activeSuggestion} />
        </>
      )}
    </div>
  )
}
