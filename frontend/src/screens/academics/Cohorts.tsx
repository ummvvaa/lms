/**
 * Подгруппы и потоки: группы с подгруппами, потоки, деление группы по
 * предмету с даты, сборка потока, правка состава.
 *
 * Образец — `route(['kymbat', 'admin'], '/cohorts')` референса.
 */
import { useEffect, useState } from 'react'
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
} from '../../api/academics'
import { useStudents } from '../../api/hooks'
import EditDrawer from '../../components/EditDrawer'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows, Segmented, StatRow } from '../../components/patterns'
import DataTable, { type Column } from '../../components/DataTable'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { todayAlmaty } from '../../lib/dates'
import { NoteCard } from './shared'

type GroupRow = ReturnType<typeof useCohorts>['data'] extends infer D ? (D extends { groups: infer G } ? (G extends (infer R)[] ? R : never) : never) : never

/** Список учеников с галочками — в форме деления и правки состава. */
function Checklist({ rows, picked, onChange, note }: { rows: AcadStudent[]; picked: Set<number>; onChange: (next: Set<number>) => void; note?: string }) {
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
      {note && <span className="t-note">{note}</span>}
    </div>
  )
}

function SplitDialog({ groups, subjects, initial, onClose }: { groups: GroupRow[]; subjects: { id: number; title: string }[]; initial: string; onClose: () => void }) {
  const split = useSplitGroup()
  const [group, setGroup] = useState(initial || groups[0]?.code || '')
  const [subject, setSubject] = useState(String(subjects[0]?.id ?? ''))
  const [rule, setRule] = useState<'level' | 'alpha' | 'hand'>('alpha')
  const [since, setSince] = useState(todayAlmaty())
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [error, setError] = useState('')
  const found = groups.find((g) => g.code === group)
  const students = useStudents({ group: found ? String(found.id) : '', page_size: 200 })
  const rows: AcadStudent[] = (students.data?.results ?? []).map((s) => ({ id: s.id, full_name: s.full_name, short: s.full_name, group: s.group_code ?? '' }))
  useEffect(() => {
    if (!rows.length) return
    const half = Math.ceil(rows.length / 2)
    setPicked(new Set(rows.slice(0, half).map((r) => r.id)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [students.data, rule])
  const submit = () => {
    const first = [...picked]
    const second = rows.map((r) => r.id).filter((id) => !picked.has(id))
    if (!first.length || !second.length) {
      setError(t('В каждой подгруппе должен быть хотя бы один ученик'))
      return
    }
    split.mutate(
      { group, subject: Number(subject), parts: [first, second], since, rule: rule === 'level' ? t('по уровню') : rule === 'alpha' ? t('по списку пополам') : t('вручную') },
      {
        onSuccess: () => {
          toast.success(`${group} ${t('разделена:')} ${first.length} ${t('и')} ${second.length}. ${t('Теперь заведите уроки для подгрупп в расписании')}`)
          onClose()
        },
        onError: (e) => setError(e.message),
      },
    )
  }
  return (
    <Modal title={t('Разделить группу')} note={t('На подгруппы для одного предмета')} onClose={onClose} wide>
      <Field.Row>
        <Field kind="select" name="group" label={t('Группа')} value={group} onChange={setGroup} options={groups.map((g) => ({ value: g.code, title: `${g.code} · ${counted(g.students, ['ученик', 'ученика', 'учеников'])}` }))} />
        <Field kind="select" name="subject" label={t('Для какого предмета')} value={subject} onChange={setSubject} options={subjects.map((s) => ({ value: String(s.id), title: s.title }))} />
      </Field.Row>
      {found && found.subgroups.some((c) => String(c.subject?.id) === subject) && (
        <Chip tone="warn" className="badge--line">
          {t('У группы по этому предмету уже есть подгруппы. Новое деление заменит их с выбранной даты, старые журналы сохранятся.')}
        </Chip>
      )}
      <Segmented
        value={rule}
        onChange={setRule}
        label={t('Как делить')}
        items={[
          { value: 'alpha', label: t('Пополам по списку') },
          { value: 'level', label: t('По уровню английского') },
          { value: 'hand', label: t('Вручную') },
        ]}
      />
      <span className="t-caps">{`${t('Подгруппа 1 · отмечено')} ${picked.size}, ${t('остальные в подгруппу 2')}`}</span>
      {students.isLoading ? <Loading /> : <Checklist rows={rows} picked={picked} onChange={setPicked} note={t('Снимите или поставьте галочку, чтобы перевести ученика')} />}
      <Field kind="date" name="since" label={t('Деление действует с')} value={since} onChange={setSince} error={error || undefined} />
      <div className="acad__actions">
        <Button onClick={submit} disabled={split.isPending}>
          {t('Разделить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

function StreamDialog({ stream, onClose }: { stream?: AcadCohort; onClose: () => void }) {
  const all = useAllCohorts()
  const make = useMakeStream()
  const update = useUpdateCohort()
  const [name, setName] = useState(stream?.name ?? '')
  const [picked, setPicked] = useState<Set<number>>(new Set(stream?.parts?.map((p) => p.id) ?? []))
  const [error, setError] = useState('')
  const parts = (all.data?.rows ?? []).filter((row) => row.kind !== 'stream')
  const submit = () => {
    if (!name.trim()) {
      setError(t('Нужно название'))
      return
    }
    if (picked.size < 2) {
      setError(t('В потоке хотя бы две части'))
      return
    }
    const done = () => {
      toast.success(stream ? t('Поток сохранён') : t('Поток собран. Уроки для него заводятся в расписании'))
      onClose()
    }
    if (stream) update.mutate({ id: stream.id, name, parts: [...picked] }, { onSuccess: done, onError: (e) => setError(e.message) })
    else make.mutate({ name, parts: [...picked] }, { onSuccess: done, onError: (e) => setError(e.message) })
  }
  return (
    <Modal title={stream ? `${t('Поток')} «${stream.name}»` : t('Собрать поток')} note={t('Несколько групп или подгрупп на одном уроке')} onClose={onClose} wide>
      <Field kind="text" name="name" label={t('Название')} value={name} onChange={setName} placeholder={t('Например: IELTS 7+ · BOSTON + CHICAGO')} autoFocus error={error || undefined} />
      <span className="t-caps">{t('Кто входит')}</span>
      {all.isLoading ? (
        <Loading />
      ) : (
        <div className="acad__checklist">
          {parts.map((row) => (
            <Field
              key={row.id}
              kind="checkbox"
              name={`p${row.id}`}
              label={`${row.name}${row.subject ? ` · ${row.subject.short_title.toLowerCase()}` : row.kind === 'group' ? ` · ${t('вся группа')}` : ''} · ${counted(row.students, ['ученик', 'ученика', 'учеников'])}`}
              checked={picked.has(row.id)}
              onChange={(on) => {
                const next = new Set(picked)
                if (on) next.add(row.id)
                else next.delete(row.id)
                setPicked(next)
              }}
            />
          ))}
          <span className="t-note">{t('Если выбрать группу и её же подгруппу, ученики не задвоятся')}</span>
        </div>
      )}
      <div className="acad__actions">
        <Button onClick={submit} disabled={make.isPending || update.isPending}>
          {stream ? t('Сохранить') : t('Собрать')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
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
      sub={data ? `${data.subject?.title ?? ''} · ${data.rule || ''} · ${used.length ? `${t('в расписании:')} ${used.map((c) => c.title).join('; ')}` : t('в расписании не используется')}` : undefined}
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
        <>
          <span className="t-caps">{`${t('Состав')} · ${counted(picked.size, ['ученик', 'ученика', 'учеников'])}`}</span>
          <Checklist rows={data.candidates ?? []} picked={picked} onChange={setPicked} />
          <Field kind="date" name="since" label={t('Перевод действует с')} value={since} onChange={setSince} />
          <p className="acad__note">{t('Оценки переведённого ученика остаются в журнале прежней подгруппы. В новой подгруппе журнал начнётся с этой даты.')}</p>
          {used.length > 0 && <p className="acad__note">{t('Подгруппа стоит в расписании: удалить нельзя, пока есть её уроки.')}</p>}
        </>
      )}
    </EditDrawer>
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
    {
      key: 'group',
      title: t('Группа'),
      width: '18%',
      cell: (g) => (
        <span>
          <b>{g.code}</b>
          <br />
          <span className="t-note">
            {t('куратор')} {g.curator || t('не назначен')}
          </span>
        </span>
      ),
      sortBy: (g) => g.code,
    },
    { key: 'students', title: t('Учеников'), width: '12%', align: 'right', cell: (g) => <b className="num">{g.students}</b>, sortBy: (g) => g.students },
    {
      key: 'subgroups',
      title: t('Подгруппы'),
      width: '38%',
      cell: (g) =>
        g.subgroups.length ? (
          <span className="acad__chips">
            {g.subgroups.map((c) => (
              <Button key={c.id} variant="outline" size="sm" onClick={() => setDialog({ kind: 'sub', id: c.id })}>
                {`${c.subject?.short_title.toLowerCase() ?? ''} ${c.number} · ${c.students}`}
              </Button>
            ))}
          </span>
        ) : (
          <span className="t-note">{t('группа учится целиком')}</span>
        ),
    },
    { key: 'streams', title: t('В потоках'), width: '20%', cell: (g) => (g.streams.length ? g.streams.join(', ') : <span className="t-note">{t('нет')}</span>) },
    {
      key: 'split',
      title: '',
      width: '12%',
      align: 'right',
      cell: (g) => (
        <Button variant="secondary" size="sm" onClick={() => setDialog({ kind: 'split', group: g.code })}>
          {t('Разделить')}
        </Button>
      ),
    },
  ]
  return (
    <div>
      <ScreenHead
        title={t('Подгруппы и потоки')}
        subtitle={t('Кто с кем учится на уроке. Урок в расписании принадлежит группе, подгруппе или потоку.')}
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
        <Kpi label={t('Групп')} value={data.kpis.groups} note={counted(data.kpis.students, ['ученик', 'ученика', 'учеников'])} />
        <Kpi label={t('Подгрупп')} value={data.kpis.subgroups || null} none={t('нет')} note={data.kpis.subgroups ? `${t('в группах:')} ${data.kpis.subgroup_groups}` : t('группы учатся целиком')} />
        <Kpi label={t('Потоков')} value={data.kpis.streams || null} none={t('нет')} note={t('две группы и больше вместе')} />
        <Kpi label={t('Не в подгруппе')} value={data.kpis.not_split || null} none={t('нет')} note={t('все распределены по подгруппам')} tone={data.kpis.not_split ? 'warn' : undefined} />
      </StatRow>
      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard title={t('Группы')} right={<Field kind="text" name="search" label={t('Найти группу')} value={search} onChange={setSearch} />}>
            <DataTable columns={columns} rows={groups} rowKey={(g) => g.id} empty={t('групп не найдено')} />
          </DataCard>
        </div>
        <div className="acad__stack">
          <DataCard
            title={t('Потоки')}
            count={data.streams.length || undefined}
            empty={data.streams.length === 0 && t('потоков нет')}
            emptyAction={data.streams.length === 0 ? <Button variant="secondary" size="sm" onClick={() => setDialog({ kind: 'stream' })}>{t('Собрать')}</Button> : undefined}
            right={
              <Button variant="link" size="sm" onClick={() => setDialog({ kind: 'stream' })}>
                {t('Собрать')}
              </Button>
            }
          >
            <Rows>
              {data.streams.map((s) => (
                <Row
                  key={s.id}
                  icon="layers"
                  tone="accent"
                  title={s.name}
                  note={`${counted(s.students, ['ученик', 'ученика', 'учеников'])} · ${(s.used as string[] | undefined)?.length ? (s.used as string[]).join('; ') : t('в расписании не используется')}`}
                  acts={
                    <>
                      <Button variant="secondary" size="sm" onClick={() => setDialog({ kind: 'stream', stream: s })}>
                        {t('Изменить')}
                      </Button>
                      <Button variant="outline" size="sm" disabled={Boolean((s.used as string[] | undefined)?.length)} onClick={() => remove.mutate(s.id, { onSuccess: () => toast.success(t('Поток удалён')), onError: (e) => toast.error(e.message) })}>
                        {t('Удалить')}
                      </Button>
                    </>
                  }
                />
              ))}
            </Rows>
          </DataCard>
          <NoteCard title={t('Как это устроено')}>
            {t('Подгруппа — часть группы для одного предмета: английский по уровню, информатика пополам. Две подгруппы идут в одно время в разных кабинетах. Поток — несколько групп или подгрупп на одном уроке. Ученик переходит в другую подгруппу с даты: старые оценки остаются в прежнем журнале, новые идут в новый.')}
          </NoteCard>
        </div>
      </div>
      {dialog?.kind === 'split' && <SplitDialog groups={data.groups} subjects={data.subjects} initial={dialog.group} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'stream' && <StreamDialog stream={dialog.stream} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'sub' && <SubgroupDrawer id={dialog.id} onClose={() => setDialog(null)} />}
    </div>
  )
}
