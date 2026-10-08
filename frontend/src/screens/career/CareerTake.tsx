/**
 * Прохождение теста профориентации (решение владельца, 08.10.2026).
 *
 * На ноутбуке — по пять утверждений во всю ширину: ответили на все пять —
 * пятёрка уезжает влево, приезжает следующая; над ней две карточки одной
 * ширины: инструкция и что означают ответы. На телефоне — лента: два
 * отвеченных сверху (мельче и бледнее), текущее в фокусе, два следующих
 * снизу; ответ → пауза 300 мс → лента едет вверх. Возврат — тапом по
 * отвеченному сверху или стрелками. Черновик уходит на сервер пачками,
 * тест открывается на первом неотвеченном; ключ ученику не приходит.
 * Движение не длиннее 320 мс и выключается при «уменьшить движение».
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { useMyAnswers, useMyAttempt, useMyFinish, type MyAttempt } from '../../api/career'
import Notice from '../../components/Notice'
import Progress from '../../components/Progress'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tn } from '../../i18n'
import { formatDate } from '../../lib/format'
import { DURATION, EASE } from '../../motion'
import { usePhone } from '../../phone'
import ScoreBars from './ScoreBars'

type Picked = { option: number | null; choice: number | null }
type Item = NonNullable<MyAttempt['items']>[number]
type Option = NonNullable<MyAttempt['options']>[number]

const FLUSH_MS = 700
/** пауза после ответа, чтобы выбор был виден, прежде чем лента поедет */
const ADVANCE_MS = 300
const PAGE = 5
/** сколько соседей видно на телефоне с каждой стороны от текущего */
const AROUND = 2

const answered = (value?: Picked) => Boolean(value && (value.option !== null || value.choice !== null))

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

/** Кнопки ответа одного утверждения: варианты теста или свои варианты вопроса. */
function Answers({ item, options, value, active, onPick }: { item: Item; options: Option[]; value?: Picked; active: boolean; onPick: (value: Picked) => void }) {
  const own = item.choices.length > 0
  return (
    <div className={`ctake__answers${own ? ' ctake__answers--choices' : ''}`} role="group" aria-label={item.text}>
      {own
        ? item.choices.map((choice) => (
            <Button key={choice.id} variant={value?.choice === choice.id ? 'default' : 'outline'} size="sm" aria-pressed={value?.choice === choice.id} disabled={!active} onClick={() => onPick({ option: null, choice: choice.id })}>
              {choice.label}
            </Button>
          ))
        : options.map((option) => (
            <Button key={option.id} variant={value?.option === option.id ? 'default' : 'outline'} size="sm" className="num" aria-pressed={value?.option === option.id} disabled={!active} onClick={() => onPick({ option: option.id, choice: null })}>
              {option.label}
            </Button>
          ))}
    </div>
  )
}

/** Ответ клавишей: 1–5 — варианты по порядку. */
function keyPick(key: string, item: Item, options: Option[]): Picked | null {
  const index = Number(key) - 1
  if (!Number.isInteger(index) || index < 0) return null
  if (item.choices.length > 0) return item.choices[index] ? { option: null, choice: item.choices[index].id } : null
  return options[index] ? { option: options[index].id, choice: null } : null
}

/** Что означают ответы — одной строкой: «++ 2 · + 1 · 0 0 · − −1 · −− −2». */
function legendOf(options: Option[]): string {
  return options.map((option) => `${option.label} ${option.value}`).join(' · ')
}

export default function CareerTake() {
  const { id } = useParams()
  const attemptId = Number(id)
  const phone = usePhone()
  const still = useReducedMotion()
  const query = useMyAttempt(Number.isFinite(attemptId) ? attemptId : null)
  const save = useMyAnswers()
  const finish = useMyFinish()
  const [picked, setPicked] = useState<Record<number, Picked>>({})
  const [loaded, setLoaded] = useState(false)
  /** текущее утверждение: на телефоне — в фокусе, на ноутбуке — начало пятёрки */
  const [cursor, setCursor] = useState(0)
  const pending = useRef<Map<number, Picked>>(new Map())
  const timer = useRef<number | null>(null)
  const advance = useRef<number | null>(null)
  const [saving, setSaving] = useState(false)

  const items = useMemo(() => query.data?.items ?? [], [query.data])
  const options = useMemo(() => query.data?.options ?? [], [query.data])
  const total = items.length

  // ответы с сервера — один раз при загрузке; дальше источник правды — экран.
  // Открываемся на первом неотвеченном
  useEffect(() => {
    if (!query.data?.answers || loaded) return
    const next: Record<number, Picked> = {}
    for (const [item, value] of Object.entries(query.data.answers)) next[Number(item)] = value
    setPicked(next)
    const first = items.findIndex((item) => !answered(next[item.id]))
    const start = first < 0 ? Math.max(0, items.length - 1) : first
    setCursor(phone ? start : start - (start % PAGE))
    setLoaded(true)
  }, [query.data, loaded, items, phone])

  const flush = () => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current)
      timer.current = null
    }
    if (pending.current.size === 0) return Promise.resolve()
    const rows = [...pending.current.entries()].map(([item, value]) => ({ item, ...value }))
    pending.current = new Map()
    setSaving(true)
    return save.mutateAsync({ attempt: attemptId, answers: rows }).then(
      () => setSaving(false),
      (error: Error) => {
        setSaving(false)
        toast.error(error.message)
      },
    )
  }

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current)
      if (advance.current !== null) window.clearTimeout(advance.current)
    },
    [],
  )

  const done = items.filter((item) => answered(picked[item.id])).length
  const left = total - done
  const pageStart = cursor - (cursor % PAGE)
  const pageItems = items.slice(pageStart, pageStart + PAGE)

  const pick = (index: number, value: Picked) => {
    const item = items[index]
    if (!item) return
    const next = { ...picked, [item.id]: value }
    setPicked(next)
    pending.current.set(item.id, value)
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => void flush(), FLUSH_MS)
    if (advance.current !== null) window.clearTimeout(advance.current)
    // телефон: после ответа лента едет к следующему; ноутбук: пятёрка уезжает,
    // когда отвечены все пять. В обоих случаях — после паузы, чтобы выбор был виден
    if (phone) {
      if (index < total - 1) advance.current = window.setTimeout(() => setCursor(index + 1), ADVANCE_MS)
      return
    }
    const start = index - (index % PAGE)
    const page = items.slice(start, start + PAGE)
    if (page.every((row) => answered(next[row.id])) && start + PAGE < total) {
      advance.current = window.setTimeout(() => setCursor(start + PAGE), ADVANCE_MS)
    }
  }

  // клавиатура: 1–5 — ответ (на ноутбуке — первому неотвеченному в пятёрке), стрелки — переход
  useEffect(() => {
    if (!loaded || total === 0) return
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
      if (phone) {
        if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
          event.preventDefault()
          setCursor((c) => Math.min(total - 1, c + 1))
          return
        }
        if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
          event.preventDefault()
          setCursor((c) => Math.max(0, c - 1))
          return
        }
        const value = items[cursor] ? keyPick(event.key, items[cursor], options) : null
        if (value) pick(cursor, value)
        return
      }
      if (event.key === 'ArrowRight') {
        event.preventDefault()
        setCursor((c) => (c - (c % PAGE) + PAGE < total ? c - (c % PAGE) + PAGE : c))
        return
      }
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        setCursor((c) => Math.max(0, c - (c % PAGE) - PAGE))
        return
      }
      const index = items.findIndex((row, i) => i >= pageStart && i < pageStart + PAGE && !answered(picked[row.id]))
      if (index < 0) return
      const value = keyPick(event.key, items[index], options)
      if (value) pick(index, value)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (query.isLoading) return <Loading kind="cards" />
  if (query.error) return <ErrorNote error={query.error} />
  if (!query.data) return null
  const attempt = query.data
  if (attempt.status === 'done') return <ResultView attempt={attempt} />

  const submit = async () => {
    await flush()
    finish.mutate(attemptId, {
      onSuccess: () => toast.success(t('Тест сдан — баллы посчитаны')),
      onError: (error) => toast.error(error.message),
    })
  }
  const motionOf = (extra: object = {}) => ({ duration: still ? 0 : DURATION.slow, ease: EASE, ...extra })
  const finishButton = (
    <Button size="sm" disabled={left > 0 || finish.isPending} onClick={() => void submit()}>
      {finish.isPending ? t('Считаю…') : t('Сдать тест')}
    </Button>
  )
  const leftWords = left > 0 ? tn(left, 'Осталось {n} утверждение|Осталось {n} утверждения|Осталось {n} утверждений') : t('Все утверждения отвечены')

  // --- телефон: лента в фокусе ---------------------------------------------------
  if (phone) {
    const window_ = items.map((item, index) => ({ item, index, offset: index - cursor })).filter((row) => Math.abs(row.offset) <= AROUND)
    return (
      <div>
        <ScreenHead title={attempt.test.title} crumb={{ label: t('Профтест'), to: '/career' }} subtitle={t('Отвечено {done} из {total}', { done, total })} actions={finishButton} />
        {attempt.instruction && (
          <Notice summary={t('Инструкция')} className="ctake__notice">
            <p>{attempt.instruction}</p>
          </Notice>
        )}
        {options.length > 0 && <p className="t-note num ctake__legend">{legendOf(options)}</p>}
        <Progress percent={total ? (done / total) * 100 : 0} />
        <div className="cstack" aria-live="polite">
          <AnimatePresence initial={false}>
            {window_.map(({ item, index, offset }) => {
              const current = offset === 0
              const value = picked[item.id]
              const scale = 1 - Math.abs(offset) * 0.07
              const opacity = current ? 1 : offset < 0 ? 0.55 - (Math.abs(offset) - 1) * 0.25 : 0.4 - (offset - 1) * 0.2
              return (
                <motion.div
                  key={item.id}
                  layout
                  initial={{ opacity: 0, scale: 0.85 }}
                  animate={{ opacity, scale }}
                  exit={{ opacity: 0, scale: 0.85 }}
                  transition={motionOf()}
                  className={`cstack__item${current ? ' cstack__item--current' : ''}${offset < 0 ? ' cstack__item--past' : ''}${offset > 0 ? ' cstack__item--next' : ''}`}
                  style={{ transformOrigin: 'center' }}
                  aria-current={current ? 'step' : undefined}
                  onClick={offset < 0 ? () => setCursor(index) : undefined}
                >
                  <div className="ctake__text">
                    <b className={`ctake__num num${answered(value) ? ' ctake__num--done' : ''}`}>{item.number}</b>
                    <span>{item.text}</span>
                  </div>
                  {(current || offset < 0) && <Answers item={item} options={options} value={value} active={current} onPick={(next) => pick(index, next)} />}
                </motion.div>
              )
            })}
          </AnimatePresence>
        </div>
        <div className="ctake__foot">
          <span className="t-note">{leftWords}</span>
          <div className="ctake__nav">
            <Button variant="outline" size="sm" disabled={cursor === 0} onClick={() => setCursor(cursor - 1)}>
              {t('Назад')}
            </Button>
            <Button variant="outline" size="sm" disabled={cursor >= total - 1} onClick={() => setCursor(cursor + 1)}>
              {t('Дальше')}
            </Button>
          </div>
        </div>
        {saving && <Chip size="sm" tone="info">{t('сохраняется…')}</Chip>}
      </div>
    )
  }

  // --- ноутбук: по пять во всю ширину -------------------------------------------------
  const pageNo = Math.floor(pageStart / PAGE) + 1
  const pages = Math.max(1, Math.ceil(total / PAGE))
  const from = pageStart + 1
  const to = Math.min(total, pageStart + PAGE)
  return (
    <div>
      <ScreenHead title={attempt.test.title} crumb={{ label: t('Профтест'), to: '/career' }} subtitle={t('Отвечено {done} из {total}', { done, total })} actions={finishButton} />
      <div className="acad__cols acad__cols--even ctake__lead">
        <DataCard title={t('Инструкция')} empty={!attempt.instruction && t('учитель не добавил инструкцию')}>
          {attempt.instruction && <p className="acad__note">{attempt.instruction}</p>}
        </DataCard>
        <DataCard title={t('Что означают ответы')}>
          {options.length > 0 && (
            <ul className="bullets">
              {options.map((option) => (
                <li key={option.id}>
                  <b className="num">{option.label}</b> — {tn(option.value, '{n} балл|{n} балла|{n} баллов')}
                </li>
              ))}
            </ul>
          )}
          <p className="t-note">{t('Правильных и неправильных ответов нет — отвечайте так, как думаете сейчас. Клавиши 1–5 — ответ, стрелки — переход.')}</p>
        </DataCard>
      </div>
      <DataCard
        title={t('Утверждения {from}–{to} из {total}', { from, to, total })}
        right={saving ? <Chip size="sm" tone="info">{t('сохраняется…')}</Chip> : <span className="t-note num">{t('страница {page} из {pages}', { page: pageNo, pages })}</span>}
      >
        <Progress percent={total ? (done / total) * 100 : 0} />
        <div className="cpage">
          <AnimatePresence initial={false} mode="wait">
            <motion.div
              key={pageStart}
              initial={{ opacity: 0, x: still ? 0 : 48 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: still ? 0 : -48 }}
              transition={motionOf({ duration: still ? 0 : DURATION.base })}
            >
              {pageItems.map((item, i) => {
                const index = pageStart + i
                const value = picked[item.id]
                return (
                  <div key={item.id} className={`ctake__item${answered(value) ? ' ctake__item--done' : ''}`}>
                    <div className="ctake__text">
                      <b className="ctake__num num">{item.number}</b>
                      <span>{item.text}</span>
                    </div>
                    <Answers item={item} options={options} value={value} active onPick={(next) => pick(index, next)} />
                  </div>
                )
              })}
            </motion.div>
          </AnimatePresence>
        </div>
        <div className="ctake__foot">
          <span className="t-note">{leftWords}</span>
          <div className="ctake__nav">
            <Button variant="outline" size="sm" disabled={pageStart === 0} onClick={() => setCursor(Math.max(0, pageStart - PAGE))}>
              {t('Назад')}
            </Button>
            {pageStart + PAGE < total ? (
              <Button variant="secondary" size="sm" onClick={() => setCursor(pageStart + PAGE)}>
                {t('Дальше')}
              </Button>
            ) : (
              <Button disabled={left > 0 || finish.isPending} onClick={() => void submit()}>
                {finish.isPending ? t('Считаю…') : t('Сдать тест')}
              </Button>
            )}
          </div>
        </div>
      </DataCard>
    </div>
  )
}
