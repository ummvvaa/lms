/**
 * «Мои вузы»: список ученика с соответствием требованиям и конкретным разрывом.
 *
 * Процент — соответствие заведённым требованиям, не шанс поступления
 * (инвариант №11). Внутренних ярлыков здесь нет (инвариант №7).
 */
import { useNavigate } from 'react-router-dom'
import { useMyUniversities, useRemoveFromMyList, useCatalog } from '../api/hooks'
import Empty from '../components/Empty'
import MatchCard from '../components/MatchCard'
import { counted, ErrorNote, Loading, ScreenHead } from '../components/ui'
import './universities.css'
import { t } from '../i18n'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'

export default function MyUniversities() {
  const navigate = useNavigate()
  const mine = useMyUniversities()
  // карточки каталога знают, что у ученика уже в списке и что он может убрать
  const catalog = useCatalog({})
  const remove = useRemoveFromMyList()

  if (mine.isLoading) return <Loading />
  if (mine.error) return <ErrorNote error={mine.error} />

  const byProgram = new Map((catalog.data?.results ?? []).map((card) => [card.program, card]))
  const results = mine.data ?? []
  const open = results.filter((r) => r.is_open).length
  const waiting = results.filter((r) => {
    const card = byProgram.get(r.program)
    return card?.my_entry && !card.my_entry.is_confirmed
  }).length

  return (
    <div>
      <ScreenHead
        title={t('Мои вузы')}
        subtitle={
          results.length === 0
            ? 'Список пока пуст — начните с каталога.'
            : `${counted(results.length, ['программа', 'программы', 'программ'])} в вашем списке, ` +
              `по ${open} вы проходите уже сейчас.`
        }
        actions={
          <>
            <Button variant="outline" onClick={() => navigate('/catalog?mode=whatif')}>
              {t('Что откроется, если')}
            </Button>
            <Button onClick={() => navigate('/catalog')}>{t('Найти ещё в каталоге')}</Button>
          </>
        }
      />

      <div className="toolbar">
        {waiting > 0 && (
          <Badge variant="warn" className="num">
            ждут подтверждения директора: {waiting}
          </Badge>
        )}
      </div>

      <div className="grid grid--cards">
        {results.map((result) => {
          const card = byProgram.get(result.program)
          const entry = card?.my_entry ?? null
          return (
            <MatchCard
              key={result.program}
              card={{
                ...result,
                university: card?.university ?? 0,
                level: card?.level ?? 'low',
                rounds: card?.rounds ?? [],
                in_my_list: true,
                my_entry: entry,
              }}
              actions={
                entry?.can_remove ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => remove.mutate(entry.id)}
                    disabled={remove.isPending}
                  >
                    {t('Убрать из списка')}
                  </Button>
                ) : (
                  <span className="muted uni__note">{t('Эту программу ведёт директор по поступлению')}</span>
                )
              }
            />
          )
        })}
        {results.length === 0 && (
          <Empty
            icon="bookmark"
            title={t('Ваш список вузов пуст')}
            what={t('Выберите программы в каталоге — и они появятся здесь.')}
            hint={t(
              'По каждой видно, проходите ли вы по требованиям и чего не хватает, а дедлайны сами станут задачами плана.',
            )}
            action={t('Открыть каталог')}
            to="/catalog"
          />
        )}
      </div>
    </div>
  )
}
