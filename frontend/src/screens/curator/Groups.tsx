/**
 * «Мои группы» — из меню профиля (фаза 61).
 *
 * Строка на группу: сколько человек, с какого числа ведёт куратор,
 * «Открыть учеников». Сменить куратора отсюда нельзя и не будет
 * можно: назначение — право администратора (фаза 60), и плашка внизу
 * говорит об этом словами, а не молчанием отсутствующей кнопки.
 */
import { useNavigate } from 'react-router-dom'
import { useCuratorOverview } from '../../api/hooks'
import Notice from '../../components/Notice'
import { Row, Rows } from '../../components/patterns'
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
      <ScreenHead title={t('Мои группы')} />

      <DataCard title={t('Группы')} count={groups.length || undefined} empty={groups.length === 0 && t('группы вам ещё не назначены — обратитесь к администратору')}>
        <Rows>
          {groups.map((group) => (
            <Row
              key={group.id}
              icon="people"
              tone="accent"
              title={group.code}
              note={`${counted(group.students, ['ученик', 'ученика', 'учеников'])} · ${t('куратор с')} ${new Date(group.since).toLocaleDateString('ru')}`}
              acts={
                <Button variant="secondary" size="sm" onClick={() => navigate(`/students?group=${group.code}`)}>
                  {t('Открыть учеников')}
                </Button>
              }
            />
          ))}
        </Rows>
      </DataCard>

      <Notice className="cnote">
        {t(
          'Сменить куратора у группы может только администратор. История подтверждений остаётся за прежним куратором, а группы переходят новому.',
        )}
      </Notice>
    </div>
  )
}
