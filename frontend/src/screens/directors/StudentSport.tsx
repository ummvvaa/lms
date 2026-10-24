/**
 * Мероприятия школы у ученика (макет StSport, 24.10.2026): ближайшее
 * мероприятие, свои заявки и все мероприятия. Заявка — «Участвовать»
 * с комментарием директору или «Приду смотреть»; решает директор спорта.
 * Ученик видит только свои заявки. У 8–10 — в разделе «Спорт», у 11 —
 * во вкладке «Спорт» портфолио.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useApplySport, useMySport, useWithdrawSport, type SportEventRow } from '../../api/directors'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import RowMenu, { RowMenuItem } from '../../components/RowMenu'
import { Segmented, ShowAll } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { formatDateTimeLong, formatDayMonth } from '../../lib/format'
import './directors.css'

const STATUS_TONE: Record<string, Tone> = { pending: 'warn', accepted: 'good', declined: 'neutral' }

function seatsLeft(row: SportEventRow): string {
  if (row.seats === null) return t('без ограничения мест')
  return t('мест осталось {n} из {total}', { n: row.seats_left ?? 0, total: row.seats })
}

export default function StudentSport() {
  const { data, isLoading, error } = useMySport()
  const apply = useApplySport()
  const withdraw = useWithdrawSport()
  const [kind, setKind] = useState<'all' | 'competition' | 'event'>('all')
  const [playing, setPlaying] = useState<SportEventRow | null>(null)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const upcoming = data.rows.filter((row) => !row.past)
  const next = upcoming[0]
  const mine = data.rows.filter((row) => row.mine)
  const shown = upcoming.filter((row) => kind === 'all' || row.kind === kind)

  const watch = (row: SportEventRow) =>
    apply.mutate(
      { id: row.id, kind: 'watch', comment: '' },
      { onSuccess: () => toast.success(t('Заявка отправлена директору спорта')) },
    )

  const actions = (row: SportEventRow) =>
    row.mine ? (
      <Chip tone={STATUS_TONE[row.mine.status]} size="sm">
        {`${row.mine.kind_title} · ${row.mine.status_title.toLocaleLowerCase()}`}
      </Chip>
    ) : (
      <span className="dir__acts">
        {row.spectators && (
          <Button variant="ghost" size="sm" disabled={apply.isPending} onClick={() => watch(row)}>
            {t('Приду смотреть')}
          </Button>
        )}
        <Button variant="outline" size="sm" disabled={row.seats_left === 0} onClick={() => setPlaying(row)}>
          {t('Участвовать')}
        </Button>
      </span>
    )

  return (
    <>
      {next ? (
        <DataCard
          className="card--beam"
          title={next.title}
          note={[next.kind_title, next.sport_title].filter(Boolean).join(' · ')}
        >
          <div className="dir__lines">
            <div className="dir__line">
              <span>{t('Дата')}</span>
              <b>{formatDateTimeLong(next.starts_at)}</b>
            </div>
            <div className="dir__line">
              <span>{t('Место')}</span>
              <b>{next.place}</b>
            </div>
            <div className="dir__line">
              <span>{t('Мест для участников')}</span>
              <b>{seatsLeft(next)}</b>
            </div>
          </div>
          <div className="acad__actions">{actions(next)}</div>
        </DataCard>
      ) : (
        <DataCard
          title={t('Мероприятия школы')}
          empty={t('ближайших мероприятий нет — ведёт директор спорта')}
        />
      )}
      <div className="lay-main lay-main--even">
        <DataCard
          title={t('Все мероприятия')}
          count={shown.length || undefined}
          empty={shown.length === 0 && t('мероприятий пока нет')}
        >
          <div className="filters">
            <Segmented
              value={kind}
              onChange={setKind}
              label={t('Какие')}
              items={[
                { value: 'all', label: t('Все') },
                { value: 'competition', label: t('Соревнования') },
                { value: 'event', label: t('Мероприятия') },
              ]}
            />
          </div>
          <div className="dir__rows">
            <ShowAll>
              {shown.map((row) => (
                <div key={row.id} className="dir__row">
                  <span className="dir__what">
                    <b>{row.title}</b>
                    <span className="t-note">
                      {[
                        formatDayMonth(row.starts_at),
                        row.sport_title,
                        row.place,
                        row.spectators ? '' : t('без зрителей'),
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </span>
                  <span />
                  {actions(row)}
                </div>
              ))}
            </ShowAll>
          </div>
        </DataCard>
        <DataCard
          title={t('Мои заявки')}
          count={mine.length || undefined}
          empty={mine.length === 0 && t('заявок пока нет')}
        >
          <div className="dir__rows">
            <ShowAll>
              {mine.map((row) => (
                <div key={row.id} className="dir__row">
                  <span className="dir__what">
                    <b>{row.title}</b>
                    <span className="t-note">{`${row.mine?.kind_title} · ${formatDayMonth(row.starts_at)}${row.past ? ` · ${t('прошло')}` : ''}`}</span>
                  </span>
                  <Chip tone={STATUS_TONE[row.mine?.status ?? 'pending']} size="sm">
                    {row.mine?.status_title}
                  </Chip>
                  <span className="dir__acts">
                    {row.mine &&
                      !row.past &&
                      !(row.mine.status === 'accepted' && row.mine.kind === 'play') && (
                        <RowMenu>
                          <RowMenuItem
                            onClick={() =>
                              withdraw.mutate(row.mine!.id, {
                                onSuccess: () => toast.success(t('Заявка отозвана')),
                              })
                            }
                          >
                            {t('Отозвать заявку')}
                          </RowMenuItem>
                        </RowMenu>
                      )}
                  </span>
                </div>
              ))}
            </ShowAll>
          </div>
        </DataCard>
      </div>
      {playing && <ApplyDialog row={playing} onClose={() => setPlaying(null)} />}
    </>
  )
}

function ApplyDialog({ row, onClose }: { row: SportEventRow; onClose: () => void }) {
  const apply = useApplySport()
  const [comment, setComment] = useState('')
  return (
    <Modal
      title={t('Участвовать')}
      note={`${row.title} · ${formatDayMonth(row.starts_at)}`}
      onClose={onClose}
    >
      <Field
        kind="textarea"
        name="sport-comment"
        label={t('Комментарий директору')}
        value={comment}
        onChange={setComment}
        rows={3}
        placeholder={t('Например: играю в команде, был на прошлом турнире')}
      />
      {apply.error && <ErrorNote error={apply.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={apply.isPending}
          onClick={() =>
            apply.mutate(
              { id: row.id, kind: 'play', comment },
              {
                onSuccess: () => {
                  toast.success(t('Заявка отправлена директору спорта'))
                  onClose()
                },
              },
            )
          }
        >
          {t('Отправить заявку')}
        </Button>
      </div>
    </Modal>
  )
}
