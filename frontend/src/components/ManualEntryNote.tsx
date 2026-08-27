/**
 * Подсказка на экранах директора, где раньше была загрузка файла.
 *
 * С фазы 35 файлы грузит только администратор: формат выгрузок у всех
 * разный, и разбираться с чужими файлами должен один человек, а не пятеро.
 * Директор вносит данные руками в таблице или вставкой текста. Первое,
 * что сделает человек без кнопки, — напишет, что она пропала; поэтому
 * здесь не «доступ запрещён», а объяснение, куда идти.
 */
import { useNavigate } from 'react-router-dom'
import Icon from '../layout/icons'
import { t } from '../i18n'
import { Button } from './ui/button'

export default function ManualEntryNote({
  paste = true,
  history = true,
}: {
  /** показать переход к вставке текста в помощнике */
  paste?: boolean
  /** показать переход к истории загрузок */
  history?: boolean
}) {
  const navigate = useNavigate()
  return (
    <div className="manual-note" role="note">
      <span className="manual-note__icon" aria-hidden="true">
        <Icon name="upload" size={16} />
      </span>
      <span className="manual-note__text">
        {t('Данные вносятся руками или вставкой текста; файлы загружает администратор.')}
      </span>
      {paste && (
        <Button variant="outline" size="sm" onClick={() => navigate('/assistant?panel=paste_as_is')}>
          {t('Вставить текст')}
        </Button>
      )}
      {history && (
        <Button variant="ghost" size="sm" onClick={() => navigate('/import')}>
          {t('История загрузок')}
        </Button>
      )}
    </div>
  )
}
