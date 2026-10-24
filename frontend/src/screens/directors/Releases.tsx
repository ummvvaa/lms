/**
 * «Освобождения от уроков» — директор талантов (макет TRelease, 24.10.2026).
 *
 * Неделя по дням: кто, куда и на какие уроки отпущен. Освобождение видят
 * Кымбат — меткой на уроке и списком недели в расписании, кураторы — чипом
 * вместо трёх кнопок в утренней отметке, учитель — в составе урока;
 * пропуск такого урока читается как уважительный.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCancelRelease, useOlympiadEvents, useReleases, type ReleaseRow } from '../../api/directors'
import Modal from '../../components/Modal'
import { Segmented } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { shiftDay } from '../../lib/dates'
import { formatDayMonth, weekdayName } from '../../lib/format'
import { ReleaseDialog } from './talent'
import './directors.css'

const iso = (date: Date) => date.toISOString().slice(0, 10)

function monday(day: string): string {
  const date = new Date(`${day}T12:00:00`)
  return shiftDay(day, -((date.getDay() + 6) % 7))
}

export default function Releases() {
  const today = iso(new Date())
  const [week, setWeek] = useState<'this' | 'next'>('this')
  const from = week === 'this' ? monday(today) : shiftDay(monday(today), 7)
  const to = shiftDay(from, 4)
  const { data, isLoading, error } = useReleases(from, to)
  const olympiads = useOlympiadEvents()
  const [creating, setCreating] = useState(false)
  const [opened, setOpened] = useState<ReleaseRow | null>(null)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const days = [0, 1, 2, 3, 4].map((offset) => shiftDay(from, offset))
  const rows = data.rows
  const soon = (olympiads.data?.rows ?? []).filter((row) => row.ends >= today)

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Освобождения от уроков')}
        subtitle={t('видно академ директору и кураторам групп')}
        actions={
          <Button disabled={soon.length === 0} onClick={() => setCreating(true)}>
            {t('Новое освобождение')}
          </Button>
        }
      />
      <div className="filters">
        <Segmented
          value={week}
          onChange={setWeek}
          label={t('Неделя')}
          items={[
            { value: 'this', label: t('Эта неделя') },
            { value: 'next', label: t('Следующая') },
          ]}
        />
        <span className="t-note">{`${formatDayMonth(from)} – ${formatDayMonth(to)} · ${t('освобождений: {n}', { n: rows.reduce((sum, row) => sum + row.students.length, 0) })}`}</span>
      </div>
      <DataCard className="card--beam" title={t('Неделя')} empty={rows.length === 0 && t('на этой неделе освобождений нет')}>
        <div className="dir__week">
          {days.map((day, index) => {
            const found = rows.filter((row) => row.starts <= day && row.ends >= day)
            return (
              <div key={day} className={`dir__day${day === today ? ' dir__day--today' : ''}`}>
                <span className="dir__dayhead">
                  <span>{weekdayName(index)}</span>
                  <span className="t-note">{formatDayMonth(day)}</span>
                </span>
                {found.length === 0 && <span className="t-note">{t('все на уроках')}</span>}
                {found.map((row) => (
                  <button key={row.id} type="button" className="dir__tile" onClick={() => setOpened(row)}>
                    <b>{row.reason}</b>
                    <span className="t-note">{row.all_day ? t('весь день') : t('уроки {a}–{b}', { a: row.slot_from ?? '', b: row.slot_to ?? '' })}</span>
                    <span className="dir__chip-list">
                      {row.students.slice(0, 3).map((s) => (
                        <Chip key={s.id} size="sm">
                          {s.short_name}
                        </Chip>
                      ))}
                      {row.students.length > 3 && <Chip size="sm">{t('ещё {n}', { n: row.students.length - 3 })}</Chip>}
                    </span>
                  </button>
                ))}
              </div>
            )
          })}
        </div>
      </DataCard>
      {creating && <ReleaseDialog olympiads={soon} onClose={() => setCreating(false)} />}
      {opened && <ReleaseCard row={opened} onClose={() => setOpened(null)} />}
    </div>
  )
}

function ReleaseCard({ row, onClose }: { row: ReleaseRow; onClose: () => void }) {
  const cancel = useCancelRelease()
  return (
    <Modal title={row.reason} note={`${row.span} · ${t('освободил: {by}', { by: row.by })}`} onClose={onClose}>
      <div className="dir__lines">
        {row.students.map((student) => (
          <div key={student.id} className="dir__line">
            <span>{student.full_name}</span>
            <span className="t-note">{student.group}</span>
          </div>
        ))}
      </div>
      <div className="acad__actions">
        <Button
          variant="outline"
          disabled={cancel.isPending}
          onClick={() =>
            cancel.mutate(row.id, {
              onSuccess: () => {
                toast.success(t('Освобождение отменено · кураторы увидят'))
                onClose()
              },
            })
          }
        >
          {t('Отменить освобождение')}
        </Button>
        <Button onClick={onClose}>{t('Готово')}</Button>
      </div>
    </Modal>
  )
}
