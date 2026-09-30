/**
 * Подгруппы и потоки (решение владельца, 27.09.2026).
 *
 * Строка группы: группа, учеников, подгруппы по предметам одной строкой
 * («Английский: 1 — 24, 2 — 24»), в каких потоках, действие «Разделить».
 * Потоки — компактной таблицей. Разделение группы и сбор потока — в панели
 * справа по шагам: что делим, на сколько, кто куда. Подгруппа открывается
 * из строки — состав правится там же.
 */
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  useAllCohorts,
  useCohort,
  useCohorts,
  useDeleteCohort,
  useMakeStream,
  useSplitGroup,
  useUpdateCohort,
  type AcadCohort,
  type AcadStudent,
  type CohortsScreen,
} from '../../api/academics'
import { useStudents } from '../../api/hooks'
import EditDrawer from '../../components/EditDrawer'
import Field from '../../components/Field'
import RowMenu, { RowMenuItem } from '../../components/RowMenu'
import { Segmented, StatRow } from '../../components/patterns'
import DataTable, { type Column } from '../../components/DataTable'
import WizardSteps from '../../components/WizardSteps'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { todayAlmaty } from '../../lib/dates'

type GroupRow = CohortsScreen['groups'][number]

/** Список учеников с галочками — в форме деления и правки состава. */
function Checklist({ rows, picked, onChange }: { rows: AcadStudent[]; picked: Set<number>; onChange: (next: Set<number>) => void }) {
  return (
    <div className="acad__checklist">
      {rows.map((row) => (
        <Field
          key={row.id}
          kind="checkbox"
          name={`s${row.id}`}
          label={row.full_name}
          checked={picked.has(row.id)}
          onChange={(on) => {
            const next = new Set(picked)
            if (on) next.add(row.id)
            else next.delete(row.id)
            onChange(next)
          }}
        />
      ))}
    </div>
  )
}

/** Кнопки «Назад» и «Дальше» под шагом панели. */
function StepActions({ step, last, onBack, onNext, onDone, busy, doneLabel }: { step: number; last: number; onBack: () => void; onNext: () => void; onDone: () => void; busy: boolean; doneLabel: string }) {
  return (
    <>
      {step < last ? (
        <Button onClick={onNext}>{t('Дальше')}</Button>
      ) : (
        <Button onClick={onDone} disabled={busy}>
          {doneLabel}
        </Button>
      )}
      {step > 1 && (
        <Button variant="outline" onClick={onBack}>
          {t('Назад')}
        </Button>
      )}
    </>
  )
}

/** Разделить группу: шаг 1 — группа и предмет, шаг 2 — на сколько и как, шаг 3 — кто куда. */
function SplitDrawer({ groups, subjects, initial, onClose }: { groups: GroupRow[]; subjects: { id: number; title: string }[]; initial: string; onClose: () => void }) {
  const split = useSplitGroup()
  const [step, setStep] = useState(1)
  const [group, setGroup] = useState(initial || groups[0]?.code || '')
  const [subject, setSubject] = useState(String(subjects[0]?.id ?? ''))
  const [parts, setParts] = useState<2 | 3>(2)
  const [rule, setRule] = useState<'alpha' | 'level' | 'hand'>('alpha')
  const [since, setSince] = useState(todayAlmaty())
  const [assign, setAssign] = useState<Map<number, number>>(new Map())
  const [error, setError] = useState('')
  const found = groups.find((g) => g.code === group)
  const students = useStudents({ group: found ? String(found.id) : '', page_size: 200 })
  const rows: AcadStudent[] = useMemo(
    () => (students.data?.results ?? []).map((s) => ({ id: s.id, full_name: s.full_name, short: s.full_name, group: s.group_code ?? '' })),
    [students.data],
  )
  // раскладка по умолчанию: по списку — подряд равными частями
  useEffect(() => {
    const size = Math.ceil(rows.length / parts)
    setAssign(new Map(rows.map((row, index) => [row.id, Math.min(parts, Math.floor(index / Math.max(1, size)) + 1)])))
  }, [rows, parts, rule])
  const already = found?.subgroups.some((c) => String(c.subject?.id) === subject)
  const submit = () => {
    const lists: number[][] = Array.from({ length: parts }, () => [])
    for (const row of rows) lists[(assign.get(row.id) ?? 1) - 1].push(row.id)
    if (lists.some((list) => list.length === 0)) {
      setError(t('В каждой подгруппе должен быть хотя бы один ученик'))
      return
    }
    split.mutate(
      { group, subject: Number(subject), parts: lists, since, rule: rule === 'level' ? t('по уровню') : rule === 'alpha' ? t('по списку') : t('вручную') },
      {
        onSuccess: () => {
          toast.success(`${group} ${t('разделена:')} ${lists.map((list) => list.length).join(' / ')}`)
          onClose()
        },
        onError: (e) => setError(e.message),
      },
    )
  }
  const counts = Array.from({ length: parts }, (_, i) => rows.filter((row) => (assign.get(row.id) ?? 1) === i + 1).length)
  return (
    <EditDrawer
      open
      onClose={onClose}
      title={t('Разделить группу')}
      sub={found ? `${found.code} · ${counted(found.students, 'ученик|ученика|учеников')}` : undefined}
      footer={<StepActions step={step} last={3} onBack={() => setStep(step - 1)} onNext={() => setStep(step + 1)} onDone={submit} busy={split.isPending} doneLabel={t('Разделить')} />}
    >
      <WizardSteps steps={[t('Что делим'), t('На сколько'), t('Кто куда')]} current={step} />
      {step === 1 && (
        <div className="acad__form">
          <Field kind="select" name="group" label={t('Группа')} value={group} onChange={setGroup} options={groups.map((g) => ({ value: g.code, title: `${g.code} · ${counted(g.students, 'ученик|ученика|учеников')}` }))} />
          <Field kind="select" name="subject" label={t('Предмет')} value={subject} onChange={setSubject} options={subjects.map((s) => ({ value: String(s.id), title: s.title }))} />
          {already && <Chip tone="warn">{t('Подгруппы по этому предмету уже есть: новое деление заменит их с выбранной даты')}</Chip>}
        </div>
      )}
      {step === 2 && (
        <div className="acad__form">
          <Segmented<'2' | '3'> value={String(parts) as '2' | '3'} onChange={(value) => setParts(Number(value) as 2 | 3)} label={t('Подгрупп')} items={[{ value: '2', label: t('Две') }, { value: '3', label: t('Три') }]} />
          <Segmented value={rule} onChange={setRule} label={t('Как делить')} items={[{ value: 'alpha', label: t('По списку') }, { value: 'level', label: t('По уровню английского') }, { value: 'hand', label: t('Вручную') }]} />
          <Field kind="date" name="since" label={t('Деление действует с')} value={since} onChange={setSince} />
        </div>
      )}
      {step === 3 &&
        (students.isLoading ? (
          <Loading />
        ) : (
          <div className="acad__form">
            <span className="t-caps">{counts.map((n, i) => `${t('Подгруппа')} ${i + 1} — ${n}`).join(' · ')}</span>
            <div className="acad__checklist">
              {rows.map((row) => (
                <Field
                  key={row.id}
                  kind="select"
                  name={`p${row.id}`}
                  label={row.full_name}
                  value={String(assign.get(row.id) ?? 1)}
                  onChange={(value) => setAssign((old) => new Map(old).set(row.id, Number(value)))}
                  options={Array.from({ length: parts }, (_, i) => ({ value: String(i + 1), title: `${t('Подгруппа')} ${i + 1}` }))}
                />
              ))}
            </div>
            {error && <Chip tone="bad">{error}</Chip>}
          </div>
        ))}
    </EditDrawer>
  )
}

/** Собрать или изменить поток: шаг 1 — название, шаг 2 — кто входит. */
function StreamDrawer({ stream, onClose }: { stream?: AcadCohort; onClose: () => void }) {
  const all = useAllCohorts()
  const make = useMakeStream()
  const update = useUpdateCohort()
  const [step, setStep] = useState(1)
  const [name, setName] = useState(stream?.name ?? '')
  const [picked, setPicked] = useState<Set<number>>(new Set(stream?.parts?.map((p) => p.id) ?? []))
  const [error, setError] = useState('')
  const parts = (all.data?.rows ?? []).filter((row) => row.kind !== 'stream')
  const submit = () => {
    if (!name.trim()) {
      setStep(1)
      setError(t('Нужно название'))
      return
    }
    if (picked.size < 2) {
      setError(t('В потоке хотя бы две части'))
      return
    }
    const done = () => {
      toast.success(stream ? t('Поток сохранён') : t('Поток собран'))
      onClose()
    }
    if (stream) update.mutate({ id: stream.id, name, parts: [...picked] }, { onSuccess: done, onError: (e) => setError(e.message) })
    else make.mutate({ name, parts: [...picked] }, { onSuccess: done, onError: (e) => setError(e.message) })
  }
  return (
    <EditDrawer
      open
      onClose={onClose}
      title={stream ? stream.name : t('Собрать поток')}
      footer={<StepActions step={step} last={2} onBack={() => setStep(1)} onNext={() => setStep(2)} onDone={submit} busy={make.isPending || update.isPending} doneLabel={stream ? t('Сохранить') : t('Собрать')} />}
    >
      <WizardSteps steps={[t('Название'), t('Кто входит')]} current={step} />
      {step === 1 && (
        <div className="acad__form">
          <Field kind="text" name="name" label={t('Название')} value={name} onChange={setName} placeholder={t('Например: IELTS · BOSTON + CHICAGO')} autoFocus error={error || undefined} />
        </div>
      )}
      {step === 2 &&
        (all.isLoading ? (
          <Loading />
        ) : (
          <div className="acad__form">
            <span className="t-caps">{`${t('Отмечено')}: ${picked.size}`}</span>
            <div className="acad__checklist">
              {parts.map((row) => (
                <Field
                  key={row.id}
                  kind="checkbox"
                  name={`p${row.id}`}
                  label={`${row.name}${row.subject ? ` · ${row.subject.short_title.toLowerCase()}` : ''} · ${counted(row.students, 'ученик|ученика|учеников')}`}
                  checked={picked.has(row.id)}
                  onChange={(on) => {
                    const next = new Set(picked)
                    if (on) next.add(row.id)
                    else next.delete(row.id)
                    setPicked(next)
                  }}
                />
              ))}
            </div>
            {error && <Chip tone="bad">{error}</Chip>}
          </div>
        ))}
    </EditDrawer>
  )
}

function SubgroupDrawer({ id, onClose }: { id: number; onClose: () => void }) {
  const cohort = useCohort(id)
  const update = useUpdateCohort()
  const remove = useDeleteCohort()
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [since, setSince] = useState(todayAlmaty())
  useEffect(() => {
    if (cohort.data?.member_ids) setPicked(new Set(cohort.data.member_ids))
  }, [cohort.data])
  const data = cohort.data
  const used = (data?.used ?? []) as { title: string }[]
  return (
    <EditDrawer
      open
      onClose={onClose}
      title={data?.name ?? t('Подгруппа')}
      sub={data ? `${data.subject?.title ?? ''}${data.rule ? ` · ${data.rule}` : ''}${used.length ? ` · ${t('в расписании:')} ${used.map((c) => c.title).join('; ')}` : ''}` : undefined}
      footer={
        <>
          <Button
            onClick={() =>
              update.mutate(
                { id, members: [...picked], since },
                {
                  onSuccess: () => {
                    toast.success(t('Состав подгруппы сохранён'))
                    onClose()
                  },
                  onError: (e) => toast.error(e.message),
                },
              )
            }
            disabled={update.isPending || picked.size === 0}
          >
            {t('Сохранить состав')}
          </Button>
          <Button
            variant="outline"
            onClick={() =>
              remove.mutate(id, {
                onSuccess: () => {
                  toast.success(t('Подгруппа удалена'))
                  onClose()
                },
                onError: (e) => toast.error(e.message),
              })
            }
            disabled={used.length > 0 || remove.isPending}
          >
            {t('Удалить подгруппу')}
          </Button>
        </>
      }
    >
      {cohort.isLoading || !data ? (
        <Loading />
      ) : (
        <div className="acad__form">
          <span className="t-caps">{`${t('Состав')} · ${counted(picked.size, 'ученик|ученика|учеников')}`}</span>
          <Checklist rows={data.candidates ?? []} picked={picked} onChange={setPicked} />
          <Field kind="date" name="since" label={t('Перевод действует с')} value={since} onChange={setSince} />
        </div>
      )}
    </EditDrawer>
  )
}

/** «Английский: 1 — 24, 2 — 24; Информатика: 1 — 12, 2 — 12» кнопками по подгруппам. */
function SubgroupsLine({ rows, onOpen }: { rows: AcadCohort[]; onOpen: (id: number) => void }) {
  const bySubject = new Map<string, AcadCohort[]>()
  for (const cohort of rows) {
    const key = cohort.subject?.title ?? ''
    bySubject.set(key, [...(bySubject.get(key) ?? []), cohort])
  }
  return (
    <span className="acad__wrapline">
      {/* предмет с подгруппами переносится между подгруппами: две-три кнопки
          в ряд шире колонки и уезжали за её край */}
      {[...bySubject.entries()].map(([subject, cohorts]) => (
        <span key={subject} className="acad__wrapline">
          <span className="t-note">{subject}:</span>
          {cohorts
            .sort((a, b) => (a.number ?? 0) - (b.number ?? 0))
            .map((cohort) => (
              <Button key={cohort.id} variant="link" size="sm" className="num" onClick={() => onOpen(cohort.id)}>
                {`${t('подгр.')} ${cohort.number ?? ''} · ${cohort.students} ${t('уч.')}`}
              </Button>
            ))}
        </span>
      ))}
    </span>
  )
}

/** Список значений через запятую: переносится между значениями, не посреди. */
function WrapList({ items, sep = ',' }: { items: string[]; sep?: string }) {
  return (
    <span className="acad__wrapline">
      {items.map((item, index) => (
        <span key={`${index}-${item}`} className="acad__item">
          {index < items.length - 1 ? `${item}${sep}` : item}
        </span>
      ))}
    </span>
  )
}

export default function Cohorts() {
  const { data, isLoading, error } = useCohorts()
  const remove = useDeleteCohort()
  const [search, setSearch] = useState('')
  const [dialog, setDialog] = useState<{ kind: 'split'; group: string } | { kind: 'stream'; stream?: AcadCohort } | { kind: 'sub'; id: number } | null>(null)
  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const groups = data.groups.filter((g) => !search || g.code.toLowerCase().includes(search.toLowerCase()))
  const columns: Column<GroupRow>[] = [
    { key: 'group', title: t('Группа'), width: '12%', cell: (g) => <b>{g.code}</b>, sortBy: (g) => g.code },
    { key: 'students', title: t('Уч.'), hint: t('Учеников'), width: '8%', align: 'right', cell: (g) => <b className="num">{g.students}</b>, sortBy: (g) => g.students },
    {
      key: 'subgroups',
      title: t('Подгруппы'),
      // забирает всё, что осталось от прочих колонок
      width: 'auto',
      cell: (g) => (g.subgroups.length ? <SubgroupsLine rows={g.subgroups} onOpen={(id) => setDialog({ kind: 'sub', id })} /> : <span className="t-note">{t('учится целиком')}</span>),
    },
    { key: 'streams', title: t('В потоках'), width: '22%', cell: (g) => (g.streams.length ? <WrapList items={g.streams} /> : <span className="t-note">{t('нет')}</span>) },
    {
      // кнопка в строке не сжимается вместе с таблицей: ширина числом, не долей
      key: 'split',
      title: '',
      width: '136px',
      align: 'right',
      cell: (g) => (
        <Button variant="secondary" size="sm" onClick={() => setDialog({ kind: 'split', group: g.code })}>
          {t('Разделить')}
        </Button>
      ),
    },
  ]
  const streamColumns: Column<AcadCohort>[] = [
    // название забирает всё, что осталось от прочих колонок
    { key: 'name', title: t('Поток'), width: 'auto', cell: (s) => <b>{s.name}</b>, sortBy: (s) => s.name },
    { key: 'students', title: t('Учеников'), width: '12%', align: 'right', cell: (s) => <b className="num">{s.students}</b>, sortBy: (s) => s.students },
    {
      key: 'parts',
      title: t('Части'),
      width: '24%',
      cell: (s) =>
        s.parts?.length || s.subgroups?.length ? (
          <span className="acad__wrapline">
            {s.parts?.length ? <WrapList items={s.parts.map((p) => p.name)} /> : null}
            {/* подгруппы внутри потока: набираются из всех его групп */}
            {s.subgroups?.length ? <SubgroupsLine rows={s.subgroups} onOpen={(id) => setDialog({ kind: 'sub', id })} /> : null}
          </span>
        ) : (
          <span className="t-note">{t('нет')}</span>
        ),
    },
    {
      key: 'used',
      title: t('В расписании'),
      width: '24%',
      cell: (s) => ((s.used as string[] | undefined)?.length ? <WrapList items={s.used as string[]} sep=";" /> : <span className="t-note">{t('не используется')}</span>),
    },
    {
      // «Изменить» и меню строки в ряд: ширина числом под обе кнопки,
      // иначе на узкой доле колонки они уезжали за край карточки
      key: 'acts',
      title: '',
      width: '168px',
      align: 'right',
      cell: (s) => (
        <span className="acad__inline">
          <Button variant="secondary" size="sm" onClick={() => setDialog({ kind: 'stream', stream: s })}>
            {t('Изменить')}
          </Button>
          <RowMenu>
            <RowMenuItem risk disabled={Boolean((s.used as string[] | undefined)?.length)} onClick={() => remove.mutate(s.id, { onSuccess: () => toast.success(t('Поток удалён')), onError: (e) => toast.error(e.message) })}>
              {t('Удалить поток')}
            </RowMenuItem>
          </RowMenu>
        </span>
      ),
    },
  ]
  return (
    <div>
      <ScreenHead
        title={t('Подгруппы и потоки')}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => setDialog({ kind: 'stream' })}>
              {t('Собрать поток')}
            </Button>
            <Button size="sm" onClick={() => setDialog({ kind: 'split', group: data.groups[0]?.code ?? '' })}>
              {t('Разделить группу')}
            </Button>
          </>
        }
      />
      <StatRow>
        <Kpi label={t('Групп')} value={data.kpis.groups} note={counted(data.kpis.students, 'ученик|ученика|учеников')} />
        <Kpi label={t('Подгрупп')} value={data.kpis.subgroups || null} none={t('нет')} note={data.kpis.subgroups ? `${t('в группах:')} ${data.kpis.subgroup_groups}` : undefined} />
        <Kpi label={t('Потоков')} value={data.kpis.streams || null} none={t('нет')} />
        <Kpi label={t('Не в подгруппе')} value={data.kpis.not_split || null} none={t('нет')} note={data.kpis.not_split ? t('учеников без подгруппы по предмету') : t('все распределены')} tone={data.kpis.not_split ? 'warn' : undefined} />
      </StatRow>
      <div className="acad__stack">
        <DataCard title={t('Группы')} count={groups.length || undefined} right={<Field kind="text" name="search" label={t('Найти группу')} value={search} onChange={setSearch} />}>
          <DataTable columns={columns} rows={groups} rowKey={(g) => g.id} empty={t('групп не найдено')} minWidth="760px" />
        </DataCard>
        <DataCard
          title={t('Потоки')}
          count={data.streams.length || undefined}
          empty={data.streams.length === 0 && t('потоков нет')}
          emptyAction={data.streams.length === 0 ? <Button variant="secondary" size="sm" onClick={() => setDialog({ kind: 'stream' })}>{t('Собрать')}</Button> : undefined}
        >
          <DataTable columns={streamColumns} rows={data.streams} rowKey={(s) => s.id} minWidth="880px" />
        </DataCard>
      </div>
      {dialog?.kind === 'split' && <SplitDrawer groups={data.groups} subjects={data.subjects} initial={dialog.group} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'stream' && <StreamDrawer stream={dialog.stream} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'sub' && <SubgroupDrawer id={dialog.id} onClose={() => setDialog(null)} />}
    </div>
  )
}
