/**
 * Дашборд на пустой школе.
 *
 * Ни один экран не показывает пустую таблицу и белое поле: пока учеников
 * нет, дашборд объясняет, что это за раздел, что здесь появится и с чего
 * начать. Панель «Начало работы» идёт следом — она же и ведёт дальше.
 */
import { useGettingStarted } from '../api/hooks'
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

export default function EmptyDashboard({ title, what }: { title: string; what?: string }) {
  return (
    <div>
      <ScreenHead title={title} subtitle={t('Пока в школе нет ни одного ученика.')} />
      <GettingStarted />
      <Empty
        title={t('Здесь появятся ваши ученики')}
        what={
          what ??
          'Дашборд собирается из данных учеников: как только они появятся в базе, счётчики, списки и графики заполнятся сами. Начните с загрузки своего файла — того же, который вы ведёте сейчас.'
        }
        action={t('Загрузить файл')}
        to="/import"
      />
    </div>
  )
}
