/**
 * Риски — экран директора школы и администратора: кто просел
 * по посещаемости и домашним.
 *
 * Посещаемость считается по урокам (`acad-risks`): «у» снижает процент,
 * в риск идут только «н», «день без причины» — не меньше двух «н» и 60 %
 * уроков дня; пороги — в настройках. Опоздания — отдельная причина, когда
 * школа включила правило «Опоздания в „Рисках“»: столько опозданий за
 * выбранный период. Причины строки и порог опозданий приходят с сервера.
 * Прежние отметки дня здесь не считаются (D65). Выполнение ДЗ за четверть считается из сдач в LMS: сдано вовремя
 * из заданий со сдачей, руками не вносится. Эти ярлыки видны только
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
import { t, tk, tn } from '../../i18n'
import { dateWords, PeriodSwitch } from '../academics/shared'
import '../academics/academics.css'
import type { BehaviorData } from './data'

/** Почему ученик в списке — словами; коды причин приходят с сервера. */
const REASON_WORDS: Record<RiskRow['reasons'][number], string> = {
  attendance: tk('посещаемость ниже порога'),
  unexcused: tk('дни без причины'),
  late: tk('опоздания'),
}

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
  const late = data.rows.filter((row) => row.reasons.includes('late'))
  const homework = behavior.data?.worst_homework ?? []

  const columns: Column<RiskRow>[] = [
    {
      key: 'student',
      title: t('Ученик'),
      width: 'auto',
      cell: (row) => (
        <>
          <b>{row.full_name}</b>
          <span className="t-note"> · {row.group}</span>
          <span className="t-note risks__why">{row.reasons.map((reason) => t(REASON_WORDS[reason])).join(' · ')}</span>
        </>
      ),
      sortBy: (row) => row.full_name,
    },
    {
      key: 'pct',
      title: t('Посещаемость'),
      width: '160px',
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
    { key: 'absent', title: t('«н»'), hint: t('Пропуски без причины'), width: '88px', align: 'right', cell: (row) => <span className="num">{row.attendance.absent || t('нет')}</span>, sortBy: (row) => row.attendance.absent },
    { key: 'excused', title: t('«у»'), hint: t('По уважительной'), width: '88px', align: 'right', cell: (row) => <span className="num">{row.attendance.excused || t('нет')}</span>, sortBy: (row) => row.attendance.excused },
    {
      key: 'late',
      title: t('«оп»'),
      hint: t('Опоздания'),
      width: '96px',
      align: 'right',
      cell: (row) =>
        row.reasons.includes('late') ? (
          <Chip tone="warn" size="sm" className="num">
            {row.attendance.late}
          </Chip>
        ) : (
          <span className="num">{row.attendance.late || t('нет')}</span>
        ),
      sortBy: (row) => row.attendance.late,
    },
    {
      key: 'days',
      title: t('Дни без причины'),
      width: '200px',
      cell: (row) => (row.unexcused_days.length === 0 ? <span className="t-note">{t('нет')}</span> : row.unexcused_days.map((day) => dateWords(day).replace(/ /g, '\u00a0')).join(', ')),
      sortBy: (row) => row.unexcused_days.length,
    },
    {
      key: 'open',
      title: '',
      width: '136px',
      actions: true,
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
      <ScreenHead title={t('Риски')} />
      <div className="acad__toolbar">
        <PeriodSwitch value={period || data.periods.find((row) => row.title === data.period.title)?.code || ''} periods={data.periods} onChange={setPeriod} />
        <span className="t-note">{`${dateWords(data.period.from)} — ${dateWords(data.period.to)}`}</span>
      </div>

      <StatRow>
        <Kpi value={traffic.critical || null} none={t('нет')} label={t('Ежедневный контроль')} tone="bad" to="/table?status=critical" />
        <Kpi value={traffic.needs_supervision || null} none={t('нет')} label={t('Нужен контроль')} tone="warn" to="/table?status=needs_supervision" />
        <Kpi value={below.length || null} none={t('нет')} label={t('Ниже порога посещаемости')} note={t('порог {threshold} %', { threshold: data.threshold })} tone="bad" />
        <Kpi value={unexcused || null} none={t('нет')} label={t('Дней без причины')} note={data.period.title} tone="warn" />
        {/* правило «Опоздания в „Рисках“» включено — причина видна числом, выключено — плитки нет */}
        {data.late_limit > 0 && (
          <Kpi
            value={late.length || null}
            none={t('нет')}
            label={t('Опаздывают')}
            note={tn(data.late_limit, 'от {n} опоздания за период|от {n} опозданий за период|от {n} опозданий за период')}
            tone="warn"
          />
        )}
      </StatRow>

      {/* таблица с причинами и тремя счётчиками отметок — на всю ширину: в двух третях
          страницы имя ученика сжималось до столбика букв, кнопка строки уезжала за край */}
      <div className="acad__stack">
        <DataCard title={t('Посещаемость по урокам')} count={data.rows.length || undefined} empty={
            data.rows.length === 0 &&
            (data.late_limit > 0
              ? t('за период никто не ниже порога, дней без причины и опозданий сверх порога нет')
              : t('за период никто не ниже порога и дней без причины нет'))
          }>
          <DataTable columns={columns} rows={data.rows} rowKey={(row) => row.id} limit={20} fit />
        </DataCard>
        <DataCard
          title={t('Выполнение ДЗ за четверть')}
          note={t('сдано вовремя из заданий со сдачей')}
          count={homework.length || undefined}
          empty={homework.length === 0 && t('заданий со сдачей за четверть ещё не было')}
        >
          <Rows>
            <ShowAll>
              {homework.map((row) => (
                <Row
                  key={row.student_id}
                  avatar={`${row.student__last_name} ${row.student__first_name}`}
                  title={`${row.student__last_name} ${row.student__first_name}`}
                  note={row.homework_total ? `${t('заданий со сдачей')}: ${row.homework_total}` : undefined}
                  right={
                    <Chip tone={(row.homework_percent ?? 0) < (behavior.data?.homework_behind_pct ?? 0) ? 'bad' : (row.homework_percent ?? 0) < 100 ? 'warn' : 'good'} size="sm" className="num">
                      {`${row.homework_percent ?? 0} %`}
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
  )
}
