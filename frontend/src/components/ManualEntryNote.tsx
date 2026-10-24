/**
 * Подсказка на экранах директора, где раньше была загрузка файла.
 *
 * С фазы 35 файлы грузит только администратор: формат выгрузок у всех
 * разный, и разбираться с чужими файлами должен один человек, а не пятеро.
 * Директор вносит данные руками в таблице. Первое,
 * что сделает человек без кнопки, — напишет, что она пропала; поэтому
 * здесь не «доступ запрещён», а объяснение, куда идти.
 */
import { useNavigate } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { t } from '../i18n'
import { directorHidden, IMPORT_ROLES } from '../layout/nav'
import Notice from './Notice'
import { Button } from './ui/button'

export default function ManualEntryNote({
  history = true,
}: {
  /** показать переход к истории загрузок */
  history?: boolean
}) {
  const navigate = useNavigate()
  const { me } = useAuth()
  // история загрузок живёт на экране «Импорт»; у кого экрана нет, тому
  // и кнопка вела бы в никуда
  // у Кымбат «Импорт» спрятан (24.10.2026): кнопка вела бы на главную
  const seesHistory = history && me !== null && me !== undefined && IMPORT_ROLES.includes(me.role) && !directorHidden(me.role, '/import')
  return (
    <Notice icon="upload" className="manual-note" summary={t('Файлы загружает администратор')}>
      <span className="manual-note__text">
        {t('Данные вносятся руками; файлы загружает администратор.')}
      </span>
      {seesHistory && (
        <Button variant="ghost" size="sm" onClick={() => navigate('/import')}>
          {t('История загрузок')}
        </Button>
      )}
    </Notice>
  )
}
