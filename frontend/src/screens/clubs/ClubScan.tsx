/**
 * Отметка на встрече кружка по QR: `/k/<токен>`. Та же страница, что у секций
 * (`sport/Scan`): вход прямо здесь, код ждёт входа две минуты; своя ручка и слова.
 */
import { clubScan } from '../../api/clubs'
import { t } from '../../i18n'
import Scan from '../sport/Scan'

export default function ClubScan() {
  // слова — на языке интерфейса в момент показа, поэтому собираются здесь, а не при загрузке модуля
  return (
    <Scan
      kind={{
        send: clubScan,
        home: { path: '/clubs', label: t('Мои кружки') },
        stale: t('QR меняется каждые несколько секунд. Отсканируй код с экрана ментора ещё раз'),
        wish: t('Хорошей встречи!'),
      }}
    />
  )
}
