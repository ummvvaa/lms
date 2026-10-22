/**
 * Журнал куратора (фаза 62): действия по его группам — свои, Кымбат, Асем,
 * Салтанат. Читается из общего журнала правок по снимку группы (фаза 60):
 * ученик, переведённый в другую группу, не уносит с собой чужую историю.
 * Не редактируется; выгружается тем же кодом XLSX.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useCuratorJournal, type JournalRow } from '../../api/hooks'
import DataTable, { type Column } from '../../components/DataTable'
import { ExportPreview } from '../../components/ExportPreview'
import { ShowAll } from '../../components/patterns'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { useAuth } from '../../auth/AuthContext'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import GroupSwitch from './GroupSwitch'
import { useGroup } from './state'
import { formatDateTime } from '../../lib/format'
import './curator.css'
import './curator-layout.css'

export default function CuratorJournal() {
  const navigate = useNavigate()
  const [group, setGroup] = useGroup()
  const { me } = useAuth()
  const { data, isLoading, error } = useCuratorJournal(group)
  const [exporting, setExporting] = useState(false)

  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const exportPath = `/curator/journal/export/${group !== 'all' ? `?group=${encodeURIComponent(group)}` : ''}`

  const columns: Column<JournalRow>[] = [
    { key: 'at', title: t('Когда'), width: '20%', cell: (row) => <span className="squeue__when num">{formatDateTime(row.at)}</span>, sortBy: (row) => row.at },
    {
      key: 'who',
      title: t('Кто'),
      width: '15%',
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
    { key: 'what', title: t('Что'), width: '20%', cell: (row) => row.what },
    {
      key: 'now',
      title: t('Стало'),
      width: '25%',
      cell: (row) => (
        <>
          {row.was && <span className="t-note">{row.was} → </span>}
          {row.now}
        </>
      ),
    },
  ]

  // сводка справа — из тех же строк, что в таблице: сколько записей, сколько ваших, кто менял
  const rows = data.results
  const mine = me ? rows.filter((row) => row.who === me.full_name).length : 0
  const byWho = [...rows.reduce((map, row) => map.set(row.who, (map.get(row.who) ?? 0) + 1), new Map<string, number>())].sort((a, b) => b[1] - a[1])
  const top = byWho[0]?.[1] ?? 0

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Журнал изменений')}
        subtitle={t('Кто, когда и что поменял по ученикам ваших групп')}
        actions={
          <Button variant="outline" size="sm" onClick={() => setExporting(true)}>
            {t('Выгрузить')}
          </Button>
        }
      />
      <GroupSwitch groups={data.groups} value={group} onChange={setGroup} />

      <div className="lay-main">
        <section className="card card-pad">
          <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} limit={50} empty={<span className="t-note">{t('Пока ничего не менялось')}</span>} />
        </section>
        <DataCard className={rows.length ? 'card--beam' : undefined} title={t('Сводка')} empty={rows.length === 0 && t('пока ничего не менялось')}>
          <div className="lay-2 clog__nums">
            <div className="clog__num">
              <span className="t-caps">{t('Записей')}</span>
              <b className="t-value num">{rows.length}</b>
            </div>
            <div className="clog__num">
              <span className="t-caps">{t('Ваших')}</span>
              <b className="t-value num">{mine}</b>
            </div>
          </div>
          <span className="t-caps clog__label">{t('Кто менял')}</span>
          <div className="clog__who">
            <ShowAll>
              {byWho.map(([who, count]) => (
                <div key={who} className="clog__whorow">
                  <span className="clog__whoname">{who}</span>
                  <span className="num t-note">{count}</span>
                  <span className="cstudents__bar" aria-hidden="true">
                    <i style={{ width: `${top ? Math.round((count / top) * 100) : 0}%` }} />
                  </span>
                </div>
              ))}
            </ShowAll>
          </div>
        </DataCard>
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
