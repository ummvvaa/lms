/**
 * Стипендии у ученика (фаза 44): каталог, сохранённые, подбор под профиль.
 *
 * Гранты и стипендии — то, ради чего многие вообще подают документы
 * за границу: ученик, который не знает про финансирование, отсекает себе
 * половину вариантов. Поэтому раздел свой, а не строчка в каталоге вузов.
 *
 * Ни одной стипендии мимо справочника здесь появиться не может: и каталог,
 * и подбор берут записи из базы (инвариант №10). Непроверенная запись
 * приходит с плашкой от сервера, а не подставляется экраном (инвариант №14).
 */
import { useState } from 'react'
import { toast } from 'sonner'
import {
  useSaveScholarship,
  useSavedScholarships,
  useScholarshipOverview,
  useScholarshipPick,
  useScholarships,
  type ScholarshipRow,
} from '../api/hooks'
import Empty from '../components/Empty'
import Modal from '../components/Modal'
import Icon from '../layout/icons'
import { counted, ErrorNote, Loading, ScreenHead, ScreenTabs, UnverifiedNote } from '../components/ui'
import { CatalogCard, Hero, StatCard, StatRow } from '../components/patterns'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { NativeSelect } from '../components/ui/native-select'
import './scholarships.css'
import { t } from '../i18n'

type Mode = 'catalog' | 'saved' | 'pick'

function Heart({ row }: { row: ScholarshipRow }) {
  const { save, remove } = useSaveScholarship()
  const busy = save.isPending || remove.isPending
  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={busy}
      aria-pressed={row.is_saved}
      aria-label={row.is_saved ? t('Убрать из сохранённых') : t('Сохранить стипендию')}
      className={row.is_saved ? 'schol__heart schol__heart--on' : 'schol__heart'}
      onClick={() => {
        const action = row.is_saved ? remove : save
        action.mutate(row.id, {
          onSuccess: (result) => toast.success(result.detail),
          onError: (error) => toast.error(error.message),
        })
      }}
    >
      <Icon name="heart" size={16} />
    </Button>
  )
}

/** Цвет срока в сетке фактов: сегодня — винным, день-два — янтарным. */
function factTone(days: number | null): 'ok' | 'warn' | 'risk' | undefined {
  if (days === null || days < 0) return undefined
  if (days === 0) return 'risk'
  if (days <= 2) return 'warn'
  return undefined
}

function Card({ row, onOpen }: { row: ScholarshipRow; onOpen: () => void }) {
  const { save, remove } = useSaveScholarship()
  const busy = save.isPending || remove.isPending
  return (
    <CatalogCard
      icon="card"
      tone="indigo"
      title={row.name}
      subtitle={row.organizer || undefined}
      favorite={row.is_saved}
      favoriteLabel={row.is_saved ? t('Убрать из сохранённых') : t('Сохранить стипендию')}
      onFavorite={() => {
        if (busy) return
        const action = row.is_saved ? remove : save
        action.mutate(row.id, {
          onSuccess: (result) => toast.success(result.detail),
          onError: (error) => toast.error(error.message),
        })
      }}
      chips={
        <>
          {row.basis_titles.map((title) => (
            <Badge key={title} variant="indigo">
              {title}
            </Badge>
          ))}
          {!row.is_verified && <Badge variant="warn">{t('не подтверждено')}</Badge>}
        </>
      }
      facts={[
        { value: row.funding_title, label: t('Финансирование') },
        { value: row.country || t('Любая'), label: t('Страна') },
        { value: row.amount_title || '—', label: t('Сумма') },
        { value: row.deadline_state, label: t('Дедлайн'), tone: factTone(row.days_left) },
      ]}
      footer={t('Подробнее')}
      onFooter={onOpen}
    />
  )
}

function Details({ row, onClose }: { row: ScholarshipRow; onClose: () => void }) {
  return (
    <Modal title={row.name} note={row.organizer || undefined} onClose={onClose}>
      {!row.is_verified && <UnverifiedNote note={row.verification_note} />}
      <div className="schol__badges">
        {row.basis_titles.map((title) => (
          <Badge key={title} variant="indigo">
            {title}
          </Badge>
        ))}
        <Badge variant="mute">{row.funding_title}</Badge>
        {row.level_title && <Badge variant="mute">{row.level_title}</Badge>}
        {row.country && <Badge variant="mute">{row.country}</Badge>}
      </div>
      <dl className="schol__list">
        {row.amount_title && (
          <>
            <dt>{t('Сумма')}</dt>
            <dd className="num">{row.amount_title}</dd>
          </>
        )}
        <dt>{t('Дедлайн')}</dt>
        <dd>
          {row.deadline ? new Date(row.deadline).toLocaleDateString('ru') : '—'} · {row.deadline_state}
        </dd>
        {row.university_name && (
          <>
            <dt>{t('Вуз')}</dt>
            <dd>{row.university_name}</dd>
          </>
        )}
        {row.requirements && (
          <>
            <dt>{t('Требования')}</dt>
            <dd>{row.requirements}</dd>
          </>
        )}
        {row.description && (
          <>
            <dt>{t('Описание')}</dt>
            <dd>{row.description}</dd>
          </>
        )}
      </dl>
      <div className="schol__actions">
        <Heart row={row} />
        {row.url && (
          <Button variant="outline" size="sm" render={<a href={row.url} target="_blank" rel="noreferrer" />}>
            {t('Открыть страницу стипендии')}
          </Button>
        )}
      </div>
    </Modal>
  )
}

/** Подбор под профиль: правила отбирают, модель формулирует. */
function PickPanel() {
  const pick = useScholarshipPick()
  const result = pick.data

  return (
    <div>
      <div className="toolbar">
        <Button onClick={() => pick.mutate()} disabled={pick.isPending}>
          {pick.isPending ? t('Подбираю…') : t('Подобрать под меня')}
        </Button>
        <span className="muted schol__note">
          {t('Отбор идёт по вашей целевой стране и уровню обучения из портфолио.')}
        </span>
      </div>

      {pick.error && <ErrorNote error={pick.error} />}
      {result && result.offline && result.offline_reason && (
        <p className="muted schol__note">
          {t('Объяснения собраны правилами:')} {result.offline_reason}
        </p>
      )}
      {result && result.note && <p className="schol__note">{result.note}</p>}

      <div className="grid grid--cards">
        {(result?.picks ?? []).map((row) => (
          <article key={row.id} className="card card-pad schol__card">
            <header className="schol__head">
              <div className="schol__name">
                <b>{row.name}</b>
                {row.organizer && <span className="muted schol__org">{row.organizer}</span>}
              </div>
            </header>
            <div className="schol__badges">
              {row.basis_titles.map((title) => (
                <Badge key={title} variant="indigo">
                  {title}
                </Badge>
              ))}
              <Badge variant="mute">{row.funding_title}</Badge>
              {!row.is_verified && <Badge variant="warn">{t('не подтверждено')}</Badge>}
            </div>
            <p>
              <b>{t('Почему подходит.')}</b> {row.why}
            </p>
            {row.missing && (
              <p className="muted">
                <b>{t('Чего не хватает.')}</b> {row.missing}
              </p>
            )}
            <div className="schol__facts">
              {row.amount_title && (
                <div className="schol__fact">
                  <span className="muted schol__factlabel">{t('Сумма')}</span>
                  <b className="num">{row.amount_title}</b>
                </div>
              )}
              <div className="schol__fact">
                <span className="muted schol__factlabel">{t('Дедлайн')}</span>
                <Badge variant="mute">{row.deadline_state}</Badge>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

export default function Scholarships() {
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

  return (
    <div>
      <ScreenHead
        title={t('Стипендии')}
        subtitle={t('Гранты и финансирование по вашему направлению')}
        actions={
          <Button variant="outline" onClick={() => setMode('saved')}>
            {`${t('Сохранённые')} (${saved.data?.count ?? 0})`}
          </Button>
        }
      />

      <Hero
        tone="indigo"
        eyebrow={t('Каталог школы')}
        title={`${t('В каталоге')} ${counted(overview.data?.total ?? 0, ['стипендия', 'стипендии', 'стипендий'])}`}
        note={t(
          'Подберём те, под требования которых вы уже проходите, и назовём, чего не хватает до остальных. Сохранённые попадают в календарь и напоминания.',
        )}
        figure="dots"
        action={<Button onClick={() => setMode('pick')}>{t('Открыть подбор')}</Button>}
      />

      <StatRow>
        <StatCard
          icon="card"
          tone="indigo"
          label={t('Доступно стипендий')}
          value={overview.data?.total ?? 0}
        />
        <StatCard
          icon="clock"
          tone="warn"
          label={t('Дедлайн близко')}
          value={overview.data?.soon ?? 0}
          note={`${t('подать нужно в ближайшие')} ${overview.data?.soon_days ?? 30} ${t('дней')}`}
        />
        <StatCard
          icon="star"
          tone="ok"
          label={t('Всего финансирования')}
          value={funding.length ? `${funding[0].amount.toLocaleString('ru')} ${funding[0].currency}` : '—'}
          note={
            funding.length > 1
              ? `${t('и ещё в валютах:')} ${funding
                  .slice(1)
                  .map((row) => row.currency)
                  .join(', ')}`
              : t('по каждой валюте отдельно')
          }
        />
      </StatRow>

      <ScreenTabs
        value={mode}
        onChange={setMode}
        items={[
          { value: 'catalog', label: t('Каталог') },
          { value: 'saved', label: `${t('Сохранённые')} · ${saved.data?.count ?? 0}` },
          { value: 'pick', label: t('Подобрать под меня') },
        ]}
      />

      {mode === 'pick' && <PickPanel />}

      {mode === 'saved' && (
        <>
          {saved.isLoading && <Loading kind="cards" />}
          {saved.error && <ErrorNote error={saved.error} />}
          <div className="catgrid">
            {savedRows.map((row) => (
              <Card key={row.id} row={row} onOpen={() => setOpen(row)} />
            ))}
          </div>
          {!saved.isLoading && savedRows.length === 0 && (
            <Empty
              icon="heart"
              title={t('Сохранённых стипендий пока нет')}
              what={t('Отметьте сердечком то, что подходит, — дедлайн появится в календаре.')}
              hint={t(
                'Дедлайн не копируется в задачу: он живёт у самой стипендии, и если школа его сдвинет, срок сдвинется сам.',
              )}
              action={t('Открыть каталог')}
              onAction={() => setMode('catalog')}
            />
          )}
        </>
      )}

      {mode === 'catalog' && (
        <>
          <div className="toolbar">
            <Input
              placeholder={t('Название или организатор')}
              value={filters.q ?? ''}
              onChange={(event) => setFilter('q', event.target.value)}
            />
            <NativeSelect
              aria-label={t('Страна')}
              value={filters.country ?? ''}
              onChange={(event) => setFilter('country', event.target.value)}
            >
              <option value="">{t('Все страны')}</option>
              {(facets?.countries ?? []).map((country) => (
                <option key={country} value={country}>
                  {country}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect
              aria-label={t('Уровень обучения')}
              value={filters.level ?? ''}
              onChange={(event) => setFilter('level', event.target.value)}
            >
              <option value="">{t('Любой уровень')}</option>
              {(facets?.levels ?? []).map((level) => (
                <option key={level.value} value={level.value}>
                  {level.title}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect
              aria-label={t('Тип финансирования')}
              value={filters.funding_type ?? ''}
              onChange={(event) => setFilter('funding_type', event.target.value)}
            >
              <option value="">{t('Любое финансирование')}</option>
              {(facets?.funding_types ?? []).map((item) => (
                <option key={item.value} value={item.value}>
                  {item.title}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect
              aria-label={t('Основание')}
              value={filters.basis ?? ''}
              onChange={(event) => setFilter('basis', event.target.value)}
            >
              <option value="">{t('Любое основание')}</option>
              {(facets?.bases ?? []).map((item) => (
                <option key={item.value} value={item.value}>
                  {item.title}
                </option>
              ))}
            </NativeSelect>
            <span className="toolbar__spacer" />
            <Badge variant="mute" className="num">
              {catalog.data?.count ?? 0}
            </Badge>
          </div>

          {catalog.isLoading && <Loading kind="cards" />}
          {catalog.error && <ErrorNote error={catalog.error} />}

          <div className="catgrid">
            {rows.map((row) => (
              <Card key={row.id} row={row} onOpen={() => setOpen(row)} />
            ))}
          </div>

          {!catalog.isLoading && rows.length === 0 && (
            <Empty
              icon="card"
              title={hasFilters ? t('По этим фильтрам ничего нет') : t('В справочнике пока нет стипендий')}
              what={
                hasFilters
                  ? t('Под эти фильтры не подошла ни одна стипендия — снимите часть.')
                  : t('Стипендии заводит директор по поступлению — как появятся, они будут здесь.')
              }
              hint={t(
                'Каталог собирается только из справочника школы: стипендии, которой там нет, здесь не появится.',
              )}
              action={hasFilters ? t('Снять фильтры') : undefined}
              onAction={hasFilters ? () => setFilters({}) : undefined}
            />
          )}
        </>
      )}

      {open && <Details row={open} onClose={() => setOpen(null)} />}
    </div>
  )
}
