/**
 * «Занятие и QR» — директор спорта и администратор (макет SSession, 27.10.2026).
 *
 * Слева — занятия сегодня со статусами «прошло / идёт / скоро»; занятие идёт
 * по расписанию, открывать и заканчивать его не нужно. Посередине — код
 * секции: он постоянный, тот же, что на печатном листе у площадки
 * (05.11.2026); «Скачать QR для печати» и «На весь экран». У секции без
 * места кода нет — отметка только вручную. Справа «Пришли / Ещё нет» — опрос
 * раз в несколько секунд, «Отметить» для пришедшего без телефона и «Снять
 * отметку» у отмеченного вручную. Ниже — «Гости»: отсканировали код секции,
 * в которую не записаны; записать на этот час — одним нажатием.
 *
 * Сверху — «На проверку»: отметки по коду с неточным местом или чуть за
 * радиусом, за все дни; «Подтвердить» засчитывает, «Отклонить» — нет.
 * Пока отметка ждёт, она нигде не считается.
 */
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router'
import {
  confirmWarnings,
  useEnrollStudent,
  usePendingMarks,
  useReviewMark,
  useSession,
  useSessionAction,
  useSessionsToday,
  type MarkMethod,
  type PendingMark,
  type SessionGuest,
  type SessionRow,
  type SessionState,
  type SessionToken,
} from '../../api/sport'
import Modal from '../../components/Modal'
import { Segmented } from '../../components/patterns'
import { Chip, DataCard, EmptyNote, ErrorNote, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { formatDateLong, formatDayMonth, formatTime } from '../../lib/format'
import { downloadQrSheet } from './printQr'
import QrCode from './QrCode'
import { slotTime } from './words'
import '../directors/directors.css'
import './sport.css'

const STATE: Record<SessionState, { label: string; tone: Tone }> = {
  past: { label: tk('прошло'), tone: 'neutral' },
  live: { label: tk('идёт'), tone: 'good' },
  soon: { label: tk('скоро'), tone: 'info' },
}

/** Как отмечен: «по QR · 16:21 · 40 м» (расстояние — у отметки с проверкой места) или «вручную · 16:30». */
function howWords(method: MarkMethod | '', at: string | null, distance: string): string {
  const time = at ? formatTime(at) : ''
  if (method === 'manual') return t('вручную · {time}', { time })
  return [t('по QR · {time}', { time }), distance].filter(Boolean).join(' · ')
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
        subtitle={t('{date} · код секции постоянный, отметка — по коду и вручную', {
          date: formatDateLong(data.date),
        })}
      />
      <PendingMarks />
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

/**
 * «На проверку»: отметки по печатному QR, которым сервер не поверил сразу —
 * телефон определил место неточно или ученик чуть за радиусом. Список за все
 * дни: отметка не теряется, если директор открыл экран после занятия.
 * Пустой очереди на экране нет.
 */
function PendingMarks() {
  const { data } = usePendingMarks()
  const review = useReviewMark()
  const rows = data?.rows ?? []
  if (rows.length === 0) return null
  const decide = (mark: PendingMark, decision: 'confirm' | 'reject') =>
    review.mutate(
      { id: mark.id, decision },
      {
        onSuccess: () =>
          toast.success(
            decision === 'confirm'
              ? t('{name} — отметка засчитана', { name: mark.student.short_name })
              : t('{name} — отметка отклонена', { name: mark.student.short_name }),
          ),
        onError: (reason) => toast.error(reason.message),
      },
    )
  return (
    <DataCard
      title={t('На проверку')}
      count={rows.length}
      note={t('печатный QR · не считаются до решения')}
    >
      <div className="dir__rows">
        {rows.map((mark) => (
          <div key={mark.id} className="dir__row sport-review">
            <span className="dir__what">
              <b className="dir__name">{mark.student.short_name}</b>
              <span className="t-note">
                {[
                  mark.section,
                  mark.slot_title,
                  mark.at
                    ? t('{date}, {time}', { date: formatDayMonth(mark.date), time: formatTime(mark.at) })
                    : formatDayMonth(mark.date),
                  t('{n} параллель', { n: mark.student.parallel }),
                  mark.student.group,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
              <span className="t-note sport-why">{mark.why}</span>
            </span>
            {mark.guest ? <Chip size="sm">{t('гость')}</Chip> : <span />}
            <span className="dir__acts">
              <Button size="sm" disabled={review.isPending} onClick={() => decide(mark, 'confirm')}>
                {t('Подтвердить')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={review.isPending}
                onClick={() => decide(mark, 'reject')}
              >
                {t('Отклонить')}
              </Button>
            </span>
          </div>
        ))}
      </div>
    </DataCard>
  )
}

/**
 * Свежий токен меняющегося кода, пока занятие идёт: перезапрос, когда срок истекает.
 * У секций код постоянный (05.11.2026) — хук остался кружкам, они берут токен со своей ручки.
 */
export function useLiveToken(id: number, live: boolean, fetchToken: (id: number) => Promise<SessionToken>) {
  const [token, setToken] = useState<SessionToken | null>(null)
  const [left, setLeft] = useState(0)
  useEffect(() => {
    if (!live) return
    let alive = true
    let timer: number | undefined
    const load = () =>
      fetchToken(id)
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
  }, [id, live, fetchToken])
  useEffect(() => {
    if (!live) return
    const tick = window.setInterval(() => setLeft((value) => Math.max(0, value - 1)), 1000)
    return () => window.clearInterval(tick)
  }, [live])
  return { token: live ? token : null, left }
}

function SessionPanel({ row }: { row: SessionRow }) {
  const live = row.state === 'live'
  const session = useSession(row.id, live)
  const actions = useSessionAction()
  const [tab, setTab] = useState<'came' | 'wait'>('came')
  const box = useRef<HTMLDivElement>(null)
  // код секции постоянный: тот же, что на печатном листе; после «Выпустить новый QR» — новый
  const url = session.data?.qr_url ?? row.qr_url
  const students = session.data?.students ?? []
  const guests = session.data?.guest_rows ?? []
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
          {url ? (
            <>
              <QrCode value={url} />
              <p className="t-note">
                {row.state === 'soon'
                  ? t('Код постоянный — он же на листе у площадки. Отметка откроется в {time}', {
                      time: row.starts,
                    })
                  : row.state === 'live'
                    ? t('Код постоянный — он же на листе у площадки. Отметка идёт до {time}', {
                        time: row.ends,
                      })
                    : t('Занятие закончилось — отметка по коду закрыта, вручную отметить можно')}
              </p>
            </>
          ) : (
            <p className="t-note sport-why">
              {t('Место секции не задано — отметка только вручную, обратитесь к администратору')}
            </p>
          )}
        </div>
        {url && (
          <div className="acad__actions">
            <Button variant="outline" onClick={() => void downloadQrSheet(row.section, row.title)}>
              {t('Скачать QR для печати')}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                void box.current?.requestFullscreen?.().catch(() => undefined)
              }}
            >
              {t('На весь экран')}
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
                  <span className="t-note">{t('{n} параллель', { n: student.parallel })}</span>
                  {student.came && student.at && (
                    <span className="t-note sport-how">
                      {howWords(student.method, student.at, student.distance)}
                    </span>
                  )}
                </span>
                <span />
                <span className="dir__acts">
                  {student.came
                    ? student.method === 'manual' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={actions.unmark.isPending}
                          onClick={() =>
                            actions.unmark.mutate(
                              { id: row.id, student: student.id },
                              {
                                onSuccess: () =>
                                  toast.success(t('{name} — отметка снята', { name: student.short_name })),
                                onError: (reason) => toast.error(reason.message),
                              },
                            )
                          }
                        >
                          {t('Снять отметку')}
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
        {guests.length > 0 && <Guests slot={row} guests={guests} />}
      </DataCard>
    </>
  )
}

/**
 * Гости занятия: в процент записанных не входят. «Записать в эту секцию» —
 * на этот час; нельзя — строка объясняет почему; сверх предела секций или
 * лимита часа — сначала подтверждение.
 */
function Guests({ slot, guests }: { slot: SessionRow; guests: SessionGuest[] }) {
  const enroll = useEnrollStudent()
  const [confirm, setConfirm] = useState<SessionGuest | null>(null)
  const send = (guest: SessionGuest, force: boolean) =>
    enroll.mutate(
      { student: guest.id, slot: slot.id, force },
      {
        onSuccess: () => {
          toast.success(
            t('{name} записан · {section}, {time}', {
              name: guest.short_name,
              section: slot.title,
              time: slotTime(slot),
            }),
          )
          setConfirm(null)
        },
        onError: (reason) => {
          if (confirmWarnings(reason)) setConfirm(guest)
          else toast.error(reason.message)
        },
      },
    )
  return (
    <div className="sport-guests">
      <div className="sport-list__head">
        <span className="t-card">{t('Гости')}</span>
        <Chip className="num">{guests.length}</Chip>
      </div>
      <p className="t-note">
        {t('отсканировали код, но в эту секцию не записаны · в процент посещения не входят')}
      </p>
      <div className="dir__rows">
        {guests.map((guest) => (
          <div key={guest.id} className="dir__row sport-guest">
            <span className="dir__what">
              <b className="dir__name">{guest.short_name}</b>
              <span className="t-note">
                {[
                  t('{n} параллель', { n: guest.parallel }),
                  guest.group,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
              {guest.at && (
                <span className="t-note sport-how">{howWords(guest.method, guest.at, guest.distance)}</span>
              )}
              {guest.sections.length > 0 && (
                <span className="t-note">{t('секции: {list}', { list: guest.sections.join(', ') })}</span>
              )}
              {guest.refusal && <span className="t-note sport-why">{guest.refusal}</span>}
            </span>
            <span className="dir__acts">
              <Button
                variant="outline"
                size="sm"
                disabled={Boolean(guest.refusal) || enroll.isPending}
                onClick={() => (guest.warnings.length ? setConfirm(guest) : send(guest, false))}
              >
                {t('Записать в эту секцию')}
              </Button>
            </span>
          </div>
        ))}
      </div>
      {confirm && (
        <Modal title={t('Записать сверх предела?')} note={confirm.full_name} onClose={() => setConfirm(null)}>
          <div className="sport-warn">
            {(confirm.warnings.length ? confirm.warnings : (confirmWarnings(enroll.error) ?? [])).map(
              (item) => (
                <p key={item} className="t-note">
                  {item}
                </p>
              ),
            )}
          </div>
          <div className="acad__actions">
            <Button variant="outline" onClick={() => setConfirm(null)}>
              {t('Отмена')}
            </Button>
            <Button disabled={enroll.isPending} onClick={() => send(confirm, true)}>
              {t('Всё равно записать')}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
