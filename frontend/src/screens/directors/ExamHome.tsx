/**
 * Главная академического директора (макет EHome, 24.10.2026): отчёты недели,
 * успеваемость по параллелям, задачи сотрудникам с просрочкой и кто сегодня
 * вне уроков. Числа — из тех же отчётов, что на экране «Отчёты».
 */
import { useState } from 'react'
import { todayAlmaty } from '../../lib/dates'
import { toast } from 'sonner'
import { useNavigate } from 'react-router'
import {
  useReleases,
  useSchoolReports,
  useStaffTaskAction,
  useStaffTasks,
  type SchoolReport,
} from '../../api/directors'
import { Avatar, ShowAll } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import PendingQueue from '../../components/PendingQueue'
import { Button } from '../../components/ui/button'
import { t, tn } from '../../i18n'
import { formatDayMonth } from '../../lib/format'
import { ReportDialog, ReportLine, todayLine, useGreeting } from './parts'
import { StaffTaskDialog } from './StaffTasks'

export default function ExamHome() {
  const navigate = useNavigate()
  const greeting = useGreeting()
  const reports = useSchoolReports()
  const tasks = useStaffTasks()
  const remind = useStaffTaskAction()
  const today = todayAlmaty()
  const released = useReleases(today, today)
  const [opened, setOpened] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  if (reports.isLoading || tasks.isLoading) return <Loading kind="cards" />
  if (reports.error) return <ErrorNote error={reports.error} />

  const current = reports.data?.current ?? []
  const of = (kind: string): SchoolReport | undefined => current.find((row) => row.kind === kind)
  const grades = of('grades_parallels')?.figures as { fo: number | null; below: number; parallels: { parallel: number; fo: number; below: number }[] } | undefined
  const teachers = of('teachers')?.figures as { lessons: number; homework: number; teachers: number } | undefined
  const mock = of('mock')?.figures as { took: number; date: string | null } | undefined
  const open = (tasks.data?.rows ?? []).filter((task) => task.status === 'open' || task.status === 'returned')
  const late = open.filter((task) => task.late)
  const away = (released.data?.rows ?? []).flatMap((row) => row.students.map((student) => ({ student, row })))

  return (
    <div className="lay-screen">
      <ScreenHead
        title={greeting}
        subtitle={todayLine(t('отчёты, результаты и задачи сотрудникам'))}
        actions={
          <>
            <Button variant="outline" onClick={() => navigate('/school-reports')}>
              {t('Все отчёты')}
            </Button>
            <Button onClick={() => setCreating(true)}>{t('Новая задача')}</Button>
          </>
        }
      />
      <div className="lay-4">
        <Kpi label={t('Средний ФО по школе за неделю')} value={grades?.fo != null ? `${grades.fo} %` : null} note={of('grades_parallels')?.source} to="/school-reports" />
        <Kpi label={t('Неотмеченных уроков')} value={teachers?.lessons ?? null} note={teachers ? t('у {n} учителей за неделю', { n: teachers.teachers }) : undefined} to="/school-reports" />
        <Kpi label={t('Mock Test')} value={mock?.took ?? null} note={mock?.date ? t('сдавали {date} · IELTS и SAT', { date: formatDayMonth(mock.date) }) : undefined} to="/exam-results" />
        <Kpi
          label={t('Задач сотрудникам открыто')}
          value={open.length}
          chip={late.length ? { label: t('просрочено {n}', { n: late.length }), tone: 'bad' } : undefined}
          to="/staff-tasks"
        />
      </div>
      {/* что внесли ученики — решение прямо в строке: раздела «Предложения» нет (24.10.2026) */}
      <PendingQueue fold />
      <div className="lay-main lay-main--even">
        <div className="lay-stack">
          <DataCard
            className="card--beam"
            title={t('Отчёты за неделю')}
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
          </DataCard>
          <DataCard
            title={t('Задачи сотрудникам: просрочено')}
            count={late.length || undefined}
            empty={late.length === 0 && t('просроченных задач нет')}
            right={
              <Button variant="link" size="sm" onClick={() => navigate('/staff-tasks')}>
                {t('Все')}
              </Button>
            }
          >
            <div className="dir__rows">
              <ShowAll>
                {late.map((task) => (
                  <div key={task.id} className="dir__row">
                    <span className="dir__what">
                      <b>{task.title}</b>
                      <span className="t-note">{`${task.assignee.name} · ${task.assignee.role_title}`}</span>
                    </span>
                    <Chip tone="bad" size="sm">
                      {tn(task.days_late, 'просрочено {n} день|просрочено {n} дня|просрочено {n} дней')}
                    </Chip>
                    <span className="dir__acts">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={remind.isPending}
                        onClick={() => remind.mutate({ id: task.id, action: 'remind' }, { onSuccess: () => toast.success(t('Напоминание отправлено — {name}', { name: task.assignee.name })) })}
                      >
                        {t('Напомнить')}
                      </Button>
                    </span>
                  </div>
                ))}
              </ShowAll>
            </div>
          </DataCard>
        </div>
        <div className="lay-stack">
          <DataCard title={t('Успеваемость по параллелям · ФО')} note={of('grades_parallels')?.period_title} empty={!grades?.parallels.length && t('оценок за неделю ещё нет')}>
            <div className="dir__bars">
              {(grades?.parallels ?? []).map((row) => (
                <div key={row.parallel} className="dir__bar">
                  <span>{t('{n} параллель', { n: row.parallel })}</span>
                  <Bar percent={row.fo} />
                  <b className="num">{`${row.fo} %`}</b>
                </div>
              ))}
            </div>
            {grades && grades.below > 0 && (
              <span className="t-note">{tn(grades.below, '{n} ученик ниже 60 %|{n} ученика ниже 60 %|{n} учеников ниже 60 %')}</span>
            )}
          </DataCard>
          <DataCard
            title={t('Сегодня вне уроков')}
            count={away.length || undefined}
            empty={away.length === 0 && t('сегодня все на уроках')}
            right={
              <Button variant="link" size="sm" onClick={() => navigate('/schedule')}>
                {t('Расписание')}
              </Button>
            }
          >
            <div className="dir__rows">
              <ShowAll>
                {away.map(({ student, row }) => (
                  <div key={`${row.id}-${student.id}`} className="dir__row">
                    <Avatar name={student.full_name} />
                    <span className="dir__what">
                      <b>{student.short_name}</b>
                      <span className="t-note">{`${student.group} · ${row.reason}`}</span>
                    </span>
                    <Chip tone="info" size="sm">
                      {row.all_day ? t('весь день') : t('уроки {a}–{b}', { a: row.slot_from ?? '', b: row.slot_to ?? '' })}
                    </Chip>
                    <span />
                  </div>
                ))}
              </ShowAll>
            </div>
          </DataCard>
        </div>
      </div>
      {opened && <ReportDialog kind={opened} onClose={() => setOpened(null)} />}
      {creating && <StaffTaskDialog onClose={() => setCreating(false)} />}
    </div>
  )
}
