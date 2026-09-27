/**
 * Отбор в олимпиадную группу — экран директора талантов и администратора.
 *
 * Отметка открывает ученику раздел материалов, снятие — закрывает.
 * Правка идёт через журнал изменений, как любое доменное поле.
 * Слева таблица учеников с кнопкой в строке, справа — кто уже в группе.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useOlympiadGroup, usePickForGroup, type GroupRow } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import Field from '../components/Field'
import PhoneFold from '../components/PhoneFold'
import { Row, Rows, ShowAll } from '../components/patterns'
import { counted, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import './academics/academics.css'

export default function OlympiadGroup() {
  const [query, setQuery] = useState('')
  const [group, setGroup] = useState('')
  const [onlyMembers, setOnlyMembers] = useState(false)

  const list = useOlympiadGroup({ q: query, group, member: onlyMembers ? 'true' : undefined })
  const members = useOlympiadGroup({ member: 'true' })
  const pick = usePickForGroup()

  if (list.isLoading) return <Loading kind="table" />
  if (list.isError) return <ErrorNote error={list.error} />

  const rows = list.data?.students ?? []
  const inGroup = members.data?.students ?? []
  const filtered = Boolean(query || group || onlyMembers)
  const toggle = (row: GroupRow) =>
    pick.mutate(
      { student: row.id, member: !row.in_group },
      { onSuccess: (answer) => toast.success(answer.detail), onError: (error) => toast.error(error.message) },
    )

  const columns: Column<GroupRow>[] = [
    { key: 'name', title: t('Ученик'), width: '40%', cell: (row) => <b>{row.full_name}</b>, sortBy: (row) => row.full_name },
    { key: 'group', title: t('Группа'), width: '16%', cell: (row) => row.group || <span className="t-note">{t('без группы')}</span>, sortBy: (row) => row.group },
    {
      key: 'materials',
      title: t('Материалов'),
      width: '20%',
      align: 'right',
      cell: (row) => (row.materials === 0 ? <span className="t-note">{t('нет')}</span> : <span className="num">{counted(row.materials, ['материал', 'материала', 'материалов'])}</span>),
      sortBy: (row) => row.materials,
    },
    {
      key: 'pick',
      title: '',
      width: '24%',
      align: 'right',
      cell: (row) => (
        <Button variant={row.in_group ? 'outline' : 'secondary'} size="sm" disabled={pick.isPending} onClick={() => toggle(row)}>
          {row.in_group ? t('Снять из группы') : t('Отметить')}
        </Button>
      ),
      sortBy: (row) => (row.in_group ? 0 : 1),
    },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Олимпиадная группа')}
        pills={list.data?.detail ? [{ label: list.data.detail }] : undefined}
      />

      <div className="acad__cols">
        <div className="acad__stack">
          <PhoneFold active={filtered}>
            <div className="acad__toolbar">
              <Field name="q" label={t('Поиск')} value={query} placeholder={t('Фамилия или имя')} onChange={setQuery} />
              {/* школа ведёт только выпускников: делим по группам, класса в фильтре нет */}
              <Field kind="select" name="group" label={t('Группа')} value={group} onChange={setGroup} options={[{ value: '', title: t('все группы') }, ...(list.data?.groups ?? []).map((code) => ({ value: code, title: code }))]} />
              <Field kind="checkbox" name="members" label={t('только те, кто в группе')} checked={onlyMembers} onChange={setOnlyMembers} />
            </div>
          </PhoneFold>
          <DataCard
            title={t('Ученики')}
            count={rows.length || undefined}
            empty={rows.length === 0 && (filtered ? t('никого не нашлось — снимите фильтры') : t('учеников ещё нет — карточки заводит администратор'))}
            emptyAction={
              filtered ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setQuery('')
                    setGroup('')
                    setOnlyMembers(false)
                  }}
                >
                  {t('Снять фильтры')}
                </Button>
              ) : undefined
            }
          >
            <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} />
          </DataCard>
        </div>
        <div className="acad__stack">
          <DataCard title={t('Кто в группе')} count={inGroup.length || undefined} empty={inGroup.length === 0 && t('пока никого — отметьте первого')}>
            <Rows>
              <ShowAll>
                {inGroup.map((row) => (
                  <Row key={row.id} avatar={row.full_name} title={row.full_name} note={[row.group, row.materials ? counted(row.materials, ['материал', 'материала', 'материалов']) : ''].filter(Boolean).join(' · ')} to={`/students/${row.id}`} />
                ))}
              </ShowAll>
            </Rows>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
