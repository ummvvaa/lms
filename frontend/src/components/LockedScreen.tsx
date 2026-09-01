/**
 * Замок вместо пустоты (фазы 47 и 48).
 *
 * Раздел, который откроется после шага ученика, показывается приглушённым:
 * содержимое видно, но не нажимается, а сверху — крупная карточка с одной
 * фразой о том, что сделать. Человек видит, что его ждёт, и знает
 * следующий шаг — вместо формы, которая ничего не найдёт.
 *
 * До фазы 48 на этом месте стояла пустая карточка с иконкой: она объясняла
 * причину, но не показывала раздел, и «что я потеряю» оставалось словами.
 *
 * К чужим доменам это не относится: там ответ без объяснений, потому что
 * дело не в шагах, а в данных других детей (инвариант №7).
 */
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import type { SectionLock } from '../api/hooks'
import { Dimmed } from './patterns'
import { t } from '../i18n'

export default function LockedScreen({ lock, children }: { lock: SectionLock; children?: ReactNode }) {
  const navigate = useNavigate()
  return (
    <Dimmed
      title={t(lock.reason)}
      what={
        lock.hint
          ? `${t(lock.hint)}. ${t('Раздел откроется сам, как только шаг будет сделан.')}`
          : t('Раздел откроется сам, как только шаг будет сделан.')
      }
      action={lock.action ? t(lock.action) : undefined}
      onAction={lock.action ? () => navigate(lock.to) : undefined}
    >
      {children}
    </Dimmed>
  )
}
