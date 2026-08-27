/**
 * Полоса «Нет связи с сервером» — одна на всё приложение (фаза 36, D3).
 *
 * Появляется, когда сервер перестал отвечать, и исчезает сама, когда
 * ответил: экран под ней остаётся тем же, черновики не теряются, входить
 * заново не нужно. Кнопка даёт попробовать сейчас, не дожидаясь таймера.
 */
import { retryNow } from '../api/connection'
import { useConnection } from '../api/useConnection'
import { t } from '../i18n'
import { Button } from './ui/button'

export default function ConnectionBanner() {
  const { offline, attempt, nextIn } = useConnection()
  if (!offline) return null
  return (
    <div className="connection" role="status" aria-live="polite" data-attempt={attempt}>
      <span className="connection__dot" aria-hidden="true" />
      <span className="connection__text">
        {t('Нет связи с сервером, пробуем переподключиться')}
        <span className="muted connection__note">
          {' '}
          · попытка {attempt}, следующая через {nextIn} с
        </span>
      </span>
      <Button variant="outline" size="sm" className="connection__retry" onClick={retryNow}>
        {t('Попробовать сейчас')}
      </Button>
    </div>
  )
}
