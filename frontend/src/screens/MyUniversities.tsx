/**
 * «Мои вузы»: список ученика с соответствием требованиям и конкретным разрывом.
 *
 * Процент — соответствие заведённым требованиям, не шанс поступления
 * (инвариант №11). Внутренних ярлыков здесь нет (инвариант №7).
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import {
  useChangeTier,
  useMyUniversities,
  useRemoveFromMyList,
  useSetPriority,
  useCatalog,
} from '../api/hooks'
import Empty from '../components/Empty'
import MatchCard from '../components/MatchCard'
import Modal from '../components/Modal'
import { counted, ErrorNote, Loading, ScreenHead } from '../components/ui'
import './universities.css'
import { t } from '../i18n'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'

/** Категории списка — те же слова и в том же порядке, что в каталоге
 *  при добавлении: ученик выбирал их там, правит здесь (фаза 70). */
const TIERS = [
  { value: 'reach', title: 'с запасом вверх' },
  { value: 'target', title: 'по силам' },
  { value: 'safety', title: 'подстраховка' },
]

export default function MyUniversities() {
  const navigate = useNavigate()
  const mine = useMyUniversities()
  // карточки каталога знают, что у ученика уже в списке и что он может убрать
  const catalog = useCatalog({})
  const remove = useRemoveFromMyList()
  const priority = useSetPriority()
  const retier = useChangeTier()
  // «Изменить» правит ровно то, что ученик вносил при добавлении, —
  // категорию: «мечта, цель или запасной» (фаза 70)
  const [editing, setEditing] = useState<number | null>(null)
  // убираем по подтверждению, и в нём написано название вуза: список
  // ученика — его решения, а промах по кнопке стирает одно из них
  const [dropping, setDropping] = useState<{ id: number; name: string } | null>(null)

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
                <>
                  {/* приоритетный — один на список и первым в нём; пометку
                      ставит ученик, в том числе на строке директора: место
                      в списке его, а содержимое строки — нет (фаза 70) */}
                  {entry?.is_priority ? (
                    <Badge variant="brand">{t('Приоритетный')}</Badge>
                  ) : (
                    entry && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={priority.isPending}
                        onClick={() =>
                          priority.mutate(entry.id, {
                            onSuccess: () => toast.success(t('Приоритетный вуз отмечен')),
                            onError: (error) => toast.error(error.message),
                          })
                        }
                      >
                        {t('Сделать приоритетным')}
                      </Button>
                    )
                  )}
                  {entry?.can_remove &&
                    (editing === entry.id ? (
                      <>
                        <span className="muted uni__note">{t('Куда отнести?')}</span>
                        {TIERS.map((tier) => (
                          <Button
                            key={tier.value}
                            variant={entry.tier === tier.value ? 'default' : 'outline'}
                            size="sm"
                            disabled={retier.isPending}
                            onClick={() =>
                              retier.mutate(
                                { id: entry.id, tier: tier.value },
                                {
                                  onSuccess: () => {
                                    setEditing(null)
                                    toast.success(t('Категория изменена'))
                                  },
                                  onError: (error) => toast.error(error.message),
                                },
                              )
                            }
                          >
                            {t(tier.title)}
                          </Button>
                        ))}
                        <Button variant="ghost" size="sm" onClick={() => setEditing(null)}>
                          {t('Отмена')}
                        </Button>
                      </>
                    ) : (
                      <Button variant="outline" size="sm" onClick={() => setEditing(entry.id)}>
                        {t('Изменить')}
                      </Button>
                    ))}
                  {entry?.can_remove ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        setDropping({
                          id: entry.id,
                          name: `${result.university_name} · ${result.program_name}`,
                        })
                      }
                      disabled={remove.isPending}
                    >
                      {t('Убрать')}
                    </Button>
                  ) : (
                    <span className="muted uni__note">{t('Эту программу ведёт директор по поступлению')}</span>
                  )}
                </>
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

      {/* «Добавить ещё» стоит под списком: добавляют из каталога, и второго
          способа мы не заводим — программа приходит из справочника */}
      {results.length > 0 && (
        <div className="toolbar">
          <Button variant="outline" onClick={() => navigate('/catalog')}>
            {t('Добавить ещё')}
          </Button>
        </div>
      )}

      {dropping && (
        <Modal title={t('Убрать из списка?')} onClose={() => setDropping(null)}>
          <p>
            {t('Программа уйдёт из вашего списка:')} <b>{dropping.name}</b>
          </p>
          <p className="muted">{t('Задачи по ней уйдут из плана. Добавить её снова можно из каталога.')}</p>
          <div className="ctask__actions">
            <span className="cfilters__spacer" />
            <Button
              size="sm"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(dropping.id, {
                  onSuccess: () => {
                    setDropping(null)
                    toast.success(t('Программа убрана из списка'))
                  },
                  onError: (error) => toast.error(error.message),
                })
              }
            >
              {t('Убрать')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setDropping(null)}>
              {t('Отмена')}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
