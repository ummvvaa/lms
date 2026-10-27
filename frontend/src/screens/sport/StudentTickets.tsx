/**
 * «Билеты» ученика (макет StTickets, 27.10.2026): анонс с обратным отсчётом
 * до старта по часам сервера (не телефона), «Забрать билет», «Не смогу пойти»,
 * место в очереди и «Беру билет», когда освободился. Ниже — «Мои билеты».
 */
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { useMyTicketAction, useMyTickets, type MyDropRow } from '../../api/sport'
import { Bar, Chip, DataCard, ErrorNote, Loading, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { formatDateTimeLong, formatDayMonth, formatTime } from '../../lib/format'
import '../directors/directors.css'
import './sport.css'

const fail = (reason: unknown) => toast.error(reason instanceof Error ? reason.message : String(reason))

/** Часы сервера: разница с телефоном берётся из ответа и тикает раз в секунду. */
function useServerNow(serverNow: string | undefined): number {
  const offset = useMemo(() => (serverNow ? new Date(serverNow).getTime() - Date.now() : 0), [serverNow])
  const [now, setNow] = useState(() => Date.now() + offset)
  useEffect(() => {
    setNow(Date.now() + offset)
    const tick = window.setInterval(() => setNow(Date.now() + offset), 1000)
    return () => window.clearInterval(tick)
  }, [offset])
  return now
}

function countdown(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  const clock = [hours, minutes, seconds].map((n) => String(n).padStart(2, '0')).join(':')
  return days > 0 ? t('{days} д {clock}', { days, clock }) : clock
}

function mineWords(row: MyDropRow): { label: string; tone: Tone } {
  const mine = row.mine
  if (!mine)
    return row.stage === 'announce'
      ? { label: t('анонс'), tone: 'info' }
      : row.stage === 'past'
        ? { label: t('прошло'), tone: 'neutral' }
        : { label: t('идёт'), tone: 'good' }
  if (mine.status === 'received') return { label: t('получен'), tone: 'good' }
  if (mine.status === 'queued')
    return { label: row.stage === 'past' ? t('был в очереди') : t('в очереди'), tone: 'info' }
  if (mine.status === 'offered') return { label: t('твоя очередь'), tone: 'accent' }
  return { label: mine.status_title.toLocaleLowerCase(), tone: 'neutral' }
}

export default function StudentTickets() {
  const { data, isLoading, error } = useMyTickets()
  const now = useServerNow(data?.now)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const active = data.rows.filter((row) => row.stage !== 'past')
  const mine = data.rows.filter((row) => row.mine)
  return (
    <>
      {active.length === 0 ? (
        <DataCard title={t('Билеты')} empty={t('раздач билетов пока нет · анонс придёт уведомлением')} />
      ) : (
        <div className="sport-choose">
          {active.map((row, index) => (
            <DropCard key={row.id} row={row} now={now} main={index === 0} />
          ))}
        </div>
      )}
      <DataCard
        title={t('Мои билеты')}
        count={mine.length || undefined}
        empty={mine.length === 0 && t('ты ещё не забирал билетов')}
      >
        <div className="dir__rows">
          {mine.map((row) => {
            const words = mineWords(row)
            return (
              <div key={row.id} className="dir__row">
                <span className="dir__what">
                  <b>{row.title}</b>
                  <span className="t-note">{[formatDayMonth(row.event_at), row.place].join(' · ')}</span>
                </span>
                <Chip tone={words.tone} size="sm">
                  {words.label}
                </Chip>
                <span />
              </div>
            )
          })}
        </div>
      </DataCard>
    </>
  )
}

function DropCard({ row, now, main }: { row: MyDropRow; now: number; main: boolean }) {
  const actions = useMyTicketAction()
  const opensIn = new Date(row.opens_at).getTime() - now
  const started = opensIn <= 0
  const mine = row.mine
  const note = [formatDateTimeLong(row.event_at), row.place].join(' · ')
  const head = t('Бесплатные билеты от школы · {n} штук · один в руки', { n: row.count })
  let body
  if (!mine && !started) {
    body = (
      <>
        <p className="sport-count num">{countdown(opensIn)}</p>
        <p className="t-note">
          {t(
            'Раздача начнётся {when}. Кнопка у всех включится в одну и ту же секунду. За 5 минут придёт напоминание',
            {
              when: formatDateTimeLong(row.opens_at),
            },
          )}
        </p>
        <Button disabled>{t('Забрать билет')}</Button>
      </>
    )
  } else if (!mine) {
    body = (
      <>
        <p className="t-note num">
          {row.left > 0
            ? t('Раздача идёт · осталось {n} из {total}', { n: row.left, total: row.count })
            : t('Билеты разобрали · можно встать в очередь')}
        </p>
        <Bar percent={((row.count - row.left) * 100) / Math.max(1, row.count)} />
        <Button
          disabled={actions.claim.isPending}
          onClick={() => actions.claim.mutate(row.id, { onError: fail })}
        >
          {row.left > 0 ? t('Забрать билет') : t('Встать в очередь')}
        </Button>
      </>
    )
  } else if (mine.status === 'received') {
    body = (
      <>
        <Chip tone="good">{t('Билет твой')}</Chip>
        <p className="t-note">
          {t('Забери: {pickup}. Не забрал — билет уходит следующему в очереди', { pickup: row.pickup })}
        </p>
        {row.stage !== 'past' && (
          <Button
            variant="outline"
            disabled={actions.decline.isPending}
            onClick={() =>
              actions.decline.mutate(row.id, {
                onSuccess: () => toast.success(t('Ты отказался · билет ушёл первому в очереди')),
                onError: fail,
              })
            }
          >
            {t('Не смогу пойти')}
          </Button>
        )}
      </>
    )
  } else if (mine.status === 'queued') {
    body = (
      <>
        <Chip tone="info">{t('Билеты разобрали · ты в очереди №{n}', { n: mine.place ?? 0 })}</Chip>
        <p className="t-note">
          {t(
            'Если кто-то откажется, билет предложат тебе по порядку. Придёт уведомление, на ответ будет {n} минут',
            { n: row.offer_minutes },
          )}
        </p>
        <Button
          variant="outline"
          disabled={actions.decline.isPending}
          onClick={() =>
            actions.decline.mutate(row.id, {
              onSuccess: () => toast.success(t('Ты вышел из очереди')),
              onError: fail,
            })
          }
        >
          {t('Выйти из очереди')}
        </Button>
      </>
    )
  } else if (mine.status === 'offered') {
    body = (
      <>
        <Chip tone="accent">{t('Освободился билет — он для тебя')}</Chip>
        <p className="t-note">
          {t('Подтверди до {time}, иначе билет предложат следующему', {
            time: mine.offer_until ? formatTime(mine.offer_until) : '',
          })}
        </p>
        <div className="acad__actions">
          <Button
            variant="outline"
            disabled={actions.decline.isPending}
            onClick={() => actions.decline.mutate(row.id, { onError: fail })}
          >
            {t('Не нужно')}
          </Button>
          <Button
            disabled={actions.accept.isPending}
            onClick={() =>
              actions.accept.mutate(row.id, {
                onSuccess: () => toast.success(t('Билет твой · забери до срока')),
                onError: fail,
              })
            }
          >
            {t('Беру билет')}
          </Button>
        </div>
      </>
    )
  } else {
    body = <Chip tone="neutral">{mine.status_title}</Chip>
  }
  return (
    <DataCard className={main ? 'card--beam' : undefined} title={row.title} note={note}>
      <p className="t-note">{head}</p>
      <div className="sport-drop">{body}</div>
    </DataCard>
  )
}
