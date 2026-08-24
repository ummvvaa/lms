/**
 * Панели операций с моделью.
 *
 * Каждая кнопка помощника, которой нужен ввод, открывает свою панель.
 * Ответ приходит фоновой задачей — на экране виден этап, а не пустое
 * ожидание. Ничего не применяется без подтверждения человека: операции,
 * которые что-то меняют, отдают предложение (инвариант №3).
 */
import { useRef, useState } from 'react'
import {
  useParseActivity,
  useParseImage,
  useParseUniversity,
  usePrograms,
  useRunOperation,
  useStudents,
  useTaskPolling,
  useVerifyRequirements,
  type OperationInput,
  type OperationResult,
  type ParseResult,
} from '../api/hooks'
import { counted, Loading } from '../components/ui'
import SuggestionPreview from './SuggestionPreview'
import { t } from '../i18n'

/** Коды, для которых здесь есть панель. Кода без панели быть не должно. */
export const AI_PANELS = [
  'explain_list',
  'week_changes',
  'focus_today',
  'bulk_tasks',
  'prep_plan',
  'gap_to_tasks',
  'parent_letter',
  'parse_university',
  'verify_requirements',
  'parse_activity',
  'parse_certificate',
  'parse_score_screenshot',
] as const

export type AiCode = (typeof AI_PANELS)[number]

const TITLES: Record<AiCode, string> = {
  explain_list: 'Объясни этот список',
  week_changes: 'Что изменилось за неделю',
  focus_today: 'На кого смотреть сегодня',
  bulk_tasks: 'Поставить задачу выделенным',
  prep_plan: 'План подготовки к экзамену',
  gap_to_tasks: 'Пробелы портфолио в задачи',
  parent_letter: 'Черновик письма родителю',
  parse_university: 'Разобрать вуз',
  verify_requirements: 'Сверить требования с сайтом',
  parse_activity: 'Разобрать активность',
  parse_certificate: 'Прочитать грамоту',
  parse_score_screenshot: 'Прочитать скриншот с баллами',
}

const NEEDS_MANY: AiCode[] = ['explain_list', 'bulk_tasks']
const NEEDS_ONE: AiCode[] = [
  'prep_plan',
  'gap_to_tasks',
  'parent_letter',
  'parse_activity',
  'parse_certificate',
  'parse_score_screenshot',
]
const NEEDS_TEXT: AiCode[] = ['bulk_tasks', 'parse_university', 'parse_activity']
const NEEDS_IMAGE: AiCode[] = ['parse_certificate', 'parse_score_screenshot']
/** Операции над программой справочника, а не над учеником. */
const NEEDS_PROGRAM: AiCode[] = ['verify_requirements']

const PLACEHOLDER: Partial<Record<AiCode, string>> = {
  bulk_tasks: 'Что нужно сделать. Например: собрать рекомендательные письма до конца ноября',
  parse_university: 'Название или ссылка. Например: University of Toronto',
  parse_activity: 'Опишите активность словами: что было, когда, чем закончилось',
}

export default function AiPanel({ code, available }: { code: AiCode; available: boolean }) {
  const students = useStudents({ page_size: 300 })
  const programs = usePrograms()
  const run = useRunOperation()
  const verify = useVerifyRequirements()
  const parseUniversity = useParseUniversity()
  const parseActivity = useParseActivity()
  const parseImage = useParseImage()
  const fileInput = useRef<HTMLInputElement>(null)

  const [picked, setPicked] = useState<number[]>([])
  const [one, setOne] = useState<number | null>(null)
  const [program, setProgram] = useState<number | null>(null)
  const [text, setText] = useState('')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)

  const task = useTaskPolling<OperationResult & ParseResult>(taskId)
  const answer = task.data?.state === 'SUCCESS' ? task.data.result : undefined
  const rows = students.data?.results ?? []

  function start() {
    setProblem(null)
    setTaskId(null)

    if (NEEDS_MANY.includes(code) && picked.length === 0) {
      setProblem('Отметьте учеников — без них операции не с чем работать')
      return
    }
    if (NEEDS_ONE.includes(code) && one === null) {
      setProblem('Выберите ученика')
      return
    }
    if (NEEDS_TEXT.includes(code) && !text.trim()) {
      setProblem('Опишите словами, что нужно')
      return
    }
    if (NEEDS_PROGRAM.includes(code) && program === null) {
      setProblem('Выберите программу — сверять требования нужно по конкретной')
      return
    }

    const done = (response: { task: string }) => setTaskId(response.task)
    const failed = (error: unknown) => setProblem(error instanceof Error ? error.message : 'Не получилось')

    if (code === 'parse_university') {
      parseUniversity.mutate(text.trim(), { onSuccess: done, onError: failed })
      return
    }
    if (code === 'verify_requirements') {
      verify.mutate(program!, { onSuccess: done, onError: failed })
      return
    }
    if (code === 'parse_activity') {
      parseActivity.mutate({ text: text.trim(), student: one! }, { onSuccess: done, onError: failed })
      return
    }
    if (NEEDS_IMAGE.includes(code)) {
      fileInput.current?.click()
      return
    }

    const body: OperationInput = { code }
    if (NEEDS_MANY.includes(code)) body.students = picked
    if (NEEDS_ONE.includes(code)) body.student = one!
    if (NEEDS_TEXT.includes(code)) body.text = text.trim()
    run.mutate(body, { onSuccess: done, onError: failed })
  }

  return (
    <div className="card card-pad">
      <span className="eyebrow">{TITLES[code]}</span>

      {!available && (
        <p className="chip chip-warn ai__offline">
          {t(
            'Модель сейчас недоступна. Операция всё равно отработает — на правилах, формулировки будут проще.',
          )}
        </p>
      )}

      {NEEDS_MANY.includes(code) && (
        <div className="ai__pick">
          <div className="row-between">
            <span className="muted">
              {picked.length === 0
                ? 'Отметьте учеников'
                : `Отмечено: ${counted(picked.length, ['ученик', 'ученика', 'учеников'])}`}
            </span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setPicked(picked.length === rows.length ? [] : rows.map((row) => row.id))}
            >
              {picked.length === rows.length ? 'Снять все' : 'Отметить всех'}
            </button>
          </div>
          <div className="ai__list">
            {rows.map((row) => (
              <label key={row.id} className="ai__row">
                <input
                  type="checkbox"
                  checked={picked.includes(row.id)}
                  onChange={(event) =>
                    setPicked(
                      event.target.checked ? [...picked, row.id] : picked.filter((id) => id !== row.id),
                    )
                  }
                />
                {row.full_name}
                <span className="muted"> · {row.group_code ?? '—'}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      {NEEDS_ONE.includes(code) && (
        <label className="ai__field">
          {t('Ученик')}
          <select
            className="input"
            value={one ?? ''}
            aria-label={t('Ученик')}
            onChange={(event) => setOne(Number(event.target.value) || null)}
          >
            <option value="">{t('выберите')}</option>
            {rows.map((row) => (
              <option key={row.id} value={row.id}>
                {row.full_name}
              </option>
            ))}
          </select>
        </label>
      )}

      {NEEDS_PROGRAM.includes(code) && (
        <label className="ai__field">
          {t('Программа')}
          <select
            className="input"
            value={program ?? ''}
            aria-label={t('Программа')}
            onChange={(event) => setProgram(Number(event.target.value) || null)}
          >
            <option value="">{t('выберите')}</option>
            {(programs.data?.results ?? []).map((row) => (
              <option key={row.id} value={row.id}>
                {row.university_name} · {row.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {NEEDS_TEXT.includes(code) && (
        <textarea
          className="assistant__input"
          rows={code === 'bulk_tasks' ? 3 : 4}
          value={text}
          aria-label={t('Что нужно')}
          placeholder={PLACEHOLDER[code]}
          onChange={(event) => setText(event.target.value)}
        />
      )}

      <input
        ref={fileInput}
        type="file"
        accept=".jpg,.jpeg,.png"
        style={{ display: 'none' }}
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          if (!file || one === null) return
          parseImage.mutate(
            { file, student: one, kind: code === 'parse_certificate' ? 'certificate' : 'scores' },
            {
              onSuccess: (response) => setTaskId(response.task),
              onError: (error) => setProblem(error instanceof Error ? error.message : 'Файл не принят'),
            },
          )
        }}
      />

      <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
        {task.data?.state === 'PROGRESS' && (
          <span className="chip chip-mute">{task.data.progress?.stage ?? 'Обрабатываю…'}</span>
        )}
        {task.data?.state === 'FAILURE' && (
          <span className="chip chip-risk">{t('Не получилось — попробуйте ещё раз')}</span>
        )}
        {answer?.offline && <span className="chip chip-mute">{t('собрано правилами')}</span>}
        <span className="toolbar__spacer" />
        <button className="btn btn-primary btn-sm" onClick={start}>
          {NEEDS_IMAGE.includes(code) ? 'Выбрать изображение' : 'Выполнить'}
        </button>
      </div>

      {problem && <p className="chip chip-risk ai__problem">{problem}</p>}
      {task.isFetching && !answer && <Loading />}

      {answer && (
        <div className="ai__answer">
          {answer.ok === false && <p className="chip chip-warn">{answer.detail}</p>}
          {answer.text && <p className="ai__text">{answer.text}</p>}
          {(answer.lines ?? []).length > 0 && (
            <ul className="digest">
              {answer.lines.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          )}
          {answer.strength && (
            <p className="muted">
              <b>{t('Чем сильна:')}</b> {answer.strength}
            </p>
          )}
          {answer.missing && (
            <p className="muted">
              <b>{t('Чего не хватает:')}</b> {answer.missing}
            </p>
          )}
          {answer.source?.url && (
            <p className="muted ai__source">
              <b>{t('Источник:')}</b>{' '}
              <a href={answer.source.url} target="_blank" rel="noreferrer">
                {answer.source.url}
              </a>
              {answer.source.checked_at ? ` · сверено ${answer.source.checked_at}` : ''}
              {answer.source.quote ? ` · «${answer.source.quote}»` : ''}
            </p>
          )}
          {answer.detail && answer.ok !== false && <p className="chip chip-ok">{answer.detail}</p>}
        </div>
      )}

      {answer?.suggestion && <SuggestionPreview id={answer.suggestion} />}
    </div>
  )
}
