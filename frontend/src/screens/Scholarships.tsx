/**
 * Стипендии у ученика: каталог строками с фильтрами слева, сохранённые,
 * подбор под профиль. Три показателя в ряд вместо цветного полотна.
 *
 * Ни одной стипендии мимо справочника здесь появиться не может: и каталог,
 * и подбор берут записи из базы (инвариант №10). Непроверенная запись
 * приходит с плашкой от сервера, а не подставляется экраном (инвариант №14).
 */
import { useState } from 'react'
import { useTrack } from '../usage/context'
import { toast } from 'sonner'
import { useSaveScholarship, useSavedScholarships, useScholarshipOverview, useScholarshipPick, useScholarships, type ScholarshipRow } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import EditDrawer from '../components/EditDrawer'
import Field from '../components/Field'
import PhoneFold from '../components/PhoneFold'
import { Row, Rows, Segmented, StatRow } from '../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead, UnverifiedNote } from '../components/ui'
import { Button } from '../components/ui/button'
import { t, tn } from '../i18n'
import { formatDate, formatNumber } from '../lib/format'
import './catalog.css'

type Mode = 'catalog' | 'saved' | 'pick'

function Heart({ row }: { row: ScholarshipRow }) {
  const { save, remove } = useSaveScholarship()
  const busy = save.isPending || remove.isPending
  return (
    <Button
      variant={row.is_saved ? 'secondary' : 'outline'}
      size="sm"
      disabled={busy}
      aria-pressed={row.is_saved}
      onClick={(event) => {
        event.stopPropagation()
        const action = row.is_saved ? remove : save
        action.mutate(row.id, { onSuccess: (result) => toast.success(result.detail), onError: (error) => toast.error(error.message) })
      }}
    >
      {row.is_saved ? t('Сохранена') : t('Сохранить')}
    </Button>
  )
}

function Details({ row, onClose }: { row: ScholarshipRow; onClose: () => void }) {
  return (
    <EditDrawer
      open
      onClose={onClose}
      title={row.name}
      sub={row.organizer || undefined}
      footer={
        <>
          <Heart row={row} />
          {row.url && (
            <Button variant="outline" size="sm" onClick={() => window.open(row.url, '_blank', 'noopener')}>
              {t('Открыть страницу стипендии')}
            </Button>
          )}
        </>
      }
    >
      {!row.is_verified && <UnverifiedNote note={row.verification_note} />}
      <div className="acad__chips">
        {row.basis_titles.map((title) => (
          <Chip key={title} tone="info" size="sm">
            {title}
          </Chip>
        ))}
        <Chip size="sm">{row.funding_title}</Chip>
        {row.level_title && <Chip size="sm">{row.level_title}</Chip>}
        {row.country && <Chip size="sm">{t(row.country)}</Chip>}
      </div>
      <Rows>
        <Row title={t('Сумма')} value={row.amount_title || null} none={t('не указана')} />
        <Row title={t('Дедлайн')} value={row.deadline ? `${formatDate(row.deadline)} · ${row.deadline_state}` : null} none={t('не указан')} />
        {row.university_name && <Row title={t('Вуз')} value={row.university_name} />}
        {row.requirements && <Row title={t('Требования')} note={row.requirements} />}
        {row.description && <Row title={t('Описание')} note={row.description} />}
      </Rows>
    </EditDrawer>
  )
}

/** Подбор под профиль: правила отбирают, модель формулирует. */
function PickPanel({ onOpen }: { onOpen: (id: number) => void }) {
  const pick = useScholarshipPick()
  const result = pick.data
  return (
    <div className="acad__cols">
      <div className="acad__stack">
        {pick.error && <ErrorNote error={pick.error} />}
        <DataCard title={t('Подходят вам')} count={result?.picks.length || undefined} empty={!result && t('нажмите «Подобрать под меня» — отбор идёт по целевой стране и уровню из портфолио')}>
          {result && result.picks.length === 0 && <p className="acad__note">{t('Под ваш профиль в справочнике пока ничего не нашлось.')}</p>}
          <Rows>
            {(result?.picks ?? []).map((row) => (
              <Row
                key={row.id}
                icon="card"
                title={row.name}
                note={`${row.why}${row.missing ? ` · ${t('Чего не хватает.')} ${row.missing}` : ''}`}
                right={<Chip size="sm">{row.deadline_state}</Chip>}
                onOpen={() => onOpen(row.id)}
                openLabel={t('Подробнее')}
              />
            ))}
          </Rows>
        </DataCard>
      </div>
      <div className="acad__stack">
        <DataCard title={t('Подбор под профиль')}>
          <div className="acad__actions">
            <Button onClick={() => pick.mutate()} disabled={pick.isPending}>
              {pick.isPending ? t('Подбираю…') : t('Подобрать под меня')}
            </Button>
          </div>
          {result && result.offline && result.offline_reason && <p className="t-note">{`${t('Объяснения собраны правилами:')} ${result.offline_reason}`}</p>}
        </DataCard>
      </div>
    </div>
  )
}

export default function Scholarships() {
  const trackFilter = useTrack('filter.change')
  const [mode, setMode] = useState<Mode>('catalog')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [open, setOpen] = useState<ScholarshipRow | null>(null)

  const overview = useScholarshipOverview()
  const catalog = useScholarships(filters)
  const saved = useSavedScholarships()

  const setFilter = (name: string, value: string) => setFilters((prev) => ({ ...prev, [name]: value }))
  const hasFilters = Object.values(filters).some(Boolean)
  const rows = catalog.data?.results ?? []
  const savedRows = saved.data?.results ?? []
  const facets = overview.data?.facets
  const funding = overview.data?.funding ?? []

  const columns: Column<ScholarshipRow>[] = [
    {
      key: 'name',
      title: t('Стипендия'),
      width: '34%',
      cell: (row) => (
        <>
          <b>{row.name}</b>
          {row.organizer && <span className="t-note"> · {row.organizer}</span>}
          {!row.is_verified && (
            <Chip tone="warn" size="sm" className="catalog__badge">
              {t('не подтверждено')}
            </Chip>
          )}
        </>
      ),
      sortBy: (row) => row.name,
    },
    { key: 'basis', title: t('Основание'), width: '16%', cell: (row) => row.basis_titles.join(', ') || <span className="t-note">{t('нет')}</span> },
    { key: 'funding', title: t('Финансирование'), width: '14%', cell: (row) => row.funding_title, sortBy: (row) => row.funding_title },
    { key: 'amount', title: t('Сумма'), width: '12%', align: 'right', cell: (row) => <span className="num">{row.amount_title || t('нет')}</span> },
    { key: 'deadline', title: t('Дедлайн'), width: '14%', cell: (row) => <Chip tone={row.deadline_tone} size="sm">{row.deadline_state}</Chip>, sortBy: (row) => row.deadline },
    { key: 'save', title: '', width: '10%', align: 'right', cell: (row) => <Heart row={row} /> },
  ]

  const filterCard = (
    <DataCard title={t('Фильтры')} right={hasFilters ? <Button variant="link" size="sm" onClick={() => { trackFilter(); setFilters({}) }}>{t('Сбросить')}</Button> : undefined}>
      <Field usageFilter kind="text" name="q" label={t('Поиск')} value={filters.q ?? ''} onChange={(value) => setFilter('q', value)} placeholder={t('Название или организатор')} />
      <Field usageFilter kind="select" name="country" label={t('Страна')} value={filters.country ?? ''} onChange={(value) => setFilter('country', value)} placeholder={t('Все страны')} options={(facets?.countries ?? []).map((country) => ({ value: country, title: t(country) }))} />
      <Field usageFilter kind="select" name="level" label={t('Уровень обучения')} value={filters.level ?? ''} onChange={(value) => setFilter('level', value)} placeholder={t('Любой уровень')} options={(facets?.levels ?? []).map((level) => ({ value: level.value, title: level.title }))} />
      <Field usageFilter kind="select" name="funding_type" label={t('Тип финансирования')} value={filters.funding_type ?? ''} onChange={(value) => setFilter('funding_type', value)} placeholder={t('Любое финансирование')} options={(facets?.funding_types ?? []).map((item) => ({ value: item.value, title: item.title }))} />
      <Field usageFilter kind="select" name="basis" label={t('Основание')} value={filters.basis ?? ''} onChange={(value) => setFilter('basis', value)} placeholder={t('Любое основание')} options={(facets?.bases ?? []).map((item) => ({ value: item.value, title: item.title }))} />
    </DataCard>
  )

  return (
    <div>
      <ScreenHead
        title={t('Стипендии')}
        actions={
          <Button size="sm" onClick={() => setMode('pick')}>
            {t('Подобрать под меня')}
          </Button>
        }
      />

      <StatRow>
        <Kpi label={t('В каталоге')} value={overview.data?.total || null} none={t('нет')} note={t('стипендий')} />
        <Kpi tone="warn" label={t('Дедлайн близко')} value={overview.data?.soon || null} none={t('нет')} note={tn(overview.data?.soon_days ?? 30, 'подать нужно в ближайшие {n} день|подать нужно в ближайшие {n} дня|подать нужно в ближайшие {n} дней')} />
        <Kpi tone="good" label={t('Всего финансирования')} value={funding.length ? `${formatNumber(funding[0].amount)} ${funding[0].currency}` : null} none={t('нет')} note={funding.length > 1 ? `${t('и ещё в валютах:')} ${funding.slice(1).map((row) => row.currency).join(', ')}` : t('по каждой валюте отдельно')} />
        <Kpi label={t('Сохранено')} value={saved.data?.count || null} none={t('нет')} onClick={() => setMode('saved')} />
      </StatRow>

      <div className="acad__toolbar">
        <Segmented<Mode>
          value={mode}
          onChange={setMode}
          label={t('Режим')}
          items={[
            { value: 'catalog', label: t('Каталог') },
            { value: 'saved', label: `${t('Сохранённые')} · ${saved.data?.count ?? 0}` },
            { value: 'pick', label: t('Подобрать под меня') },
          ]}
        />
      </div>

      {mode === 'pick' && <PickPanel onOpen={(id) => setOpen([...rows, ...savedRows].find((row) => row.id === id) ?? null)} />}

      {mode === 'saved' && (
        <div className="acad__cols">
          <div className="acad__stack">
            {saved.error && <ErrorNote error={saved.error} />}
            <DataCard title={t('Сохранённые')} count={savedRows.length || undefined} empty={savedRows.length === 0 && t('отметьте в каталоге то, что подходит, — дедлайн появится в календаре')}>
              <Rows>
                {savedRows.map((row) => (
                  <Row key={row.id} icon="card" title={row.name} note={[row.organizer, row.funding_title, row.amount_title].filter(Boolean).join(' · ')} right={<Chip tone={row.deadline_tone} size="sm">{row.deadline_state}</Chip>} onOpen={() => setOpen(row)} openLabel={t('Подробнее')} />
                ))}
              </Rows>
            </DataCard>
          </div>
        </div>
      )}

      {mode === 'catalog' && (
        <div className="catalog__layout">
          <PhoneFold active={hasFilters}>{filterCard}</PhoneFold>
          <div className="acad__stack">
            {catalog.error && <ErrorNote error={catalog.error} />}
            {catalog.isLoading && !catalog.data && <Loading kind="table" />}
            {catalog.data && (
              <div className="card">
                <DataTable
                  columns={columns}
                  rows={rows}
                  rowKey={(row) => row.id}
                  limit={30}
                  onRowClick={setOpen}
                  foot={<span className="t-note">{counted(catalog.data.count ?? rows.length, 'стипендия|стипендии|стипендий')}</span>}
                  empty={
                    <Rows>
                      <Row icon="card" title={hasFilters ? t('По этим фильтрам ничего нет') : t('В справочнике пока нет стипендий')} note={hasFilters ? t('Снимите часть фильтров') : t('Стипендии заводит директор по поступлению')} acts={hasFilters ? <Button variant="secondary" size="sm" onClick={() => setFilters({})}>{t('Снять фильтры')}</Button> : undefined} />
                    </Rows>
                  }
                />
              </div>
            )}
          </div>
        </div>
      )}

      {open && <Details row={open} onClose={() => setOpen(null)} />}
    </div>
  )
}
