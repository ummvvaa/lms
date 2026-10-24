/**
 * «Родители» — директор школы (макет BParents, 24.10.2026).
 *
 * Вкладки: «Позвонить сегодня» — список по включённым правилам обзвона,
 * итог звонка (дозвонились, не ответили, перезвонить и текст) пишется
 * в карточку ученика; «Контакты»; «История звонков» — её же ведут кураторы;
 * «Правила обзвона» — включить или выключить правило, правка — на своём экране.
 */
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { useNavigate } from 'react-router'
import { downloadFile } from '../../api/client'
import { useCalls, useCallsToday, type CallRow, type CallTodayRow } from '../../api/directors'
import { useCallRuleDirectory, useContacts, type ParentContact } from '../../api/hooks'
import DataTable, { type Column } from '../../components/DataTable'
import Field from '../../components/Field'
import { Avatar } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead, ScreenTabs } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { formatDateTime, formatDayMonthShort } from '../../lib/format'
import { usePhone } from '../../phone'
import { CallDialog, OUTCOME_TONE, todayLine } from './parts'

type Tab = 'today' | 'contacts' | 'history' | 'rules'
type Calling = { id: number; name: string; note: string; contact: number | null; rule?: string }

export default function Parents() {
  const phone = usePhone()
  const navigate = useNavigate()
  const today = useCallsToday()
  const history = useCalls(30)
  const [tab, setTab] = useState<Tab>('today')
  const [search, setSearch] = useState('')
  const contacts = useContacts({ search })
  const rules = useCallRuleDirectory()
  const [calling, setCalling] = useState<Calling | null>(null)

  const lastCall = useMemo(() => {
    const out = new Map<number, CallRow>()
    for (const row of history.data?.rows ?? []) if (!out.has(row.student.id)) out.set(row.student.id, row)
    return out
  }, [history.data])

  if (today.isLoading && !today.data) return <Loading kind="table" />
  if (today.error) return <ErrorNote error={today.error} />
  if (!today.data) return null

  const rows = today.data.rows
  const left = rows.filter((row) => !row.today)
  const week = today.data.week

  const todayColumns: Column<CallTodayRow>[] = [
    {
      key: 'student',
      title: t('Ученик'),
      width: 'auto',
      phone: 'head',
      cell: (row) => (
        <span className="personcell">
          <Avatar name={row.student} />
          <span className="personcell__text">
            <b>{row.student}</b>
            <span className="t-note">{[row.group, row.parent].filter(Boolean).join(' · ')}</span>
          </span>
        </span>
      ),
    },
    { key: 'why', title: t('Причина'), width: 'auto', cell: (row) => row.reason },
    { key: 'phone', title: t('Телефон'), width: '160px', cell: (row) => (row.contact?.phone ? <a href={`tel:${row.contact.phone}`}>{row.contact.phone}</a> : t('нет телефона')) },
    {
      key: 'state',
      title: t('Статус'),
      width: '140px',
      cell: (row) =>
        row.today ? (
          <Chip tone={OUTCOME_TONE[row.today.outcome]} size="sm">
            {row.today.outcome_title}
          </Chip>
        ) : (
          <Chip tone="accent" size="sm">
            {t('ждёт звонка')}
          </Chip>
        ),
    },
    {
      key: 'acts',
      title: '',
      width: '140px',
      actions: true,
      cell: (row) => (
        <Button
          variant="outline"
          size="sm"
          onClick={() => setCalling({ id: row.student_id, name: row.student, note: [row.parent, row.contact?.phone].filter(Boolean).join(' · '), contact: row.contact_id })}
        >
          {t('Итог звонка')}
        </Button>
      ),
    },
  ]

  const contactColumns: Column<ParentContact>[] = [
    { key: 'student', title: t('Ученик'), width: 'auto', phone: 'head', cell: (row) => <b>{row.student_name}</b> },
    { key: 'group', title: t('Группа'), width: '110px', cell: (row) => row.student_group || t('без группы') },
    {
      key: 'parent',
      title: t('Родитель'),
      width: 'auto',
      cell: (row) => (
        <>
          {row.full_name}
          <span className="t-note">{` · ${row.relation_title}`}</span>
        </>
      ),
    },
    { key: 'phone', title: t('Телефон'), width: '160px', cell: (row) => (row.phone ? <a href={`tel:${row.phone}`}>{row.phone}</a> : t('нет телефона')) },
    {
      key: 'last',
      title: t('Последний звонок'),
      width: '150px',
      cell: (row) => {
        const last = lastCall.get(row.student)
        return last ? `${formatDayMonthShort(last.at)} · ${last.outcome_title.toLocaleLowerCase()}` : t('не звонили')
      },
    },
    {
      key: 'acts',
      title: '',
      width: '140px',
      actions: true,
      cell: (row) => (
        <Button variant="outline" size="sm" onClick={() => setCalling({ id: row.student, name: row.student_name, note: [row.full_name, row.phone].filter(Boolean).join(' · '), contact: row.id })}>
          {t('Итог звонка')}
        </Button>
      ),
    },
  ]

  const historyColumns: Column<CallRow>[] = [
    { key: 'when', title: t('Когда'), width: '150px', cell: (row) => formatDateTime(row.at), sortBy: (row) => row.at },
    {
      key: 'student',
      title: t('Ученик'),
      width: 'auto',
      phone: 'head',
      cell: (row) => (
        <>
          <b>{row.student.short_name}</b>
          <span className="t-note">{` · ${row.student.group}`}</span>
        </>
      ),
    },
    { key: 'who', title: t('Кто звонил'), width: 'auto', cell: (row) => row.by },
    { key: 'res', title: t('Итог'), width: '140px', cell: (row) => <Chip tone={OUTCOME_TONE[row.outcome]} size="sm">{row.outcome_title}</Chip> },
    { key: 'note', title: t('Комментарий'), width: 'auto', cell: (row) => row.note || t('без записи') },
  ]

  const ruleRows = rules.query.data?.results ?? []
  const counts = new Map<string, number>()
  for (const row of rows) counts.set(row.reason, (counts.get(row.reason) ?? 0) + 1)

  return (
    <div className="lay-screen">
      <ScreenHead title={t('Родители')} subtitle={todayLine(t('итоги звонков записываются в карточку ученика'))} />
      <div className="lay-4">
        <Kpi label={t('Позвонить сегодня')} value={left.length} note={t('по правилам обзвона')} />
        <Kpi label={t('Звонков за неделю')} value={week.total} note={t('вы и кураторы')} />
        <Kpi label={t('Дозвонились')} value={week.reached} note={t('за неделю')} />
        <Kpi label={t('Перезвонить')} value={week.later} note={t('не ответили или просили позже')} />
      </div>
      <ScreenTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'today' as const, label: <>{t('Позвонить сегодня')} <span className="tabs__n num">{left.length}</span></> },
          { value: 'contacts' as const, label: t('Контакты') },
          { value: 'history' as const, label: <>{t('История звонков')} <span className="tabs__n num">{history.data?.total ?? 0}</span></> },
          { value: 'rules' as const, label: t('Правила обзвона') },
        ]}
      />
      {tab === 'today' && (
        <DataCard className={rows.length ? 'card--beam' : undefined} title={t('Позвонить сегодня')} note={t('по включённым правилам')} count={rows.length || undefined} empty={rows.length === 0 && t('по правилам обзвона звонить сегодня некому')}>
          <DataTable columns={todayColumns} rows={rows} rowKey={(row) => row.student_id} limit={5} fit={!phone} />
        </DataCard>
      )}
      {tab === 'contacts' && (
        <DataCard title={t('Контакты родителей')} count={contacts.data?.count}>
          <div className="filters">
            <Field usageFilter className="filters__search" name="q" label={t('Поиск')} value={search} placeholder={t('Фамилия ученика')} onChange={setSearch} />
          </div>
          <DataTable columns={contactColumns} rows={contacts.data?.results ?? []} rowKey={(row) => row.id} limit={5} fit={!phone} empty={t('Никого с такой фамилией')} />
        </DataCard>
      )}
      {tab === 'history' && (
        <DataCard
          title={t('История звонков')}
          note={t('за 30 дней · вы и кураторы')}
          count={history.data?.total}
          empty={(history.data?.rows.length ?? 0) === 0 && t('звонков за 30 дней не было')}
          right={
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                downloadFile('/directors/calls/export/', t('Звонки родителям.xlsx'))
                  .then(() => toast.success(t('Файл xlsx скачан')))
                  .catch((reason: unknown) => toast.error(reason instanceof Error ? reason.message : String(reason)))
              }
            >
              {t('Выгрузить xlsx')}
            </Button>
          }
        >
          <DataTable columns={historyColumns} rows={history.data?.rows ?? []} rowKey={(row) => row.id} limit={5} fit={!phone} />
        </DataCard>
      )}
      {tab === 'rules' && (
        <DataCard
          title={t('Правила обзвона')}
          note={t('из них собирается «Позвонить сегодня»')}
          count={ruleRows.length || undefined}
          empty={ruleRows.length === 0 && t('правил пока нет')}
          right={
            <Button variant="outline" size="sm" onClick={() => navigate('/call-rules')}>
              {t('Изменить правила')}
            </Button>
          }
        >
          <div className="dir__rows">
            {ruleRows.map((rule) => (
              <div key={rule.id} className="dir__row">
                <span className="dir__what">
                  <b>{rule.reason}</b>
                  <span className="t-note">{`${rule.condition_title} · ${t('сегодня: {n}', { n: counts.get(rule.reason) ?? 0 })}`}</span>
                </span>
                <Chip tone={rule.is_active ? 'good' : 'neutral'} size="sm">
                  {rule.is_active ? t('включено') : t('выключено')}
                </Chip>
                <span className="dir__acts">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={rules.update.isPending}
                    onClick={() => rules.update.mutate({ id: rule.id, is_active: !rule.is_active }, { onSuccess: () => void today.refetch() })}
                  >
                    {rule.is_active ? t('Выключить') : t('Включить')}
                  </Button>
                </span>
              </div>
            ))}
          </div>
        </DataCard>
      )}
      {calling && <CallDialog student={calling.id} name={calling.name} note={calling.note} contact={calling.contact} rule={calling.rule} onClose={() => setCalling(null)} />}
    </div>
  )
}
