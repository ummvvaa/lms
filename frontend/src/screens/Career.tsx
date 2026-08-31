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
import { DataCard, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { NativeSelect } from '../components/ui/native-select'
import { Textarea } from '../components/ui/textarea'
import './career.css'
import { t } from '../i18n'

type Mode = 'test' | 'history'

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
  const [draft, setDraft] = useState<Record<string, string>>({})
  const state = useCareer()
  const run = useCareerRun()

  if (state.isLoading) return <Loading kind="cards" />
  if (state.error) return <ErrorNote error={state.error} />

  const data = state.data
  const questions = data?.questions ?? []
  const runs = data?.runs ?? []
  const last = run.data ?? runs[0]
  const answered = questions.filter((question) => (draft[question.code] ?? '').trim() !== '').length

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

      {!data?.available && (
        <div className="card card-pad career__closed card--accent card--warn">
          <b>{t('Профтест сейчас недоступен')}</b>
          <p className="muted career__line">{data?.detail}</p>
          <p className="muted career__line">
            {t(
              'Разбор анкеты правилами дал бы бессмысленный результат, поэтому раздел ждёт подключения модели.',
            )}
          </p>
        </div>
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

          {questions.map((question) => (
            <div key={question.id} className="card card-pad career__q">
              <label className="career__label" htmlFor={`q-${question.code}`}>
                {question.text}
              </label>
              {question.hint && <p className="muted career__line">{question.hint}</p>}
              {question.kind === 'choice' ? (
                <NativeSelect
                  id={`q-${question.code}`}
                  value={draft[question.code] ?? ''}
                  onChange={(event) => setDraft((prev) => ({ ...prev, [question.code]: event.target.value }))}
                >
                  <option value="">{t('— выберите —')}</option>
                  {question.options_list.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </NativeSelect>
              ) : question.text.length > 60 ? (
                <Textarea
                  id={`q-${question.code}`}
                  rows={2}
                  value={draft[question.code] ?? ''}
                  onChange={(event) => setDraft((prev) => ({ ...prev, [question.code]: event.target.value }))}
                />
              ) : (
                <Input
                  id={`q-${question.code}`}
                  value={draft[question.code] ?? ''}
                  onChange={(event) => setDraft((prev) => ({ ...prev, [question.code]: event.target.value }))}
                />
              )}
            </div>
          ))}

          {questions.length > 0 && (
            <div className="toolbar">
              <Button
                disabled={run.isPending || answered === 0}
                onClick={() =>
                  run.mutate(
                    questions.map((question) => ({
                      question: question.code,
                      value: draft[question.code] ?? '',
                    })),
                    { onError: (error) => toast.error(error.message) },
                  )
                }
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
