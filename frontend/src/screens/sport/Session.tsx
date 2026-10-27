/**
 * «Занятие и QR» — директор спорта и администратор (макет SSession, 27.10.2026).
 *
 * Слева — занятия сегодня со статусами «прошло / идёт / скоро». У идущего
 * занятия посередине QR: код меняется каждые N секунд (настройка школы),
 * обратный отсчёт до смены, «На весь экран» и «Закончить занятие». Справа
 * «Пришли / Ещё нет» — опрос раз в несколько секунд, без вебсокетов,
 * и «Отметить» для пришедшего без телефона.
 */
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router'
import {
  sessionToken,
  useSession,
  useSessionAction,
  useSessionsToday,
  type SessionRow,
  type SessionState,
  type SessionToken,
} from '../../api/sport'
import Modal from '../../components/Modal'
import { Segmented } from '../../components/patterns'
import { Chip, DataCard, EmptyNote, ErrorNote, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { formatDateLong, formatTime } from '../../lib/format'
import QrCode from './QrCode'
import { slotTime } from './words'
import '../directors/directors.css'
import './sport.css'

const STATE: Record<SessionState, { label: string; tone: Tone }> = {
  past: { label: tk('прошло'), tone: 'neutral' },
  live: { label: tk('идёт'), tone: 'good' },
  soon: { label: tk('скоро'), tone: 'info' },
}

export default function Session() {
  const { data, isLoading, error } = useSessionsToday()
  const [params, setParams] = useSearchParams()
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const live = data.rows.find((row) => row.state === 'live')
  const picked =
    data.rows.find((row) => row.id === Number(params.get('open'))) ?? live ?? data.rows[0] ?? null
  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Занятие и QR')}
        subtitle={t('{date} · открой занятие и покажи код ученикам', { date: formatDateLong(data.date) })}
      />
      {data.rows.length === 0 ? (
        <DataCard title={t('Занятия сегодня')} empty={t('сегодня занятий секций нет')} />
      ) : (
        <div className="sport-session">
          <DataCard title={t('Занятия сегодня')} count={data.rows.length}>
            <div className="sport-today">
              {data.rows.map((row) => (
                <Button
                  key={row.id}
                  variant="ghost"
                  className={`sport-slot${row.id === picked?.id ? ' sport-slot--on' : ''}`}
                  aria-pressed={row.id === picked?.id}
                  onClick={() => setParams({ open: String(row.id) }, { replace: true })}
                >
                  <span className="sport-slot__line">
                    <b className="sport-slot__head">{row.title}</b>
                    <Chip tone={STATE[row.state].tone} size="sm">
                      {row.state === 'past'
                        ? t('прошло · {came} из {n}', { came: row.came, n: row.enrolled })
                        : t(STATE[row.state].label)}
                    </Chip>
                  </span>
                  <span className="t-note num">
                    {[
                      slotTime(row),
                      t('параллели {grades}', { grades: `${row.parallel_from}–${row.parallel_to}` }),
                      row.room,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </Button>
              ))}
            </div>
          </DataCard>
          {picked && <SessionPanel key={picked.id} row={picked} />}
        </div>
      )}
    </div>
  )
}

/** Свежий токен, пока занятие идёт: перезапрос, когда срок истекает. */
function useLiveToken(id: number, live: boolean) {
  const [token, setToken] = useState<SessionToken | null>(null)
  const [left, setLeft] = useState(0)
  useEffect(() => {
    if (!live) return
    let alive = true
    let timer: number | undefined
    const load = () =>
      sessionToken(id)
        .then((next) => {
          if (!alive) return
          setToken(next)
          setLeft(next.expires_in)
          timer = window.setTimeout(load, Math.max(1, next.expires_in) * 1000)
        })
        .catch(() => {
          if (alive) timer = window.setTimeout(load, 3000)
        })
    void load()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [id, live])
  useEffect(() => {
    if (!live) return
    const tick = window.setInterval(() => setLeft((value) => Math.max(0, value - 1)), 1000)
    return () => window.clearInterval(tick)
  }, [live])
  return { token: live ? token : null, left }
}

function SessionPanel({ row }: { row: SessionRow }) {
  const live = row.state === 'live'
  const { token, left } = useLiveToken(row.id, live)
  const session = useSession(row.id, live)
  const actions = useSessionAction()
  const [ending, setEnding] = useState(false)
  const [tab, setTab] = useState<'came' | 'wait'>('came')
  const box = useRef<HTMLDivElement>(null)
  const url = token?.token ? `${window.location.origin}/s/${token.token}` : ''
  const students = session.data?.students ?? []
  const came = students.filter((s) => s.came)
  const waiting = students.filter((s) => !s.came)
  const shown = tab === 'came' ? came : waiting
  return (
    <>
      <DataCard
        className="card--beam"
        title={row.title}
        note={[
          `${row.day}, ${slotTime(row)}`,
          t('параллели {grades}', { grades: `${row.parallel_from}–${row.parallel_to}` }),
          row.address,
        ]
          .filter(Boolean)
          .join(' · ')}
      >
        <div className="sport-qr" ref={box}>
          {live && url ? (
            <>
              <QrCode value={url} />
              <p className="sport-qr__count">
                {t('новый код через')} <b className="num">{left}</b>
              </p>
              <p className="t-note">
                {t('Фото кода, отправленное другу, через {n} секунд не сработает', { n: token?.ttl ?? 20 })}
              </p>
            </>
          ) : (
            <EmptyNote
              what={
                row.state === 'soon'
                  ? tk('Код откроется в начале занятия')
                  : tk('Занятие закончилось, отметки закрыты')
              }
            />
          )}
        </div>
        {live && (
          <div className="acad__actions">
            <Button
              variant="outline"
              disabled={!url}
              onClick={() => {
                void box.current?.requestFullscreen?.().catch(() => undefined)
              }}
            >
              {t('На весь экран')}
            </Button>
            <Button variant="destructive" onClick={() => setEnding(true)}>
              {t('Закончить занятие')}
            </Button>
          </div>
        )}
      </DataCard>
      <DataCard
        title={t('Отметились')}
        right={<Chip className="num">{t('{came} из {n}', { came: came.length, n: students.length })}</Chip>}
      >
        <Segmented
          value={tab}
          onChange={setTab}
          label={t('Кто пришёл')}
          items={[
            { value: 'came', label: t('Пришли {n}', { n: came.length }) },
            { value: 'wait', label: t('Ещё нет {n}', { n: waiting.length }) },
          ]}
        />
        {session.error && <ErrorNote error={session.error} />}
        {shown.length === 0 ? (
          <EmptyNote what={tab === 'came' ? tk('пока никто не отметился') : tk('отметились все')} />
        ) : (
          <div className="dir__rows sport-roster">
            {shown.map((student) => (
              <div key={student.id} className="dir__row">
                <span className="dir__what">
                  <b className="dir__name">{student.short_name}</b>
                  <span className="t-note">
                    {[
                      t('{n} параллель', { n: student.parallel }),
                      student.came && student.at
                        ? student.method === 'manual'
                          ? t('вручную · {time}', { time: formatTime(student.at) })
                          : t('по QR · {time}', { time: formatTime(student.at) })
                        : '',
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </span>
                <span />
                <span className="dir__acts">
                  {student.came
                    ? student.method === 'manual' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={actions.unmark.isPending}
                          onClick={() => actions.unmark.mutate({ id: row.id, student: student.id })}
                        >
                          {t('Снять')}
                        </Button>
                      )
                    : row.state !== 'soon' && (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={actions.mark.isPending}
                          onClick={() =>
                            actions.mark.mutate(
                              { id: row.id, student: student.id },
                              {
                                onSuccess: () =>
                                  toast.success(t('{name} отмечен вручную', { name: student.short_name })),
                                onError: (reason) => toast.error(reason.message),
                              },
                            )
                          }
                        >
                          {t('Отметить')}
                        </Button>
                      )}
                </span>
              </div>
            ))}
          </div>
        )}
      </DataCard>
      {ending && (
        <Modal title={t('Закончить занятие?')} note={row.title} onClose={() => setEnding(false)}>
          <p className="t-note">
            {t('Отметились {came} из {n}, остальные — пропуск. Вручную отметить можно и после.', {
              came: came.length,
              n: students.length,
            })}
          </p>
          <div className="acad__actions">
            <Button variant="outline" onClick={() => setEnding(false)}>
              {t('Отмена')}
            </Button>
            <Button
              disabled={actions.end.isPending}
              onClick={() =>
                actions.end.mutate(row.id, {
                  onSuccess: () => {
                    toast.success(
                      t('Занятие закончено · {came} отмечены, остальные — пропуск', { came: came.length }),
                    )
                    setEnding(false)
                  },
                })
              }
            >
              {t('Закончить')}
            </Button>
          </div>
        </Modal>
      )}
    </>
  )
}
