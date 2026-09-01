/**
 * Профтест (фаза 45): анкета плюс разбор, без адаптивного теста.
 *
 * Владелец продукта согласовал упрощённый вариант: у образца это отдельный
 * большой продукт, а половина одиннадцатиклассников не знает, куда идти,
 * и простой вариант уже помогает.
 *
 * Без ключа модели раздел не притворяется работающим: он говорит, что
 * недоступен, и объясняет почему. Разбор анкеты правилами дал бы
 * бессмысленный результат.
 *
 * Все названные программы — из справочника школы (инвариант №10):
 * сервер принимает от модели только их номера.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareer, useCareerAgree, useCareerRun, type CareerRunRow } from '../api/hooks'
import Empty from '../components/Empty'
import { Dimmed } from '../components/patterns'
import { DataCard, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import './career.css'
import { t } from '../i18n'

type Mode = 'test' | 'history'

/** Свой вариант хранится в черновике отдельным ключом. */
const OWN = (code: string) => `${code}__own`

/**
 * Ответ строкой: выбранные варианты через запятую плюс свой, если есть.
 *
 * Модель получает ту же строку, что раньше приходила из текстового поля,
 * поэтому разбор не переучивается: меняется способ ввода, а не формат.
 */
function answerOf(picked: string[], own: string): string {
  return [...picked, own.trim()].filter(Boolean).join(', ')
}

function Directions({ run }: { run: CareerRunRow }) {
  const agree = useCareerAgree()

  return (
    <div className="grid grid--two">
      {run.directions.map((direction) => (
        <DataCard
          key={direction.id}
          title={direction.title}
          note={direction.subjects ? `${t('Предметы:')} ${direction.subjects}` : undefined}
          accent="indigo"
        >
          <p className="career__why">{direction.reasoning}</p>
          {direction.exams && (
            <p className="muted career__line">
              <b>{t('Экзамены.')}</b> {direction.exams}
            </p>
          )}
          {direction.programs.length > 0 ? (
            <ul className="rows__list career__programs">
              {direction.programs.map((program) => (
                <li key={program.id}>
                  <b>{program.name}</b> <span className="muted">· {program.university}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted career__line">
              {t('В справочнике школы программ под это направление пока нет.')}
            </p>
          )}
          <div className="career__actions">
            {direction.agreed ? (
              <Badge variant="ok">{t('отправлено директору')}</Badge>
            ) : (
              <Button
                size="sm"
                disabled={agree.isPending}
                onClick={() =>
                  agree.mutate(direction.id, {
                    onSuccess: (result) =>
                      result.ok ? toast.success(result.detail) : toast.error(result.detail),
                    onError: (error) => toast.error(error.message),
                  })
                }
              >
                {t('Мне подходит')}
              </Button>
            )}
          </div>
        </DataCard>
      ))}
    </div>
  )
}

export default function Career() {
  const [mode, setMode] = useState<Mode>('test')
  // выбранные варианты по вопросу и свой вариант рядом
  const [picked, setPicked] = useState<Record<string, string[]>>({})
  const [draft, setDraft] = useState<Record<string, string>>({})
  const state = useCareer()
  const run = useCareerRun()

  if (state.isLoading) return <Loading kind="cards" />
  if (state.error) return <ErrorNote error={state.error} />

  const data = state.data
  const questions = data?.questions ?? []
  const runs = data?.runs ?? []
  const last = run.data ?? runs[0]
  const valueOf = (code: string) => answerOf(picked[code] ?? [], draft[OWN(code)] ?? draft[code] ?? '')
  const answered = questions.filter((question) => valueOf(question.code) !== '').length

  /** Нажатие по варианту: выбрать или снять — тем же нажатием. */
  const toggle = (code: string, option: string) =>
    setPicked((prev) => {
      const list = prev[code] ?? []
      return { ...prev, [code]: list.includes(option) ? list.filter((o) => o !== option) : [...list, option] }
    })

  return (
    <div>
      <ScreenHead
        title={t('Профтест')}
        subtitle={t(
          'Анкета из нескольких вопросов и разбор: какие направления вам подходят и что под них нужно.',
        )}
      />

      <ScreenTabs
        value={mode}
        onChange={setMode}
        items={[
          { value: 'test', label: t('Анкета') },
          { value: 'history', label: `${t('Прошлые разборы')} · ${runs.length}` },
        ]}
      />

      {/* Без ключа модели раздел не притворяется работающим и не прячется:
          анкета видна приглушённой, а сверху сказано, почему её сейчас
          не разобрать (приём заблокированного раздела, фаза 48) */}
      {!data?.available && mode === 'test' && (
        <Dimmed
          tone="indigo"
          title={t('Профтест сейчас недоступен')}
          what={`${data?.detail ?? ''} ${t('Разбор анкеты правилами дал бы бессмысленный результат, поэтому раздел ждёт подключения модели.')}`}
        >
          <div className="career__preview">
            {questions.map((question, index) => (
              <div key={question.id} className="card card-pad career__q">
                <div className="career__qhead">
                  <span className="num career__qnum">{index + 1}</span>
                  <div className="career__qtext">
                    <span className="career__label">{question.text}</span>
                  </div>
                </div>
                <div className="career__options">
                  {question.options_list.slice(0, 6).map((option) => (
                    <span key={option} className="career__option">
                      {option}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Dimmed>
      )}

      {mode === 'test' && data?.available && (
        <>
          {questions.length === 0 && (
            <Empty
              icon="bulb"
              title={t('Анкета пока пуста')}
              what={t('Вопросы профтеста заводит директор школы — как появятся, анкета откроется.')}
              hint={t('Вопросы живут справочником, а не в коде: школа меняет формулировки без выката.')}
            />
          )}

          {/* Вопрос отвечается нажатиями: готовые варианты чипами, можно
              выбрать несколько, снимается повторным нажатием. Поле «свой
              вариант» рядом — для того, чего в списке нет. Варианты ведёт
              директор школы у самого вопроса, в коде их нет */}
          {questions.map((question, index) => {
            const options = question.options_list
            const chosen = picked[question.code] ?? []
            return (
              <div key={question.id} className="card card-pad career__q">
                <div className="career__qhead">
                  <span className="num career__qnum">{index + 1}</span>
                  <div className="career__qtext">
                    <label className="career__label" htmlFor={`q-${question.code}`}>
                      {question.text}
                    </label>
                    {question.hint && <p className="muted career__line">{question.hint}</p>}
                  </div>
                  {valueOf(question.code) !== '' && <Badge variant="ok">{t('отвечено')}</Badge>}
                </div>

                {options.length > 0 && (
                  <div className="career__options" role="group" aria-label={question.text}>
                    {options.map((option) => (
                      <button
                        key={option}
                        type="button"
                        aria-pressed={chosen.includes(option)}
                        className={`career__option${chosen.includes(option) ? ' career__option--on' : ''}`}
                        onClick={() => toggle(question.code, option)}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                )}

                <Input
                  id={`q-${question.code}`}
                  className="career__own"
                  placeholder={options.length > 0 ? t('Свой вариант') : t('Ваш ответ')}
                  aria-label={`${question.text} — ${t('свой вариант')}`}
                  value={draft[OWN(question.code)] ?? ''}
                  onChange={(event) =>
                    setDraft((prev) => ({ ...prev, [OWN(question.code)]: event.target.value }))
                  }
                />
              </div>
            )
          })}

          {questions.length > 0 && (
            <div className="toolbar">
              {/* Кнопка не выключается на пустой анкете: выключенная
                  выглядит сломанной. Пустой ответ она объясняет словами */}
              <Button
                disabled={run.isPending}
                onClick={() => {
                  if (answered === 0) {
                    toast.error(t('Ответьте хотя бы на один вопрос — тогда будет что разбирать'))
                    return
                  }
                  run.mutate(
                    questions.map((question) => ({
                      question: question.code,
                      value: valueOf(question.code),
                    })),
                    { onError: (error) => toast.error(error.message) },
                  )
                }}
              >
                {run.isPending ? t('Разбираю…') : t('Получить разбор')}
              </Button>
              <span className="muted career__line">
                {t('Отвечено:')} {answered} {t('из')} {questions.length}
              </span>
            </div>
          )}

          {run.error && <ErrorNote error={run.error} />}

          {last && last.directions.length > 0 && (
            <>
              <span className="eyebrow">{t('Что получилось')}</span>
              {last.summary && <p className="career__summary">{last.summary}</p>}
              <Directions run={last} />
            </>
          )}
        </>
      )}

      {mode === 'history' && (
        <>
          {runs.length === 0 && (
            <Empty
              icon="clock"
              title={t('Разборов пока нет')}
              what={t('Пройдите анкету — разбор сохранится, и его можно будет сравнить со следующим.')}
              hint={t(
                'Через полгода вы ответите иначе, и сравнить два разбора полезнее, чем переписать один.',
              )}
              action={t('К анкете')}
              onAction={() => setMode('test')}
            />
          )}
          {runs.map((item) => (
            <DataCard
              key={item.id}
              title={new Date(item.created_at).toLocaleDateString('ru')}
              note={item.summary || item.error || undefined}
              count={item.directions.length}
            >
              <ul className="rows__list">
                {item.directions.map((direction) => (
                  <li key={direction.id}>
                    <b>{direction.title}</b>
                    {direction.agreed && <span className="muted"> · {t('отправлено директору')}</span>}
                  </li>
                ))}
              </ul>
            </DataCard>
          ))}
        </>
      )}
    </div>
  )
}
