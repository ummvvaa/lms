/**
 * Раздел на пустой школе.
 *
 * Ни один экран не показывает пустую таблицу и белое поле: пока учеников
 * нет, раздел объясняет, что здесь появится и с чего начать.
 *
 * Текст обязателен и у каждого раздела свой. Один и тот же текст на трёх
 * страницах подряд читается как одна и та же страница — человек решает,
 * что меню сломано, а не что данных ещё нет.
 *
 * Панель «Начало работы» показывается только на дашборде: на остальных
 * разделах она занимала пол-экрана и повторялась на каждом переходе.
 */
import { useGettingStarted } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import Empty from './Empty'
import GettingStarted from './GettingStarted'
import { ScreenHead } from './ui'
import { t } from '../i18n'

/** В школе ещё нет ни одного ученика — считает сервер, а не экран. */
export function useSchoolIsEmpty(): boolean {
  const { data } = useGettingStarted()
  const step = data?.steps.find((s) => s.code === 'students')
  return step !== undefined && !step.done
}

export default function EmptyDashboard({
  title,
  hint,
  what,
  detail,
  action,
  to,
  guide = false,
}: {
  title: string
  /** заголовок пустого состояния: что именно появится здесь */
  hint: string
  /** одна фраза о том, из чего это соберётся */
  what: string
  /** подробности — по наведению, а не абзацем на экране */
  detail?: string
  action?: string
  to?: string
  /** панель «Начало работы» — только на дашборде */
  guide?: boolean
}) {
  const { me } = useAuth()
  // учеников заводит администратор списком (фаза 35): его кнопка ведёт
  // к пользователям, директору предлагать загрузку файла больше нечего —
  // у него открывается таблица, куда он вставит кусок своей
  const fallback =
    me?.role === 'admin'
      ? { action: 'Завести учеников', to: '/users' }
      : { action: 'Открыть таблицу', to: '/table' }
  return (
    <div>
      <ScreenHead title={title} subtitle={t('Пока в школе нет ни одного ученика.')} />
      {guide && <GettingStarted />}
      <Empty
        icon="dashboard"
        title={hint}
        what={what}
        hint={detail}
        action={t(action ?? fallback.action)}
        to={to ?? fallback.to}
      />
    </div>
  )
}
