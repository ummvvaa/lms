/**
 * Профтест: анкета в левой колонке, справа «что вы получите» и прошлые разборы.
 *
 * Владелец продукта согласовал упрощённый вариант: у образца это отдельный
 * большой продукт, а половина одиннадцатиклассников не знает, куда идти,
 * и простой вариант уже помогает. Без ключа модели раздел не притворяется
 * работающим: он говорит, что недоступен, и объясняет почему.
 *
 * Все названные программы — из справочника школы (инвариант №10):
 * сервер принимает от модели только их номера.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareer, useCareerAgree, useCareerRun, type CareerRunRow } from '../api/hooks'
import Field from '../components/Field'
import Progress from '../components/Progress'
import { Row, Rows, Segmented } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { NoteCard } from './academics/shared'
import './career.css'

type Mode = 'test' | 'history'

/** Свой вариант хранится в черновике отдельным ключом. */
const OWN = (code: string) => `${code}__own`

function answerOf(picked: string[], own: string): string {
  return [...picked, own.trim()].filter(Boolean).join(', ')
}

function Directions({ run }: { run: CareerRunRow }) {
  const agree = useCareerAgree()
  return (
    <>
      {run.directions.map((direction) => (
        <DataCard
          key={direction.id}
          title={direction.title}
          note={direction.subjects ? `${t('Предметы:')} ${direction.subjects}` : undefined}
          right={
            direction.agreed ? (
              <Chip tone="good" size="sm">{t('отправлено директору')}</Chip>
            ) : (
              <Button variant="secondary" size="sm" disabled={agree.isPending} onClick={() => agree.mutate(direction.id, { onSuccess: (result) => (result.ok ? toast.success(result.detail) : toast.error(result.detail)), onError: (error) => toast.error(error.message) })}>
                {t('Мне подходит')}
              </Button>
            )
          }
        >
          <p className="acad__note">{direction.reasoning}</p>
          {direction.exams && (
            <p className="t-note">
              <b>{t('Экзамены.')}</b> {direction.exams}
            </p>
          )}
          <Rows>
            {direction.programs.map((program) => (
              <Row key={program.id} icon="cap" title={program.name} note={program.university} />
            ))}
          </Rows>
          {direction.programs.length === 0 && <p className="t-note">{t('В справочнике школы программ под это направление пока нет.')}</p>}
        </DataCard>
      ))}
    </>
  )
}

export default function Career() {
  const [mode, setMode] = useState<Mode>('test')
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

  const toggle = (code: string, option: string) =>
    setPicked((prev) => {
      const list = prev[code] ?? []
      return { ...prev, [code]: list.includes(option) ? list.filter((o) => o !== option) : [...list, option] }
    })

  const submit = () => {
    if (answered === 0) {
      toast.error(t('Ответьте хотя бы на один вопрос — тогда будет что разбирать'))
      return
    }
    run.mutate(
      questions.map((question) => ({ question: question.code, value: valueOf(question.code) })),
      { onError: (error) => toast.error(error.message) },
    )
  }

  return (
    <div>
      <ScreenHead
        title={t('Профтест')}
        subtitle={questions.length ? `${questions.length} ${t('вопросов')} · ${t('займёт пять минут')} · ${t('Отвечено')} ${answered} ${t('из')} ${questions.length}` : t('Анкета и разбор: какие направления вам подходят и что под них нужно')}
        actions={
          data?.available && questions.length > 0 && mode === 'test' ? (
            <Button size="sm" disabled={run.isPending} onClick={submit}>
              {run.isPending ? t('Разбираю…') : t('Получить разбор')}
            </Button>
          ) : undefined
        }
      />
      <div className="acad__toolbar">
        <Segmented<Mode>
          value={mode}
          onChange={setMode}
          label={t('Режим')}
          items={[
            { value: 'test', label: t('Анкета') },
            { value: 'history', label: `${t('Прошлые разборы')} · ${runs.length}` },
          ]}
        />
      </div>

      {mode === 'test' && (
        <div className="acad__cols">
          <div className="acad__stack">
            {!data?.available && <DataCard title={t('Профтест сейчас недоступен')} empty={data?.detail ?? t('Модель не подключена, поэтому раздел ждёт её.')} />}
            {data?.available && questions.length === 0 && <DataCard title={t('Анкета пока пуста')} empty={t('вопросы профтеста заводит директор школы — как появятся, анкета откроется')} />}
            {questions.length > 0 && (
              <DataCard title={t('Анкета')} note={t('Ответы сохраняются сами')}>
                <Progress percent={(answered / Math.max(1, questions.length)) * 100} />
                {questions.map((question, index) => {
                  const options = question.options_list
                  const chosen = picked[question.code] ?? []
                  const done = valueOf(question.code) !== ''
                  return (
                    <div key={question.id} className="career__q">
                      <div className="career__qhead">
                        <b className={`num stu__slot${done ? ' stu__slot--done' : ''}`}>{index + 1}</b>
                        <div className="career__qtext">
                          <span className="career__label">{question.text}</span>
                          {question.hint && <p className="t-note">{question.hint}</p>}
                        </div>
                      </div>
                      {options.length > 0 && (
                        <div className="acad__chips" role="group" aria-label={question.text}>
                          {options.map((option) => (
                            <Button key={option} variant={chosen.includes(option) ? 'default' : 'outline'} size="sm" aria-pressed={chosen.includes(option)} disabled={!data?.available} onClick={() => toggle(question.code, option)}>
                              {option}
                            </Button>
                          ))}
                        </div>
                      )}
                      <Field kind="text" name={`own-${question.code}`} label={options.length > 0 ? t('Свой вариант') : t('Ваш ответ')} value={draft[OWN(question.code)] ?? ''} onChange={(value) => setDraft((prev) => ({ ...prev, [OWN(question.code)]: value }))} disabled={!data?.available} className="career__own" />
                    </div>
                  )
                })}
              </DataCard>
            )}
            {run.error && <ErrorNote error={run.error} />}
            {last && last.directions.length > 0 && (
              <>
                {last.summary && <NoteCard title={t('Что получилось')}>{last.summary}</NoteCard>}
                <Directions run={last} />
              </>
            )}
          </div>
          <div className="acad__stack">
            <DataCard title={t('Что вы получите')}>
              <Rows>
                <Row lead={<b className="num stu__slot">1</b>} title={t('Три-четыре направления, которые вам подходят')} />
                <Row lead={<b className="num stu__slot">2</b>} title={t('Какие баллы под них нужны и чего вам не хватает')} />
                <Row lead={<b className="num stu__slot">3</b>} title={t('Готовый фильтр для каталога вузов')} />
              </Rows>
            </DataCard>
            <DataCard title={t('Прошлые разборы')} count={runs.length || undefined} empty={runs.length === 0 && t('пока ни одного')}>
              <Rows>
                {runs.slice(0, 5).map((item) => (
                  <Row key={item.id} icon="clock" title={new Date(item.created_at).toLocaleDateString('ru')} note={item.directions.map((direction) => direction.title).join(', ') || item.error} onOpen={() => setMode('history')} openLabel={t('Открыть')} />
                ))}
              </Rows>
            </DataCard>
            <NoteCard title={t('Кто видит ответы')}>{t('Только вы и директор по поступлению. Разбор можно переделать сколько угодно раз.')}</NoteCard>
          </div>
        </div>
      )}

      {mode === 'history' && (
        <div className="acad__cols">
          <div className="acad__stack">
            <DataCard title={t('Прошлые разборы')} count={runs.length || undefined} empty={runs.length === 0 && t('пройдите анкету — разбор сохранится, и его можно будет сравнить со следующим')}>
              <Rows>
                {runs.map((item) => (
                  <Row key={item.id} icon="clock" title={new Date(item.created_at).toLocaleDateString('ru')} note={item.summary || item.error || undefined} right={<Chip size="sm">{`${item.directions.length} ${t('напр.')}`}</Chip>} />
                ))}
              </Rows>
            </DataCard>
            {runs.map((item) => (
              <DataCard key={item.id} title={new Date(item.created_at).toLocaleDateString('ru')} count={item.directions.length}>
                <Rows>
                  {item.directions.map((direction) => (
                    <Row key={direction.id} icon="target" title={direction.title} note={direction.agreed ? t('отправлено директору') : direction.subjects || undefined} />
                  ))}
                </Rows>
              </DataCard>
            ))}
          </div>
          <div className="acad__stack">
            <NoteCard title={t('Зачем хранить')}>{t('Через полгода вы ответите иначе, и сравнить два разбора полезнее, чем переписать один.')}</NoteCard>
          </div>
        </div>
      )}
    </div>
  )
}
