/**
 * Журнал куратора (фаза 62): действия по его группам — свои, Кымбат, Асем,
 * Салтанат. Читается из общего журнала правок по снимку группы (фаза 60):
 * ученик, переведённый в другую группу, не уносит с собой чужую историю.
 * Не редактируется; выгружается тем же кодом XLSX.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCuratorJournal, type JournalRow } from '../../api/hooks'
import DataTable, { type Column } from '../../components/DataTable'
import { ExportPreview } from '../../components/ExportPreview'
import { ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import GroupSwitch from './GroupSwitch'
import { useGroup } from './state'
import './curator.css'

export default function CuratorJournal() {
  const navigate = useNavigate()
  const [group, setGroup] = useGroup()
  const { data, isLoading, error } = useCuratorJournal(group)
  const [exporting, setExporting] = useState(false)

  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const exportPath = `/curator/journal/export/${group !== 'all' ? `?group=${encodeURIComponent(group)}` : ''}`

  const columns: Column<JournalRow>[] = [
    { key: 'at', title: t('Когда'), width: '14%', cell: (row) => <span className="squeue__when num">{new Date(row.at).toLocaleString('ru')}</span>, sortBy: (row) => row.at },
    {
      key: 'who',
      title: t('Кто'),
      width: '16%',
      cell: (row) => (
        <>
          {row.who}
          {row.role && <span className="t-note"> · {row.role}</span>}
        </>
      ),
      sortBy: (row) => row.who,
    },
    {
      key: 'student',
      title: t('Ученик'),
      width: '20%',
      cell: (row) => (
        <>
          {row.student_id ? (
            <Button variant="link" size="sm" onClick={() => navigate(`/students/${row.student_id}`)}>
              {row.student}
            </Button>
          ) : (
            row.student
          )}
          {row.group && <span className="t-note"> · {row.group}</span>}
        </>
      ),
      sortBy: (row) => row.student,
    },
    { key: 'what', title: t('Что'), width: '22%', cell: (row) => row.what },
    {
      key: 'now',
      title: t('Стало'),
      width: '28%',
      cell: (row) => (
        <>
          {row.was && <span className="t-note">{row.was} → </span>}
          {row.now}
        </>
      ),
    },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Журнал')}
        actions={
          <Button variant="outline" size="sm" onClick={() => setExporting(true)}>
            {t('Выгрузить')}
          </Button>
        }
      />
      <GroupSwitch groups={data.groups} value={group} onChange={setGroup} />

      <div className="card">
        <DataTable columns={columns} rows={data.results} rowKey={(row) => row.id} limit={50} empty={<span className="t-note">{t('Пока ничего не менялось')}</span>} />
      </div>

      {exporting && (
        <ExportPreview
          path={exportPath}
          fallback="journal.xlsx"
          title={t('Выгрузка журнала')}
          onClose={() => setExporting(false)}
        />
      )}
    </div>
  )
}
