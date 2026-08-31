/**
 * Избранное ученика (фаза 40): «присмотрел», в отличие от списка «подаюсь».
 * Из избранного программа добавляется в свой список одной кнопкой.
 */
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useAddToMyList, useFavorites } from '../api/hooks'
import Empty from '../components/Empty'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { t } from '../i18n'

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
        title={`${t('Избранное')} · ${rows.length}`}
        subtitle={t('Программы, которые вы присмотрели. Список подачи собирается отдельно.')}
      />

      {rows.length === 0 && (
        <Empty
          icon="heart"
          title={t('В избранном пусто')}
          what={t('Отмечайте сердечком программы в подборе — они соберутся здесь.')}
          action={t('Открыть подбор')}
          to="/selection"
        />
      )}

      <div className="grid grid--two">
        {rows.map((row) => (
          <div key={row.id} className="card card-pad sel__uni">
            <div className="sel__unihead">
              <span className="sel__logo" aria-hidden>
                {row.university_name.slice(0, 1)}
              </span>
              <div className="sel__uniname">
                <b>{row.university_name}</b>
                <span className="muted sel__note">
                  {row.country} · {row.program_name} · {row.level_title}
                </span>
              </div>
              {row.in_my_list && <Badge variant="ok">{t('в списке подачи')}</Badge>}
            </div>
            <div className="propose__actions">
              {!row.in_my_list && (
                <Button
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
              <Button
                variant="ghost"
                size="sm"
                disabled={remove.isPending}
                onClick={() => remove.mutate(row.program, { onError: (error) => toast.error(error.message) })}
              >
                {t('Убрать')}
              </Button>
              <Button variant="outline" size="sm" onClick={() => navigate('/catalog')}>
                {t('Открыть в каталоге')}
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
