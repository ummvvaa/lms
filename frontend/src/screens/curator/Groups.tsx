/**
 * «Мои группы» — из меню профиля (фаза 61).
 *
 * Карточка на группу: сколько человек, с какого числа ведёт куратор,
 * кнопка «Открыть учеников». Сменить куратора отсюда нельзя и не будет
 * можно: назначение — право администратора (фаза 60), и плашка внизу
 * говорит об этом словами, а не молчанием отсутствующей кнопки.
 */
import { useNavigate } from 'react-router-dom'
import { useCuratorOverview } from '../../api/hooks'
import { counted, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { ALL } from './state'
import './curator.css'

export default function CuratorGroups() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useCuratorOverview(ALL)

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />

  const groups = data?.groups ?? []

  return (
    <div>
      <ScreenHead title={t('Мои группы')} subtitle={t('Назначены администратором')} />

      <div className="cgroups">
        {groups.map((group) => (
          <DataCard
            key={group.id}
            title={group.code}
            note={`${group.grade} ${t('класс')} · ${counted(group.students, ['ученик', 'ученика', 'учеников'])}`}
            accent="brand"
          >
            <p className="muted">
              {t('Куратор с')} {new Date(group.since).toLocaleDateString('ru')}
            </p>
            <Button variant="outline" size="sm" onClick={() => navigate(`/students?group=${group.code}`)}>
              {t('Открыть учеников')}
            </Button>
          </DataCard>
        ))}
      </div>

      {groups.length === 0 && <p className="muted">{t('Группы вам ещё не назначены — обратитесь к администратору')}</p>}

      <p className="cnote">
        {t(
          'Сменить куратора у группы может только администратор. История подтверждений остаётся за прежним куратором, а группы переходят новому.',
        )}
      </p>
    </div>
  )
}
