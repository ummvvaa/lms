/**
 * Экран «Нет связи с сервером» (фаза 76).
 *
 * Показывается вместо пустого поля, когда сессию не удалось спросить
 * у сервера: он не ответил вовсе, а не отказал. Уводить на вход по
 * отсутствию ответа нельзя (фаза 36, D3) — человек с живой сессией
 * оказался бы на экране входа из-за секунды без сети. Кнопка пробует
 * сейчас, не дожидаясь таймера повторов.
 */
import { t } from '../i18n'
import { Button } from './ui/button'

export default function OfflineScreen({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="login">
      <div className="card card-pad offline" role="alert">
        <span className="eyebrow">{t('Нет связи с сервером')}</span>
        <p className="offline__text">
          {t('Сервер не ответил. Проверьте связь — данные на месте, входить заново не нужно.')}
        </p>
        <Button onClick={onRetry}>{t('Повторить')}</Button>
      </div>
    </div>
  )
}
