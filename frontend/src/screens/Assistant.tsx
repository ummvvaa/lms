/**
 * Помощник: именованные кнопки, а не чат.
 * Вставка текста → фоновый разбор → предпросмотр с разрешением неоднозначностей.
 */
import { useState } from 'react'
import {
  useApplySuggestion,
  useCommands,
  usePaste,
  useTaskPolling,
  type Ambiguity,
  type PasteResult,
} from '../api/hooks'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import SuggestionPreview from './SuggestionPreview'
import './assistant.css'

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
      <span className="eyebrow">⚠ Нужен ваш выбор</span>
      <p className="muted amb__note">
        Эти строки не удалось сопоставить однозначно. Система не угадывает — выберите вручную.
      </p>
      {items.map((item) => (
        <div key={item.query} className="amb__row">
          <div className="amb__query">
            <b>{item.query}</b>
            {item.raw && <span className="muted amb__raw">{item.raw}</span>}
          </div>
          {item.is_missing ? (
            <span className="chip chip-risk">не найден в базе</span>
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

export default function Assistant() {
  const commands = useCommands()
  const paste = usePaste()
  const [text, setText] = useState('')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [suggestionId, setSuggestionId] = useState<number | null>(null)
  const task = useTaskPolling<PasteResult>(taskId)

  const result = task.data?.state === 'SUCCESS' ? task.data.result : undefined
  const activeSuggestion = suggestionId ?? result?.suggestion ?? null

  async function send() {
    setSuggestionId(null)
    const response = await paste.mutateAsync(text)
    setTaskId(response.task)
  }

  if (commands.isLoading) return <Loading />
  if (commands.error) return <ErrorNote error={commands.error} />

  return (
    <div>
      <ScreenHead
        emoji="✦"
        title="Помощник"
        subtitle="Именованные действия. Ничего не применяется без вашего подтверждения."
      />

      <div className="assistant__buttons">
        {commands.data?.commands.map((command) => (
          <div key={command.code} className="card card-pad assistant__cmd">
            <b>{command.title}</b>
            <p className="muted assistant__hint">{command.hint}</p>
          </div>
        ))}
      </div>

      <div className="card card-pad">
        <span className="eyebrow">📋 Вставить как есть</span>
        <textarea
          className="assistant__input"
          rows={8}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={'Вставьте кусок переписки, например:\nСериков Дамир — 1320\nТлеубаева Жанна — 1450'}
        />
        <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
          {task.data?.state === 'PROGRESS' && (
            <span className="chip chip-mute">{task.data.progress?.stage ?? 'Обрабатываю…'}</span>
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
            onClick={() => void send()}
            disabled={paste.isPending || text.trim() === ''}
          >
            Разобрать
          </button>
        </div>
      </div>

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
