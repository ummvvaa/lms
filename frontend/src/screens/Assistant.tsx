/**
 * Помощник: именованные кнопки, а не чат.
 *
 * Каждая кнопка что-то делает. Действия, которые ещё не построены, здесь
 * не рисуются вовсе: карточка без обработчика — это обещание, которое
 * интерфейс не выполняет (см. `docs/DEFECTS.md`, B4).
 */
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useApplySuggestion,
  useCommands,
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
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import AiPanel, { AI_PANELS, type AiCode } from './AiPanels'
import SuggestionPreview from './SuggestionPreview'
import './assistant.css'
import { t } from '../i18n'
import { NativeSelect } from '../components/ui/native-select'
import { Textarea } from '../components/ui/textarea'
import { Input } from '../components/ui/input'

type Panel = 'paste_as_is' | 'parse_mock' | 'explain_match' | 'check_balance' | AiCode | null

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
            <span className="chip chip-risk">{t('не найден в базе')}</span>
          ) : (
            <div className="amb__choices">
              {item.candidates.map((candidate) => (
                <button
                  key={candidate.student}
                  className="btn btn-ghost btn-sm"
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
                </button>
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
              <span key={tier} className={`chip ${balance.data!.gaps[tier] ? 'chip-warn' : 'chip-ok'} num`}>
                {tier}: {n} из {balance.data!.target[tier]}
              </span>
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
        <button
          className="btn btn-primary btn-sm"
          disabled={student === null || program === null || explain.isPending}
          onClick={() =>
            explain.mutate({ student: student!, program: program! }, { onSuccess: (r) => setTaskId(r.task) })
          }
        >
          {t('Объяснить')}
        </button>
        {task.data?.state === 'PROGRESS' && <span className="chip chip-mute">{t('Считаю…')}</span>}
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
  const commands = useCommands()
  const quick = useAssistantQuick(true)
  const llm = useLLMStatus()
  const paste = usePaste()
  const upload = useUploadCommand()
  const fileInput = useRef<HTMLInputElement>(null)

  const [panel, setPanel] = useState<Panel>('paste_as_is')
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
    const response = await paste.mutateAsync({ text, command })
    setTaskId(response.task)
  }

  /** Что делает каждая кнопка. Кода без обработчика здесь быть не должно. */
  function run(code: string) {
    setNote(null)
    if (code === 'digest') {
      navigate('/digest')
      return
    }
    if (code === 'upload_file') {
      fileInput.current?.click()
      return
    }
    setPanel(code as Panel)
  }

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
        <p className="chip chip-warn assistant__state">{llm.data.detail}</p>
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
          <button className="btn btn-ghost btn-sm" onClick={() => setShowRest((v) => !v)}>
            {showRest ? t('Скрыть остальные действия') : `${t('Ещё действия')} · ${rest.length}`}
          </button>
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
          upload.mutate(file, {
            onSuccess: (r) => {
              setTaskId(r.task)
              setNote(`Разбираю «${file.name}»`)
            },
            onError: (error) => setNote(error instanceof Error ? error.message : 'Файл не принят'),
          })
          e.target.value = ''
        }}
      />

      {note && <p className="chip chip-mute">{note}</p>}

      {isPastePanel && (
        <div className="card card-pad">
          <span className="eyebrow">{panel === 'parse_mock' ? 'Разобрать мок' : 'Вставить как есть'}</span>
          <Textarea
            className="assistant__input"
            rows={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={PASTE_PLACEHOLDER[panel] ?? PASTE_PLACEHOLDER.paste_as_is}
          />
          <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
            {task.data?.state === 'PROGRESS' && (
              <span className="chip chip-mute">{task.data.progress?.stage ?? 'Обрабатываю…'}</span>
            )}
            {task.data?.state === 'FAILURE' && (
              <span className="chip chip-risk">{t('Разбор не удался')}</span>
            )}
            {result && (
              <span className="chip chip-ok num">
                Разобрано строк: {result.rows}
                {result.ambiguities.length > 0 && `, неоднозначных: ${result.ambiguities.length}`}
              </span>
            )}
            <span className="toolbar__spacer" />
            <button
              className="btn btn-primary btn-sm"
              onClick={() => void send(panel)}
              disabled={paste.isPending || text.trim() === ''}
            >
              {t('Разобрать')}
            </button>
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
