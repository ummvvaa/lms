/**
 * Раздача паролей списком (фаза 69).
 *
 * Самое опасное действие на экране: у того, кто уже придумал себе
 * пароль, выдача его сбросит, и человек окажется заперт с письмом,
 * которого не ждал. Промахнуться по всей школе — значит остановить её
 * на день.
 *
 * Поэтому окно устроено так: сначала человек читает, кого действие
 * затронет и кого обойдёт, потом видит предупреждение про уже заданные
 * пароли, и только потом набирает число затронутых руками. Одной кнопки
 * здесь нет и быть не должно.
 *
 * Числа считает сервер по той же выборке, что показана на экране, —
 * окно их не складывает само.
 *
 * Писем раздача не шлёт (фаза 70): единственный носитель — файл,
 * и раздают пароли из рук в руки.
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { useHandout, type HandoutPlan, type UserFilters } from '../api/hooks'
import { downloadFile } from '../api/client'
import Modal from './Modal'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Checkbox } from './ui/checkbox'
import { Input } from './ui/input'
import { t } from '../i18n'

export default function HandoutDialog({
  filters,
  picked,
  onClose,
}: {
  filters: UserFilters
  /** отмеченные строки; пусто — работаем по текущему фильтру */
  picked: number[]
  onClose: () => void
}) {
  const handout = useHandout()
  const [includeReady, setIncludeReady] = useState(false)
  const [typed, setTyped] = useState('')
  const [plan, setPlan] = useState<HandoutPlan | null>(null)
  const [done, setDone] = useState<HandoutPlan | null>(null)

  const scope = picked.length > 0 ? { users: picked } : filters

  // предпросмотр пересчитывается при каждой смене галочки: число,
  // которое человек набирает, должно совпадать с тем, что он видит
  useEffect(() => {
    handout.mutate(
      { ...scope, include_ready: includeReady },
      { onSuccess: setPlan, onError: (error) => toast.error(error.message) },
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [includeReady, picked.join(','), filters.state, filters.role, filters.group, filters.search])

  const run = () =>
    handout.mutate(
      { ...scope, include_ready: includeReady, confirm: typed.trim() },
      {
        onSuccess: (result) => {
          setDone(result)
          toast.success(result.detail ?? t('Пароли выданы'))
        },
        onError: (error) => toast.error(error.message),
      },
    )

  if (done) {
    return (
      <Modal title={t('Пароли выданы')} onClose={onClose}>
        <div className="handout">
          <p>{done.detail}</p>
          <p className="muted">
            {t('Пароли показываются один раз. Скачайте список — на сервере он не хранится.')}
          </p>
          <p className="muted">
            {t('В файле лист «Сотрудники» и по листу на группу — лист можно отдать куратору целиком.')}
          </p>
          <div className="ctask__actions">
            <span className="cfilters__spacer" />
            <Button
              size="sm"
              onClick={() =>
                downloadFile('/users/handout/export/', 'parolyi-uchenikov.xlsx', {
                  method: 'POST',
                  body: JSON.stringify({ rows: done.rows ?? [] }),
                }).catch((error: Error) => toast.error(error.message))
              }
            >
              {t('Скачать список')}
            </Button>
            <Button variant="outline" size="sm" onClick={onClose}>
              {t('Закрыть')}
            </Button>
          </div>
        </div>
      </Modal>
    )
  }

  const ready = plan?.confirm === typed.trim() && (plan?.total ?? 0) > 0

  return (
    <Modal title={t('Выдать пароли')} onClose={onClose}>
      <div className="handout">
        <p>
          {picked.length > 0
            ? `${t('Действие по отмеченным строкам:')} ${picked.length}`
            : t('Действие по текущему фильтру — по всем, кто сейчас в списке')}
        </p>

        {plan && (
          <>
            <div className="handout__part">
              <span className="eyebrow">{t('Кого затронет')}</span>
              <p className="handout__total num">{plan.total}</p>
              <ul className="handout__counts">
                {plan.breakdown.map((row) => (
                  <li key={row.code}>
                    {row.title}: <b className="num">{row.count}</b>
                    {row.code === 'ready' && !includeReady && (
                      <span className="muted"> {t('— не затронуты')}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>

            {plan.warning && (
              <p className="handout__warn">
                {plan.warning}
                {plan.protected > 0 && !includeReady && (
                  <>
                    {' '}
                    <Badge variant="ok">{t('сейчас исключены')}</Badge>
                  </>
                )}
              </p>
            )}

            <label className="handout__check">
              <Checkbox
                checked={includeReady}
                aria-label={t('включить и тех, кто уже сменил пароль')}
                onCheckedChange={(on) => {
                  setIncludeReady(Boolean(on))
                  setTyped('')
                }}
              />
              {t('включить и тех, кто уже сменил пароль')}
            </label>

            <label className="handout__field">
              <span className="eyebrow">
                {t('Наберите число затронутых, чтобы подтвердить:')} <b>{plan.confirm}</b>
              </span>
              <Input
                value={typed}
                aria-label={t('Число затронутых')}
                placeholder={plan.confirm}
                onChange={(event) => setTyped(event.target.value)}
              />
            </label>
          </>
        )}

        <div className="ctask__actions">
          <span className="muted">
            {t('Пароли не рассылаются — скачайте файл и раздайте сами')}
          </span>
          <span className="cfilters__spacer" />
          <Button size="sm" disabled={!ready || handout.isPending} onClick={run}>
            {t('Выдать пароли')}
          </Button>
          <Button variant="outline" size="sm" onClick={onClose}>
            {t('Отмена')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
