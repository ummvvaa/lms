/**
 * Риски — экран директора школы и администратора: кто просел
 * по посещаемости и домашним.
 *
 * Посещаемость считается по урокам (`acad-risks`): «у» снижает процент,
 * в риск идут только «н», «день без причины» — не меньше двух «н» и 60 %
 * уроков дня; пороги — в настройках. Прежние отметки дня здесь не считаются
 * (D65). Домашние работы — из профиля, как раньше. Эти ярлыки видны только
 * сотрудникам.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAcadRisks, type RiskRow } from '../../api/academics'
import { useDashboard } from '../../api/hooks'
import DataTable, { type Column } from '../../components/DataTable'
import { Row, Rows, ShowAll, StatRow } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { dateWords, NoteCard, PeriodSwitch } from '../academics/shared'
import '../academics/academics.css'
import type { BehaviorData } from './data'

export default function Risks() {
  const navigate = useNavigate()
  const [period, setPeriod] = useState('')
  const risks = useAcadRisks({ period })
  const behavior = useDashboard<BehaviorData>('behavior')
  if ((risks.isLoading && !risks.data) || behavior.isLoading) return <Loading kind="table" />
  if (risks.error) return <ErrorNote error={risks.error} />
  if (behavior.error) return <ErrorNote error={behavior.error} />
  if (!risks.data) return null

  const data = risks.data
  const traffic = behavior.data?.traffic ?? {}
  const below = data.rows.filter((row) => row.attendance.pct !== null && row.attendance.pct < data.threshold)
  const unexcused = data.rows.reduce((sum, row) => sum + row.unexcused_days.length, 0)
  const homework = behavior.data?.worst_homework ?? []

  const columns: Column<RiskRow>[] = [
    {
      key: 'student',
      title: t('Ученик'),
      width: '30%',
      cell: (row) => (
        <>
          <b>{row.full_name}</b>
          <span className="t-note"> · {row.group}</span>
        </>
      ),
      sortBy: (row) => row.full_name,
    },
    {
      key: 'pct',
      title: t('Посещаемость'),
      width: '16%',
      align: 'right',
      cell: (row) =>
        row.attendance.pct === null ? (
          <span className="t-note">{t('нет отметок')}</span>
        ) : (
          <Chip tone={row.attendance.pct < data.threshold ? 'bad' : 'warn'} size="sm" className="num">
            {row.attendance.pct} %
          </Chip>
        ),
      sortBy: (row) => row.attendance.pct ?? 101,
    },
    { key: 'absent', title: t('«н»'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.attendance.absent || t('нет')}</span>, sortBy: (row) => row.attendance.absent },
    { key: 'excused', title: t('«у»'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.attendance.excused || t('нет')}</span>, sortBy: (row) => row.attendance.excused },
    {
      key: 'days',
      title: t('Дни без причины'),
      width: '22%',
      cell: (row) => (row.unexcused_days.length === 0 ? <span className="t-note">{t('нет')}</span> : row.unexcused_days.map(dateWords).join(', ')),
      sortBy: (row) => row.unexcused_days.length,
    },
    {
      key: 'open',
      title: '',
      width: '12%',
      align: 'right',
      cell: (row) => (
        <Button
          variant="secondary"
          size="sm"
          onClick={() => navigate(`/attendance?group=${encodeURIComponent(row.group)}${row.unexcused_days.length ? `&date=${row.unexcused_days[row.unexcused_days.length - 1]}` : ''}`)}
        >
          {t('Посещаемость')}
        </Button>
      ),
    },
  ]

  return (
    <div>
      <ScreenHead title={t('Риски')} subtitle={t('Кому нужен контроль прямо сейчас. Эти ярлыки видны только сотрудникам.')} />
      <div className="acad__toolbar">
        <PeriodSwitch value={period || data.periods.find((row) => row.title === data.period.title)?.code || ''} periods={data.periods} onChange={setPeriod} />
        <span className="t-note">{`${dateWords(data.period.from)} — ${dateWords(data.period.to)}`}</span>
      </div>

      <StatRow>
        <Kpi value={traffic.critical || null} none={t('нет')} label={t('Ежедневный контроль')} tone="bad" to="/table?status=critical" />
        <Kpi value={traffic.needs_supervision || null} none={t('нет')} label={t('Нужен контроль')} tone="warn" to="/table?status=needs_supervision" />
        <Kpi value={below.length || null} none={t('нет')} label={t('Ниже порога посещаемости')} note={`${t('порог')} ${data.threshold} %`} tone="bad" />
        <Kpi value={unexcused || null} none={t('нет')} label={t('Дней без причины')} note={data.period.title} tone="warn" />
      </StatRow>

      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard title={t('Посещаемость по урокам')} count={data.rows.length || undefined} empty={data.rows.length === 0 && t('за период никто не ниже порога и дней без причины нет')}>
            <DataTable columns={columns} rows={data.rows} rowKey={(row) => row.id} limit={20} />
          </DataCard>
        </div>
        <div className="acad__stack">
          <NoteCard title={t('Что делать')}>
            {`${t('«у» снижает процент, но в риск не входит; в риск идут только «н». День без причины — не меньше двух «н» и 60 % уроков дня.')} ${t('Уважительную причину за период оформляет куратор на экране посещаемости; звонок родителям — по правилам обзвона.')}`}
          </NoteCard>
          <DataCard title={t('Худшие домашние работы')} count={homework.length || undefined} empty={homework.length === 0 && t('по домашним работам данных нет')}>
            <Rows>
              <ShowAll>
                {homework.map((row) => (
                  <Row
                    key={row.student_id}
                    avatar={`${row.student__last_name} ${row.student__first_name}`}
                    title={`${row.student__last_name} ${row.student__first_name}`}
                    right={
                      <Chip tone="warn" size="sm" className="num">
                        {row.homework_percent}%
                      </Chip>
                    }
                    to={`/students/${row.student_id}`}
                  />
                ))}
              </ShowAll>
            </Rows>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
