/**
 * Блок «Учёба» на дашборде Кымбат и администратора: уроки сегодня,
 * не отмечено, замены, накладки на следующей неделе, просьбы, отчёты.
 */
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useAcadDashboard, useRemindAllTeachers } from '../../api/academics'
import { Row, Rows } from '../../components/patterns'
import { counted, DataCard } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'

export function useAcademicsCard() {
  const navigate = useNavigate()
  const remind = useRemindAllTeachers()
  const { data } = useAcadDashboard()
  if (!data) return null
  if (data.empty)
    return {
      key: 'academics',
      column: 'aside' as const,
      rows: 1,
      folded: true,
      node: <DataCard title={t('Учёба')} empty={t('расписание ещё не составлено')} emptyAction={<Button variant="secondary" size="sm" onClick={() => navigate('/schedule')}>{t('Составить')}</Button>} />,
    }
  return {
    key: 'academics',
    column: 'aside' as const,
    rows: 6,
    node: (
      <DataCard title={t('Учёба')} right={<Button variant="link" size="sm" onClick={() => navigate('/schedule')}>{t('Расписание')}</Button>}>
        <Rows>
          <Row icon="calendar" tone="accent" title={`${t('Сегодня')} ${counted(data.lessons_today ?? 0, ['урок', 'урока', 'уроков'])}`} note={data.now_slot ? `${t('идёт')} ${data.now_slot} ${t('урок')}` : t('уроки закончились')} to="/schedule" />
          <Row
            icon="alert"
            tone={data.unmarked ? 'warn' : 'good'}
            title={data.unmarked ? `${t('Не отмечено')} ${counted(data.unmarked, ['урок', 'урока', 'уроков'])}` : t('Все уроки недели отмечены')}
            note={data.unmarked ? (data.unmarked_teachers ?? []).join(', ') : t('учителя отмечают вовремя')}
            acts={data.unmarked ? <Button variant="secondary" size="sm" onClick={() => remind.mutate(undefined, { onSuccess: (r) => toast.success(`${t('Напоминания ушли:')} ${counted(r.teachers, ['учитель', 'учителя', 'учителей'])}`), onError: (e) => toast.error(e.message) })}>{t('Напомнить')}</Button> : undefined}
          />
          <Row icon="refresh" tone="info" title={`${t('Замены и отмены:')} ${data.changes ?? 0}`} note={t('на этой неделе')} to="/schedule" />
          {data.next_conflicts ? <Row icon="alert" tone="bad" title={`${t('Накладка на следующей неделе:')} ${data.next_conflicts}`} note={data.next_conflict_text ?? ''} to="/schedule" /> : null}
          {data.requests ? <Row icon="bell" tone="warn" title={`${t('Просьбы учителей:')} ${data.requests}`} note={data.request_text ?? ''} to="/schedule" /> : null}
          {data.reports ? <Row icon="doc" title={`${t('Отчёты родителям за')} ${data.reports.title}: ${t('отправлено')} ${data.reports.sent} ${t('из')} ${data.reports.total}`} note={t('кураторы проверяют и отправляют')} to="/grades" /> : null}
        </Rows>
      </DataCard>
    ),
  }
}
