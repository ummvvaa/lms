/**
 * Прохождение теста профориентации: утверждения по одному в строке, ответ —
 * кнопкой; черновик уходит на сервер пачками, чтобы 144 ответа не пропали
 * при выходе. После сдачи — баллы по шкалам полосками. Ключ (шкалы вопросов)
 * ученику не приходит.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { useMyAnswers, useMyAttempt, useMyFinish, type MyAttempt } from '../../api/career'
import Progress from '../../components/Progress'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tn } from '../../i18n'
import { formatDate } from '../../lib/format'
import ScoreBars from './ScoreBars'

type Picked = { option: number | null; choice: number | null }

const FLUSH_MS = 700

function ResultView({ attempt }: { attempt: MyAttempt }) {
  const navigate = useNavigate()
  return (
    <div>
      <ScreenHead
        title={attempt.test.title}
        crumb={{ label: t('Профтест'), to: '/career' }}
        subtitle={attempt.finished_at ? t('сдан {date}', { date: formatDate(attempt.finished_at) }) : undefined}
        actions={
          <Button variant="outline" size="sm" onClick={() => navigate('/career')}>
            {t('К списку тестов')}
          </Button>
        }
      />
      <div className="acad__cols">
        <DataCard title={t('Баллы по шкалам')} note={t('Полоска — от наименьшего возможного балла к наибольшему')}>
          <ScoreBars scores={attempt.scores ?? []} threshold={attempt.threshold} />
        </DataCard>
      </div>
    </div>
  )
}

export default function CareerTake() {
  const { id } = useParams()
  const attemptId = Number(id)
  const query = useMyAttempt(Number.isFinite(attemptId) ? attemptId : null)
  const save = useMyAnswers()
  const finish = useMyFinish()
  const [picked, setPicked] = useState<Record<number, Picked>>({})
  const [loaded, setLoaded] = useState(false)
  const pending = useRef<Map<number, Picked>>(new Map())
  const timer = useRef<number | null>(null)
  const [saving, setSaving] = useState(false)

  // ответы с сервера — один раз при загрузке; дальше источник правды — экран
  useEffect(() => {
    if (!query.data?.answers || loaded) return
    const next: Record<number, Picked> = {}
    for (const [item, value] of Object.entries(query.data.answers)) next[Number(item)] = value
    setPicked(next)
    setLoaded(true)
  }, [query.data, loaded])

  const flush = () => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current)
      timer.current = null
    }
    if (pending.current.size === 0) return Promise.resolve()
    const answers = [...pending.current.entries()].map(([item, value]) => ({ item, ...value }))
    pending.current = new Map()
    setSaving(true)
    return save.mutateAsync({ attempt: attemptId, answers }).then(
      () => setSaving(false),
      (error: Error) => {
        setSaving(false)
        toast.error(error.message)
      },
    )
  }

  const pick = (item: number, value: Picked) => {
    setPicked((prev) => ({ ...prev, [item]: value }))
    pending.current.set(item, value)
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => void flush(), FLUSH_MS)
  }

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current)
    },
    [],
  )

  const items = useMemo(() => query.data?.items ?? [], [query.data])
  const answered = items.filter((item) => {
    const value = picked[item.id]
    return value && (value.option !== null || value.choice !== null)
  }).length

  if (query.isLoading) return <Loading kind="cards" />
  if (query.error) return <ErrorNote error={query.error} />
  if (!query.data) return null
  const attempt = query.data
  if (attempt.status === 'done') return <ResultView attempt={attempt} />

  const total = items.length
  const left = total - answered
  const submit = async () => {
    await flush()
    finish.mutate(attemptId, {
      onSuccess: () => toast.success(t('Тест сдан — баллы посчитаны')),
      onError: (error) => toast.error(error.message),
    })
  }

  return (
    <div>
      <ScreenHead
        title={attempt.test.title}
        crumb={{ label: t('Профтест'), to: '/career' }}
        subtitle={t('Отвечено {done} из {total}', { done: answered, total })}
        actions={
          <Button size="sm" disabled={left > 0 || finish.isPending} onClick={() => void submit()}>
            {finish.isPending ? t('Считаю…') : t('Сдать тест')}
          </Button>
        }
      />
      <div className="acad__cols">
        <div className="acad__stack">
          {attempt.instruction && (
            <DataCard title={t('Инструкция')}>
              <p className="acad__note">{attempt.instruction}</p>
            </DataCard>
          )}
          <DataCard title={t('Утверждения')} count={total} right={saving ? <Chip size="sm" tone="info">{t('сохраняется…')}</Chip> : undefined}>
            <Progress percent={total ? (answered / total) * 100 : 0} />
            {items.map((item) => {
              const value = picked[item.id]
              const done = Boolean(value && (value.option !== null || value.choice !== null))
              const own = item.choices.length > 0
              return (
                <div key={item.id} className={`ctake__item${done ? ' ctake__item--done' : ''}`}>
                  <div className="ctake__text">
                    <b className="ctake__num num">{item.number}</b>
                    <span>{item.text}</span>
                  </div>
                  <div className={`ctake__answers${own ? ' ctake__answers--choices' : ''}`} role="group" aria-label={item.text}>
                    {own
                      ? item.choices.map((choice) => (
                          <Button
                            key={choice.id}
                            variant={value?.choice === choice.id ? 'default' : 'outline'}
                            size="sm"
                            aria-pressed={value?.choice === choice.id}
                            onClick={() => pick(item.id, { option: null, choice: choice.id })}
                          >
                            {choice.label}
                          </Button>
                        ))
                      : (attempt.options ?? []).map((option) => (
                          <Button
                            key={option.id}
                            variant={value?.option === option.id ? 'default' : 'outline'}
                            size="sm"
                            className="num"
                            aria-pressed={value?.option === option.id}
                            onClick={() => pick(item.id, { option: option.id, choice: null })}
                          >
                            {option.label}
                          </Button>
                        ))}
                  </div>
                </div>
              )
            })}
            <div className="ctake__foot">
              <span className="t-note">{left > 0 ? tn(left, 'Осталось {n} утверждение|Осталось {n} утверждения|Осталось {n} утверждений') : t('Все утверждения отвечены')}</span>
              <Button disabled={left > 0 || finish.isPending} onClick={() => void submit()}>
                {finish.isPending ? t('Считаю…') : t('Сдать тест')}
              </Button>
            </div>
          </DataCard>
        </div>
        {attempt.options && attempt.options.length > 0 && (
          <div className="acad__stack">
            <DataCard title={t('Что означают ответы')}>
              <ul className="bullets">
                {attempt.options.map((option) => (
                  <li key={option.id}>
                    <b className="num">{option.label}</b> — {tn(option.value, '{n} балл|{n} балла|{n} баллов')}
                  </li>
                ))}
              </ul>
              <p className="t-note">{t('Правильных и неправильных ответов нет — отвечайте так, как думаете сейчас.')}</p>
            </DataCard>
          </div>
        )}
      </div>
    </div>
  )
}
