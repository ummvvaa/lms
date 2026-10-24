/**
 * «Олимпиады» — директор талантов (макет TOlympiads, 24.10.2026).
 *
 * Слева олимпиады — предстоящие и прошедшие, справа выбранная: участники
 * и их результат («ждём / участник / призёр / победитель»). Внесённый
 * результат один раз попадает в портфолио ученика подтверждённой строкой.
 * Участники и результаты видны академ директору и кураторам.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router'
import {
  useAddOlympiadEntries,
  useOlympiadEvent,
  useOlympiadEvents,
  useOlympiadResult,
  type OlympiadResult,
  type OlympiadRow,
} from '../../api/directors'
import DataTable, { type Column } from '../../components/DataTable'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Segmented, ShowAll } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { formatDayMonth } from '../../lib/format'
import { usePhone } from '../../phone'
import { OlympiadDialog, ReleaseDialog, StudentPicks, useSchoolPicks } from './talent'
import './directors.css'

export const LEVEL_TONE: Record<string, Tone> = { school: 'neutral', city: 'info', national: 'accent', international: 'good' }

const RESULTS: { value: OlympiadResult; label: string }[] = [
  { value: 'pending', label: tk('Ждём') },
  { value: 'participant', label: tk('Участник') },
  { value: 'prize', label: tk('Призёр') },
  { value: 'winner', label: tk('Победитель') },
]

export function olympiadDates(row: Pick<OlympiadRow, 'starts' | 'ends'>): string {
  return row.starts === row.ends ? formatDayMonth(row.starts) : `${formatDayMonth(row.starts)} – ${formatDayMonth(row.ends)}`
}

export default function Olympiads() {
  const { data, isLoading, error } = useOlympiadEvents()
  const [params, setParams] = useSearchParams()
  const [when, setWhen] = useState<'soon' | 'past'>('soon')
  const [creating, setCreating] = useState(params.get('new') === '1')
  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const today = new Date().toISOString().slice(0, 10)
  const soon = data.rows.filter((row) => row.ends >= today)
  const past = data.rows.filter((row) => row.ends < today).reverse()
  const rows = when === 'soon' ? soon : past
  const picked = Number(params.get('open')) || rows[0]?.id || null

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Олимпиады')}
        subtitle={t('участники и результаты видны академ директору и кураторам')}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить олимпиаду')}</Button>}
      />
      <div className="filters">
        <Segmented
          value={when}
          onChange={setWhen}
          label={t('Когда')}
          items={[
            { value: 'soon', label: <>{t('Предстоящие')} <span className="tabs__n num">{soon.length}</span></> },
            { value: 'past', label: <>{t('Прошли')} <span className="tabs__n num">{past.length}</span></> },
          ]}
        />
      </div>
      <div className="lay-main lay-main--even">
        <DataCard title={when === 'soon' ? t('Предстоящие') : t('Прошли')} count={rows.length || undefined} empty={rows.length === 0 && t('олимпиад пока нет')}>
          <div className="dir__rows">
            <ShowAll limit={8}>
              {rows.map((row) => (
                <div key={row.id} className="dir__row">
                  <span className="dir__what">
                    <b>{row.title}</b>
                    <span className="t-note">{[olympiadDates(row), row.place, t('участников: {n}', { n: row.participants ?? 0 })].filter(Boolean).join(' · ')}</span>
                  </span>
                  <Chip tone={LEVEL_TONE[row.level] ?? 'neutral'} size="sm">
                    {row.level_title}
                  </Chip>
                  <span className="dir__acts">
                    <Button variant={row.id === picked ? 'secondary' : 'ghost'} size="sm" onClick={() => setParams({ open: String(row.id) }, { replace: true })}>
                      {t('Открыть')}
                    </Button>
                  </span>
                </div>
              ))}
            </ShowAll>
          </div>
        </DataCard>
        {picked !== null && <Participants id={picked} olympiads={data.rows} key={picked} />}
      </div>
      {creating && <OlympiadDialog levels={data.levels} onClose={() => setCreating(false)} onSaved={(row) => setParams({ open: String(row.id) }, { replace: true })} />}
    </div>
  )
}

function Participants({ id, olympiads }: { id: number; olympiads: OlympiadRow[] }) {
  const phone = usePhone()
  const { data, isLoading, error } = useOlympiadEvent(id)
  const result = useOlympiadResult()
  const [adding, setAdding] = useState(false)
  const [releasing, setReleasing] = useState(false)
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const entries = data.entries ?? []
  type Entry = (typeof entries)[number]
  const columns: Column<Entry>[] = [
    { key: 'name', title: t('Ученик'), width: 'auto', phone: 'head', cell: (row) => <b>{row.student.short_name}</b> },
    { key: 'group', title: t('Группа'), width: '100px', cell: (row) => <Chip size="sm">{row.student.group}</Chip> },
    {
      key: 'free',
      title: t('Уроки'),
      width: '130px',
      cell: (row) => (row.released ? <Chip tone="info" size="sm">{t('освобождён')}</Chip> : <span className="t-note">{t('на уроках')}</span>),
    },
    {
      key: 'result',
      title: t('Результат'),
      width: '170px',
      cell: (row) => (
        <Field
          kind="select"
          name={`result-${row.id}`}
          label={t('Результат')}
          value={row.result}
          onChange={(value) => result.mutate({ id: row.id, result: value as OlympiadResult }, { onSuccess: () => toast.success(t('Результат сохранён: {name}', { name: row.student.short_name })) })}
          options={RESULTS.map((item) => ({ value: item.value, title: t(item.label) }))}
        />
      ),
    },
  ]
  return (
    <DataCard
      className="card--beam"
      title={data.title}
      note={[olympiadDates(data), data.place, data.subject_title, data.level_title].filter(Boolean).join(' · ')}
      count={entries.length || undefined}
      right={
        <>
          <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
            {t('Добавить участников')}
          </Button>
          {entries.length > 0 && (
            <Button variant="ghost" size="sm" onClick={() => setReleasing(true)}>
              {t('Освободить от уроков')}
            </Button>
          )}
        </>
      }
    >
      {entries.length === 0 ? (
        <p className="t-note">{t('участников пока нет — добавьте учеников')}</p>
      ) : (
        <DataTable columns={columns} rows={entries} rowKey={(row) => row.id} limit={8} fit={!phone} />
      )}
      {adding && <AddDialog olympiad={data} onClose={() => setAdding(false)} />}
      {releasing && <ReleaseDialog olympiads={olympiads} olympiad={data} onClose={() => setReleasing(false)} />}
    </DataCard>
  )
}

function AddDialog({ olympiad, onClose }: { olympiad: OlympiadRow; onClose: () => void }) {
  const add = useAddOlympiadEntries()
  const [search, setSearch] = useState('')
  const [picked, setPicked] = useState<number[]>([])
  const taken = new Set((olympiad.entries ?? []).map((e) => e.student.id))
  const items = useSchoolPicks(search).filter((item) => !taken.has(item.id))
  return (
    <Modal title={t('Участники')} note={olympiad.title} onClose={onClose} wide>
      <StudentPicks items={items} picked={picked} onChange={setPicked} onSearch={setSearch} />
      {add.error && <ErrorNote error={add.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={picked.length === 0 || add.isPending}
          onClick={() =>
            add.mutate(
              { id: olympiad.id, students: picked },
              {
                onSuccess: (res) => {
                  toast.success(t('Добавлено участников: {n}', { n: res.added }))
                  onClose()
                },
              },
            )
          }
        >
          {t('Добавить {n}', { n: picked.length })}
        </Button>
      </div>
    </Modal>
  )
}
