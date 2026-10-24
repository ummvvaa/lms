/**
 * Главная директора школы (макет Main, 24.10.2026): все отчёты школы
 * приходят сюда. Четыре числа-ссылки — утренние отметки, обзвон, риски;
 * ниже отчёты за сегодня и «Позвонить сегодня» с итогом звонка.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useAcadRisks } from '../../api/academics'
import { useCallsToday, useMorning, useSchoolReports } from '../../api/directors'
import { Avatar } from '../../components/patterns'
import { DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import PendingQueue from '../../components/PendingQueue'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import {
  CallDialog,
  HomeColumns,
  MyStaffTasksCard,
  ReportDialog,
  ReportLine,
  todayLine,
  useGreeting,
} from './parts'

export default function SchoolHome() {
  const navigate = useNavigate()
  const greeting = useGreeting()
  const morning = useMorning()
  const calls = useCallsToday()
  const reports = useSchoolReports()
  const risks = useAcadRisks({ period: '' })
  const [opened, setOpened] = useState<string | null>(null)
  const [calling, setCalling] = useState<{
    id: number
    name: string
    note: string
    contact: number | null
  } | null>(null)

  if (morning.isLoading || reports.isLoading) return <Loading kind="cards" />
  if (morning.error) return <ErrorNote error={morning.error} />
  if (reports.error) return <ErrorNote error={reports.error} />

  const totals = morning.data?.totals
  const left = (calls.data?.rows ?? []).filter((row) => !row.today)
  const current = reports.data?.current ?? []
  const below = (risks.data?.rows ?? []).filter(
    (row) => row.attendance.pct !== null && row.attendance.pct < risks.data!.threshold,
  )

  return (
    <div className="lay-screen">
      <ScreenHead
        title={greeting}
        subtitle={todayLine(t('все отчёты школы приходят сюда'))}
        actions={<Button onClick={() => navigate('/school-reports')}>{t('Все отчёты')}</Button>}
      />
      {totals && (
        <div className="lay-4">
          <Kpi
            label={t('Нет в школе сегодня')}
            value={totals.absent}
            note={t('из {total} · опоздали {late}', { total: totals.students, late: totals.late })}
            to="/attendance"
          />
          <Kpi
            label={t('Утренних отметок')}
            value={t('{marked} из {total}', { marked: totals.marked, total: totals.groups })}
            note={t('группы кураторов')}
            to="/attendance"
          />
          <Kpi
            label={t('Позвонить родителям')}
            value={left.length}
            note={t('по правилам обзвона')}
            to="/parents"
          />
          <Kpi
            label={t('В зоне риска')}
            value={risks.data ? below.length : null}
            note={risks.data ? t('посещаемость ниже {n} %', { n: risks.data.threshold }) : undefined}
            to="/risks"
          />
        </div>
      )}
      <MyStaffTasksCard />
      {/* что внесли ученики — решение прямо в строке: раздела «Предложения» нет (24.10.2026) */}
      <PendingQueue fold hideEmpty />
      <HomeColumns
        main={[
          <DataCard
            className="card--beam"
            title={t('Отчёты за сегодня')}
            right={
              <Button variant="link" size="sm" onClick={() => navigate('/school-reports')}>
                {t('Все отчёты')}
              </Button>
            }
          >
            <div className="dir__rows">
              {current.map((report) => (
                <ReportLine key={report.kind} report={report} onOpen={() => setOpened(report.kind)} />
              ))}
            </div>
          </DataCard>,
        ]}
        aside={[
          left.length > 0 && (
            <DataCard
              title={t('Позвонить сегодня')}
              count={left.length || undefined}
              right={
                <Button variant="link" size="sm" onClick={() => navigate('/parents')}>
                  {t('Все')}
                </Button>
              }
            >
              <div className="dir__rows">
                {left.slice(0, 5).map((row) => (
                  <div key={row.student_id} className="dir__row">
                    <Avatar name={row.student} />
                    <span className="dir__what">
                      <b>{row.student}</b>
                      <span className="t-note dir__clamp">{`${row.group} · ${row.reason}`}</span>
                    </span>
                    <span />
                    <span className="dir__acts">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          setCalling({
                            id: row.student_id,
                            name: row.student,
                            note: [row.parent, row.contact?.phone].filter(Boolean).join(' · '),
                            contact: row.contact_id,
                          })
                        }
                      >
                        {t('Итог')}
                      </Button>
                    </span>
                  </div>
                ))}
              </div>
              {left.length > 5 && (
                <Button variant="link" size="sm" onClick={() => navigate('/parents')}>
                  {t('ещё {n}', { n: left.length - 5 })}
                </Button>
              )}
            </DataCard>
          ),
        ]}
      />
      {opened && <ReportDialog kind={opened} onClose={() => setOpened(null)} />}
      {calling && (
        <CallDialog
          student={calling.id}
          name={calling.name}
          note={calling.note}
          contact={calling.contact}
          onClose={() => setCalling(null)}
        />
      )}
    </div>
  )
}
