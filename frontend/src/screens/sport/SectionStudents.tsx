/**
 * «Ученики секций» — рабочий список записей директора спорта и администратора (02.11.2026).
 *
 * В списке только ученики хотя бы с одной записью: убрали из всех секций —
 * ученик уходит, история остаётся. Строка — ученик, группа, параллель,
 * секции чипами «секция · день и час · % за месяц», последняя отметка
 * и гостевые визиты за месяц. Фильтры собираются вместе и сбрасываются одной
 * кнопкой; Excel — ровно то, что показано. Действия по записи — на её чипе:
 * перевести, назначить час, убрать. По ученику — «Записать ещё в секцию»
 * и панель истории по клику на строку. Массовые действия — галочками,
 * сначала итог «сколько пройдёт и почему нет», потом выполнение.
 */
import { useDeferredValue, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { downloadFile } from '../../api/client'
import {
  rosterQuery,
  useRemoveEnrollment,
  useRoster,
  useRosterBulk,
  useRosterHistory,
  useSections,
  type BulkAction,
  type BulkResult,
  type RosterEnrollment,
  type RosterFilters,
  type RosterRow,
  type SectionRow,
} from '../../api/sport'
import DataTable, { type Column } from '../../components/DataTable'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import PhoneFold from '../../components/PhoneFold'
import RowMenu, { RowMenuItem, RowMenuSeparator } from '../../components/RowMenu'
import { Chip, DataCard, EmptyNote, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Checkbox } from '../../components/ui/checkbox'
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '../../components/ui/dropdown-menu'
import { t, tk } from '../../i18n'
import { formatDateLong, formatDateTimeLong, formatDayMonth } from '../../lib/format'
import { usePhone } from '../../phone'
import { EnrollDialog, MoveDialog, slotOptions } from './EnrollDialogs'
import { WEEKDAYS, slotWords } from './words'
import '../directors/directors.css'
import './sport.css'

const fail = (reason: unknown) => toast.error(reason instanceof Error ? reason.message : String(reason))

const FLAGS = [
  { key: 'no_hour', label: tk('Без часа') },
  { key: 'below', label: tk('Ниже порога посещения') },
  { key: 'several', label: tk('В нескольких секциях') },
  { key: 'never', label: tk('Не был ни разу за месяц') },
] as const

const PARALLELS = ['8', '9', '10', '11']

type Pick = { row: RosterRow; item: RosterEnrollment }

export default function SectionStudents() {
  const phone = usePhone()
  const [filters, setFilters] = useState<RosterFilters>({})
  const deferred = useDeferredValue(filters)
  const { data, isLoading, error } = useRoster(deferred)
  const sections = useSections()
  const [picked, setPicked] = useState<number[]>([])
  const [enrolling, setEnrolling] = useState<RosterRow | 'new' | null>(null)
  const [moving, setMoving] = useState<(Pick & { assign: boolean }) | null>(null)
  const [removing, setRemoving] = useState<Pick | null>(null)
  const [history, setHistory] = useState<number | null>(null)
  const [bulk, setBulk] = useState<BulkAction | null>(null)
  const active = Object.values(filters).some(Boolean)
  const set = (key: string, value: string) => setFilters((current) => ({ ...current, [key]: value }))

  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const sectionRows = sections.data?.rows ?? []
  const shownIds = new Set(data.rows.map((row) => row.student.id))
  const chosen = picked.filter((id) => shownIds.has(id))
  const download = () =>
    downloadFile(`/sport/roster/export/?${rosterQuery(filters)}`, t('Ученики секций.xlsx'))
      .then(() => toast.success(t('Файл xlsx скачан · строка на каждую запись')))
      .catch(fail)

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Ученики секций')}
        subtitle={t('Кто в каких секциях · переводы, часы и выходы')}
        actions={
          <>
            <Button variant="outline" onClick={download}>
              {t('Скачать Excel')}
            </Button>
            <Button onClick={() => setEnrolling('new')}>{t('Записать ученика')}</Button>
          </>
        }
      />
      <PhoneFold active={active}>
        <div className="filters">
          <Field
            usageFilter
            className="filters__search"
            name="q"
            label={t('Поиск')}
            value={filters.q ?? ''}
            placeholder={t('Фамилия или имя')}
            onChange={(value) => set('q', value)}
          />
          <Field
            usageFilter
            kind="select"
            name="group"
            label={t('Группа')}
            value={filters.group ?? ''}
            onChange={(value) => set('group', value)}
            options={[
              { value: '', title: t('Все группы') },
              ...data.groups.map((row) => ({ value: String(row.id), title: row.code })),
            ]}
          />
          <Field
            usageFilter
            kind="select"
            name="parallel"
            label={t('Параллель')}
            value={filters.parallel ?? ''}
            onChange={(value) => set('parallel', value)}
            options={[
              { value: '', title: t('Все параллели') },
              ...PARALLELS.map((value) => ({ value, title: value })),
            ]}
          />
          <Field
            usageFilter
            kind="select"
            name="section"
            label={t('Секция')}
            value={filters.section ?? ''}
            onChange={(value) => set('section', value)}
            options={[
              { value: '', title: t('Все секции') },
              ...sectionRows.map((row) => ({ value: String(row.id), title: row.title })),
            ]}
          />
          <Field
            usageFilter
            kind="select"
            name="weekday"
            label={t('День')}
            value={filters.weekday ?? ''}
            onChange={(value) => set('weekday', value)}
            options={[
              { value: '', title: t('Все дни') },
              ...data.weekdays.map((day) => ({ value: String(day), title: t(WEEKDAYS[day]) })),
            ]}
          />
          <Field
            usageFilter
            kind="select"
            name="hour"
            label={t('Час')}
            value={filters.hour ?? ''}
            onChange={(value) => set('hour', value)}
            options={[
              { value: '', title: t('Все часы') },
              ...data.hours.map((hour) => ({ value: hour, title: hour })),
            ]}
          />
        </div>
        <div className="filters">
          {FLAGS.map((flag) => (
            <Field
              key={flag.key}
              usageFilter
              kind="checkbox"
              name={flag.key}
              label={flag.key === 'below' ? t('Ниже {n}%', { n: data.threshold }) : t(flag.label)}
              checked={filters[flag.key] === '1'}
              onChange={(value) => set(flag.key, value ? '1' : '')}
            />
          ))}
          {active && (
            <Button variant="ghost" size="sm" className="filters__end" onClick={() => setFilters({})}>
              {t('Сбросить фильтры')}
            </Button>
          )}
        </div>
      </PhoneFold>

      {chosen.length > 0 && (
        <DataCard title={t('Отмечено: {n}', { n: chosen.length })}>
          <div className="acad__actions">
            <Button variant="outline" size="sm" onClick={() => setBulk('assign_hour')}>
              {t('Назначить час')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setBulk('move_hour')}>
              {t('Перевести в час')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setBulk('remove')}>
              {t('Убрать из секции')}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setPicked([])}>
              {t('Снять отметки')}
            </Button>
          </div>
        </DataCard>
      )}

      <DataCard
        title={t('Ученики')}
        right={
          <span className="roster-count">
            <span className="t-note num">
              {t('показано {n} из {total}', { n: data.shown, total: data.total })}
            </span>
            {!phone && data.rows.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPicked(() => data.rows.map((row) => row.student.id))}
              >
                {t('Отметить всех показанных')}
              </Button>
            )}
          </span>
        }
      >
        <DataTable
          columns={columns({
            phone,
            picked,
            setPicked,
            onMove: (pick, assign) => setMoving({ ...pick, assign }),
            onRemove: setRemoving,
            onEnroll: setEnrolling,
            onHistory: (row) => setHistory(row.student.id),
          })}
          rows={data.rows}
          rowKey={(row) => row.student.id}
          fit
          onRowClick={(row) => setHistory(row.student.id)}
          selected={(row) => chosen.includes(row.student.id)}
          empty={
            <EmptyNote
              what={data.total === 0 ? tk('в секциях пока никого') : tk('никого с такими фильтрами')}
              who={
                data.total === 0
                  ? tk('запишите ученика кнопкой «Записать ученика»')
                  : tk('снимите часть фильтров')
              }
            />
          }
        />
      </DataCard>

      {enrolling && (
        <EnrollDialog
          student={enrolling === 'new' ? undefined : enrolling.student}
          onClose={() => setEnrolling(null)}
        />
      )}
      {moving && (
        <MoveDialog
          row={{ id: moving.item.id, student: moving.row.student }}
          assign={moving.assign}
          anySection={!moving.assign}
          options={slotOptions(sectionRows, moving.row.student.parallel, {
            exclude: moving.item.slot,
            section: moving.assign ? moving.item.section : undefined,
          })}
          onClose={() => setMoving(null)}
        />
      )}
      {removing && <RemoveDialog pick={removing} onClose={() => setRemoving(null)} />}
      {history !== null && <HistoryDialog id={history} onClose={() => setHistory(null)} />}
      {bulk && (
        <BulkDialog
          action={bulk}
          students={chosen}
          sections={sectionRows}
          onClose={(done) => {
            setBulk(null)
            if (done) setPicked([])
          }}
        />
      )}
    </div>
  )
}

function columns({
  phone,
  picked,
  setPicked,
  onMove,
  onRemove,
  onEnroll,
  onHistory,
}: {
  phone: boolean
  picked: number[]
  setPicked: (update: (current: number[]) => number[]) => void
  onMove: (pick: Pick, assign: boolean) => void
  onRemove: (pick: Pick) => void
  onEnroll: (row: RosterRow) => void
  onHistory: (row: RosterRow) => void
}): Column<RosterRow>[] {
  return [
    {
      key: 'pick',
      title: '',
      width: '48px',
      phone: 'hidden',
      cell: (row) => (
        <Checkbox
          checked={picked.includes(row.student.id)}
          aria-label={t('Отметить строку: {name}', { name: row.student.full_name })}
          onCheckedChange={(on) =>
            setPicked((current) =>
              on ? [...current, row.student.id] : current.filter((id) => id !== row.student.id),
            )
          }
        />
      ),
    },
    {
      key: 'name',
      title: t('Ученик'),
      width: '22%',
      phone: 'head',
      sortBy: (row) => row.student.full_name,
      cell: (row) => (
        <>
          <b className="dir__name">{row.student.full_name}</b>
          <span className="t-note dir__sub">{t('{n} параллель', { n: row.student.parallel })}</span>
        </>
      ),
    },
    {
      key: 'group',
      title: t('Группа'),
      width: '10%',
      sortBy: (row) => row.student.group,
      cell: (row) => <Chip size="sm">{row.student.group}</Chip>,
    },
    {
      key: 'sections',
      title: t('Секции'),
      width: 'auto',
      sortBy: (row) => row.worst ?? 101,
      cell: (row) => (
        <span className="roster-entries">
          {row.enrollments.map((item) => (
            <EnrollmentChip
              key={item.id}
              item={item}
              onMove={(assign) => onMove({ row, item }, assign)}
              onRemove={() => onRemove({ row, item })}
            />
          ))}
        </span>
      ),
    },
    {
      key: 'last',
      title: t('Последняя отметка'),
      width: '14%',
      sortBy: (row) => row.last_mark?.date ?? '',
      cell: (row) =>
        row.last_mark ? (
          <>
            <span className="num">{formatDayMonth(row.last_mark.date)}</span>
            <span className="t-note dir__sub">{row.last_mark.section}</span>
          </>
        ) : (
          <span className="t-note">{t('отметок нет')}</span>
        ),
    },
    {
      key: 'guests',
      title: t('Гостем за месяц'),
      width: '10%',
      align: 'right',
      sortBy: (row) => row.guest_visits,
      cell: (row) => <span className="num">{row.guest_visits}</span>,
    },
    {
      key: 'actions',
      title: '',
      width: phone ? 'auto' : '56px',
      actions: true,
      cell: (row) => (
        <RowMenu>
          <RowMenuItem onClick={() => onHistory(row)}>{t('История')}</RowMenuItem>
          <RowMenuItem onClick={() => onEnroll(row)} disabled={row.enrollments.length === 0}>
            {t('Записать ещё в секцию')}
          </RowMenuItem>
        </RowMenu>
      ),
    },
  ]
}

/** Чип записи «секция · день и час · %»: по нажатию — действия с этой записью. */
function EnrollmentChip({
  item,
  onMove,
  onRemove,
}: {
  item: RosterEnrollment
  onMove: (assign: boolean) => void
  onRemove: () => void
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="outline" size="sm" className="roster-entry" />}
        aria-label={t('Действия с записью: {section}', { section: item.section_title })}
      >
        <span>{[item.section_title, item.slot_title || t('час не выбран')].join(' · ')}</span>
        {item.percent !== null &&
          (item.below ? (
            <Chip tone="warn" size="sm" className="num">{`${item.percent}%`}</Chip>
          ) : (
            <span className="num">{item.percent}%</span>
          ))}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="rowmenu__panel">
        {item.slot === null ? (
          <RowMenuItem onClick={() => onMove(true)}>{t('Назначить час')}</RowMenuItem>
        ) : (
          <RowMenuItem onClick={() => onMove(false)}>{t('Перевести')}</RowMenuItem>
        )}
        <RowMenuSeparator />
        <RowMenuItem risk onClick={onRemove}>
          {t('Убрать из секции')}
        </RowMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function RemoveDialog({ pick, onClose }: { pick: Pick; onClose: () => void }) {
  const remove = useRemoveEnrollment()
  return (
    <Modal
      title={t('Убрать из секции?')}
      note={`${pick.row.student.full_name} · ${pick.item.section_title}`}
      onClose={onClose}
    >
      <p className="t-note">
        {pick.row.enrollments.length > 1
          ? t('Запись закроется, место освободится. Остальные секции ученика останутся.')
          : t(
              'Запись закроется, место освободится. Других секций нет — ученик уйдёт из списка, история останется.',
            )}
      </p>
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          variant="destructive"
          disabled={remove.isPending}
          onClick={() =>
            remove.mutate(pick.item.id, {
              onSuccess: () => {
                toast.success(t('Ученик убран из секции · место освободилось'))
                onClose()
              },
              onError: fail,
            })
          }
        >
          {t('Убрать')}
        </Button>
      </div>
    </Modal>
  )
}

/** История ученика: записи — когда и кем, события журнала, последние отметки и гостевые визиты. */
function HistoryDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const { data, isLoading, error } = useRosterHistory(id)
  return (
    <Modal
      title={data?.student.full_name ?? t('История')}
      note={data ? `${data.student.group} · ${t('{n} параллель', { n: data.student.parallel })}` : undefined}
      onClose={onClose}
      wide
    >
      {isLoading && <Loading />}
      {error && <ErrorNote error={error} />}
      {data && (
        <div className="roster-history">
          <section>
            <span className="t-card">{t('Записи')}</span>
            <div className="dir__rows">
              {data.enrollments.map((row) => (
                <div key={row.id} className="dir__row">
                  <span className="dir__what">
                    <b>{[row.section_title, row.slot_title || t('час не выбран')].join(' · ')}</b>
                    <span className="t-note">
                      {[
                        t('записан {when}', { when: formatDateLong(row.enrolled_at) }),
                        row.created_by || row.source_title,
                        row.slot_set_by ? t('час назначил {who}', { who: row.slot_set_by }) : '',
                        row.ended_at
                          ? t('вышел {when}', { when: formatDateLong(row.ended_at) }) +
                            (row.ended_by ? ` · ${row.ended_by}` : '')
                          : '',
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </span>
                  <Chip tone={row.ended_at ? 'neutral' : 'good'} size="sm">
                    {row.ended_at ? t('закрыта') : t('действует')}
                  </Chip>
                  <span />
                </div>
              ))}
            </div>
          </section>
          <section>
            <span className="t-card">{t('Журнал')}</span>
            {data.events.length === 0 ? (
              <EmptyNote what={tk('событий нет')} />
            ) : (
              <div className="dir__rows">
                {data.events.slice(0, 12).map((event) => (
                  <div key={event.id} className="dir__row">
                    <span className="dir__what">
                      <b>{event.text}</b>
                      <span className="t-note">
                        {[formatDateTimeLong(event.at), event.author].filter(Boolean).join(' · ')}
                      </span>
                    </span>
                    <span />
                    <span />
                  </div>
                ))}
              </div>
            )}
          </section>
          <section>
            <span className="t-card">{t('Последние отметки')}</span>
            {data.marks.length === 0 ? (
              <EmptyNote what={tk('отметок нет')} />
            ) : (
              <div className="dir__rows">
                {data.marks.map((mark) => (
                  <div key={`${mark.date}-${mark.slot}`} className="dir__row">
                    <span className="dir__what">
                      <b>{formatDateLong(mark.date)}</b>
                      <span className="t-note">{`${mark.section} · ${mark.slot}`}</span>
                    </span>
                    <Chip tone={mark.method === 'manual' ? 'info' : 'good'} size="sm">
                      {mark.method === 'manual' ? t('вручную') : t('по QR')}
                    </Chip>
                    <span />
                  </div>
                ))}
              </div>
            )}
          </section>
          <section>
            <span className="t-card">{t('Гостевые визиты')}</span>
            {data.guests.length === 0 ? (
              <EmptyNote what={tk('гостем не приходил')} />
            ) : (
              <div className="dir__rows">
                {data.guests.map((mark) => (
                  <div key={`${mark.date}-${mark.slot}`} className="dir__row">
                    <span className="dir__what">
                      <b>{formatDateLong(mark.date)}</b>
                      <span className="t-note">{`${mark.section} · ${mark.slot}`}</span>
                    </span>
                    <Chip size="sm">{t('гость')}</Chip>
                    <span />
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </Modal>
  )
}

const BULK_TITLE: Record<BulkAction, string> = {
  assign_hour: tk('Назначить час'),
  move_hour: tk('Перевести в час'),
  remove: tk('Убрать из секции'),
}

/**
 * Массовое действие: выбор секции или часа → итог «пройдёт N, не пройдёт M
 * с причинами» → выполнение. Каждый ученик — своя транзакция на сервере.
 */
function BulkDialog({
  action,
  students,
  sections,
  onClose,
}: {
  action: BulkAction
  students: number[]
  sections: SectionRow[]
  onClose: (done: boolean) => void
}) {
  const run = useRosterBulk()
  const [section, setSection] = useState(String(sections[0]?.id ?? ''))
  const [slot, setSlot] = useState('')
  const [preview, setPreview] = useState<BulkResult | null>(null)
  const current = sections.find((row) => String(row.id) === section)
  const slots = useMemo(
    () =>
      (current?.slots ?? []).map((row) => ({
        value: String(row.id),
        title: t('{slot} · параллели {grades} · свободно {free}', {
          slot: slotWords(row),
          grades: `${row.parallel_from}–${row.parallel_to}`,
          free: row.free ?? 0,
        }),
      })),
    [current],
  )
  const needsSlot = action !== 'remove'
  const body = () => ({
    action,
    students,
    section: Number(section),
    slot: needsSlot ? Number(slot) : undefined,
  })
  const ask = () => run.mutate({ ...body(), apply: false }, { onSuccess: setPreview, onError: fail })
  const apply = () =>
    run.mutate(
      { ...body(), apply: true },
      {
        onSuccess: (result) => {
          toast.success(t('Готово: {ok} · не прошло {failed}', { ok: result.ok, failed: result.failed }))
          if (result.failed === 0) onClose(true)
          else setPreview(result)
        },
        onError: fail,
      },
    )
  const failed = preview?.rows.filter((row) => !row.ok) ?? []
  const warned = preview?.rows.filter((row) => row.ok && row.warnings.length > 0) ?? []
  return (
    <Modal
      title={t(BULK_TITLE[action])}
      note={t('Отмечено учеников: {n}', { n: students.length })}
      onClose={() => onClose(false)}
      wide
    >
      <Field
        kind="select"
        name="bulk-section"
        label={t('Секция')}
        value={section}
        onChange={(value) => {
          setSection(value)
          setSlot('')
          setPreview(null)
        }}
        options={sections.map((row) => ({ value: String(row.id), title: row.title }))}
      />
      {needsSlot && (
        <Field
          kind="select"
          name="bulk-slot"
          label={t('Час занятия')}
          value={slot}
          placeholder={t('Выберите час')}
          onChange={(value) => {
            setSlot(value)
            setPreview(null)
          }}
          options={slots}
        />
      )}
      {preview && (
        <div className="roster-bulk">
          <p className="t-card">
            {preview.applied
              ? t('Выполнено: {ok} · не прошло {failed}', { ok: preview.ok, failed: preview.failed })
              : t('Пройдёт: {ok} · не пройдёт: {failed}', { ok: preview.ok, failed: preview.failed })}
          </p>
          {failed.length > 0 && (
            <div className="dir__rows">
              {failed.map((row) => (
                <div key={row.student.id} className="dir__row">
                  <span className="dir__what">
                    <b className="dir__name">{row.student.short_name}</b>
                    <span className="t-note">{row.reason}</span>
                  </span>
                  <Chip tone="bad" size="sm">
                    {t('не пройдёт')}
                  </Chip>
                  <span />
                </div>
              ))}
            </div>
          )}
          {warned.length > 0 && (
            <div className="sport-warn">
              {warned.map((row) => (
                <p key={row.student.id} className="t-note">
                  {`${row.student.short_name}: ${row.warnings.join(' · ')}`}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="acad__actions">
        <Button variant="outline" onClick={() => onClose(Boolean(preview?.applied))}>
          {preview?.applied ? t('Закрыть') : t('Отмена')}
        </Button>
        {!preview || preview.applied ? (
          !preview?.applied && (
            <Button disabled={!section || (needsSlot && !slot) || run.isPending} onClick={ask}>
              {t('Показать итог')}
            </Button>
          )
        ) : (
          <Button
            variant={action === 'remove' ? 'destructive' : 'default'}
            disabled={preview.ok === 0 || run.isPending}
            onClick={apply}
          >
            {t('Выполнить для {n}', { n: preview.ok })}
          </Button>
        )}
      </div>
    </Modal>
  )
}
