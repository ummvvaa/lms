/**
 * Вкладки «Секция · Мероприятия · Билеты» в «Спорте» ученика (макет StSections, 27.10.2026).
 *
 * У 8–10 — раздел «Спорт», у 11 — вкладка «Спорт» портфолио: внутри одни и те
 * же три вкладки. «Мероприятия» — прежнее содержимое раздела как было.
 * Вкладка живёт в адресе (`?sport=tickets`): уведомление о билете ведёт сразу туда.
 */
import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router'
import { ScreenTabs } from '../../components/ui'
import { t } from '../../i18n'
import StudentSection from './StudentSection'
import StudentTickets from './StudentTickets'

type SportTab = 'section' | 'events' | 'tickets'
const TABS: SportTab[] = ['section', 'events', 'tickets']

export default function SportTabs({ events }: { events: ReactNode }) {
  const [params, setParams] = useSearchParams()
  const raw = params.get('sport') ?? ''
  const tab: SportTab = TABS.includes(raw as SportTab) ? (raw as SportTab) : 'section'
  return (
    <>
      <ScreenTabs
        value={tab}
        onChange={(next) => {
          const query = new URLSearchParams(params)
          query.set('sport', next)
          setParams(query, { replace: true })
        }}
        items={[
          { value: 'section', label: t('Секция') },
          { value: 'events', label: t('Мероприятия') },
          { value: 'tickets', label: t('Билеты') },
        ]}
      />
      {tab === 'section' && <StudentSection />}
      {tab === 'events' && events}
      {tab === 'tickets' && <StudentTickets />}
    </>
  )
}
