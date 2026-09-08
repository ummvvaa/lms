/**
 * Кабинет куратора (фаза 60) — первая, короткая версия экрана.
 *
 * Свои группы и число учеников в них; всё считает сервер по назначениям
 * на сегодня, а не по текстовому полю группы. Очередь подтверждений,
 * задачи ученикам, заметки и пробники появятся в фазах 61–63 — здесь их нет.
 * Строка группы никуда не ведёт намеренно: списка учеников группы у куратора
 * пока нет, а стрелка на закрытый ему экран была бы ссылкой в никуда.
 */
import { useCabinet } from '../../api/hooks'
import { Row, Rows } from '../../components/patterns'
import { counted, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import { CabinetStats } from './cabinet'

interface CuratorCabinetState {
  title: string
  owner: string
  stats: Parameters<typeof CabinetStats>[0]['stats']
  groups: { id: number; code: string; grade: number; students: number; since: string }[]
}

export default function CuratorCabinet() {
  const { data, isLoading, error } = useCabinet()

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const cabinet = data as unknown as CuratorCabinetState

  return (
    <div>
      <ScreenHead title={t(cabinet.title)} subtitle={cabinet.owner} />
      <CabinetStats stats={cabinet.stats} />

      <DataCard
        title={t('Мои группы')}
        note={t('Назначены администратором на сегодня')}
        count={cabinet.groups.length}
        accent="brand"
      >
        {cabinet.groups.length === 0 && (
          <p className="muted rows__empty">{t('Группы вам ещё не назначены — обратитесь к администратору')}</p>
        )}
        <Rows>
          {cabinet.groups.map((group) => (
            <Row
              key={group.id}
              icon="people"
              tone="brand"
              title={group.code}
              note={`${group.grade} ${t('класс')} · ${counted(group.students, ['ученик', 'ученика', 'учеников'])}`}
              right={`${t('с')} ${new Date(group.since).toLocaleDateString('ru')}`}
            />
          ))}
        </Rows>
      </DataCard>
    </div>
  )
}
