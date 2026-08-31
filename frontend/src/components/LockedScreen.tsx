/**
 * Замок вместо пустоты (фаза 47).
 *
 * Раздел, который откроется после шага ученика, показывается с замком
 * и одной фразой: что сделать, чтобы он открылся. Ученик видит, что его
 * ждёт, и знает следующий шаг — вместо формы, которая ничего не найдёт,
 * и пустого списка без объяснений.
 *
 * К чужим доменам это не относится: там ответ без объяснений, потому что
 * дело не в шагах, а в данных других детей (инвариант №7).
 */
import { useNavigate } from 'react-router-dom'
import type { SectionLock } from '../api/hooks'
import Icon from '../layout/icons'
import { Hint } from './ui'
import { Button } from './ui/button'
import './jobs.css'
import { t } from '../i18n'

export default function LockedScreen({ lock }: { lock: SectionLock }) {
  const navigate = useNavigate()
  return (
    <div className="empty locked">
      <span className="empty__icon" aria-hidden="true">
        <Icon name="clock" size={22} />
      </span>
      <b className="empty__title">
        {t(lock.reason)}
        {lock.hint && <Hint text={t(lock.hint)} />}
      </b>
      <p className="muted empty__what">{t('Раздел откроется сам, как только шаг будет сделан.')}</p>
      {lock.action && (
        <Button className="empty__action" onClick={() => navigate(lock.to)}>
          {t(lock.action)}
        </Button>
      )}
    </div>
  )
}
