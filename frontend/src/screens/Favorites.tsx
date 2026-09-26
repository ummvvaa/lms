/**
 * Избранное ученика: «присмотрел», в отличие от списка «подаюсь».
 * Те же строки, что в каталоге; из избранного программа добавляется
 * в свой список одной кнопкой.
 */
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useAddToMyList, useFavorites } from '../api/hooks'
import { Row, Rows } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { NoteCard } from './academics/shared'

export default function Favorites() {
  const { query, remove } = useFavorites()
  const addToList = useAddToMyList()
  const navigate = useNavigate()

  if (query.isLoading) return <Loading kind="table" />
  if (query.error) return <ErrorNote error={query.error} />

  const rows = query.data?.results ?? []

  return (
    <div>
      <ScreenHead
        title={t('Избранное')}
        subtitle={t('Программы, которые вы присмотрели. Список подачи собирается отдельно.')}
        actions={
          <Button size="sm" onClick={() => navigate('/catalog')}>
            {t('Открыть каталог')}
          </Button>
        }
      />
      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard
            title={t('Сохранённые программы')}
            count={rows.length || undefined}
            empty={rows.length === 0 && t('отмечайте сердечком программы в каталоге — они соберутся здесь')}
            emptyAction={
              <Button variant="secondary" size="sm" onClick={() => navigate('/selection')}>
                {t('Открыть подбор')}
              </Button>
            }
          >
            <Rows>
              {rows.map((row) => (
                <Row
                  key={row.id}
                  avatar={row.university_name}
                  title={row.university_name}
                  note={`${row.country} · ${row.program_name} · ${row.level_title}`}
                  right={row.in_my_list ? <Chip tone="good" size="sm">{t('в списке подачи')}</Chip> : undefined}
                  acts={
                    <>
                      {!row.in_my_list && (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() =>
                            addToList.mutate(
                              { program: row.program, tier: 'target' },
                              {
                                onSuccess: () => toast.success(t('Добавлено в ваш список')),
                                onError: (error) => toast.error(error.message),
                              },
                            )
                          }
                        >
                          {t('В мой список')}
                        </Button>
                      )}
                      <Button variant="ghost" size="sm" disabled={remove.isPending} onClick={() => remove.mutate(row.program, { onError: (error) => toast.error(error.message) })}>
                        {t('Убрать')}
                      </Button>
                    </>
                  }
                />
              ))}
            </Rows>
          </DataCard>
        </div>
        <div className="acad__stack">
          <NoteCard title={t('Как это устроено')}>{t('Избранное — заметки на полях: программу присмотрели, но ещё не решили. В список подачи она попадает кнопкой «В мой список», и тогда её дедлайн становится задачей плана.')}</NoteCard>
        </div>
      </div>
    </div>
  )
}
