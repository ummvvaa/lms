/**
 * Граница кабинета куратора: экраны рисуются только по назначенным группам (фаза 80).
 *
 * Группы куратора — его действующие назначения, и больше ничего. Пока они
 * не пришли, экраны кабинета не рисуются: выбор группы, запомненный вкладкой,
 * ещё не с чем сверить, и запрос с чужим кодом уйти не должен. Назначений
 * нет — кабинет показывает одно пустое состояние вместо карточек с нулями:
 * меню работает, профиль открывается, чужих данных нет.
 */
import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { useCuratorProfile } from '../../api/hooks'
import Empty from '../../components/Empty'
import { ErrorNote, Loading } from '../../components/ui'
import { t } from '../../i18n'

/** Профиль не про группы: он открыт и куратору без назначений. */
const WITHOUT_GROUPS = ['/profile']

export default function CuratorCabinet({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const { data, error } = useCuratorProfile()

  if (WITHOUT_GROUPS.includes(pathname)) return <>{children}</>
  if (error) return <ErrorNote error={error} />
  if (!data) return <Loading kind="cards" />
  if (data.groups.length === 0)
    return (
      <Empty
        icon="people"
        title={t('Вам не назначены группы')}
        what={t('Обратитесь к администратору: группы куратору назначает он.')}
      />
    )
  return <>{children}</>
}
