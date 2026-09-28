/**
 * Шаги мастера.
 *
 * Образец — ряд шагов в `docs/ui/language/Wizard.html` и `.steps`
 * из `docs/ui/reference.html`: номер в кружке — `--accent`
 * у текущего, `--good` с галочкой у пройденного, `--neutral-bg` у будущего;
 * между шагами линия `--line-2`, до пройденного — цветом пройденного,
 * до текущего — акцентом. На телефоне ряд не помещается, и вместо него
 * одна строка «Шаг N из M · название».
 *
 * Корень несёт и класс `wizard__steps`: по нему мастер импорта находят
 * браузерные проверки, и он же даёт отступ снизу в стилях мастера.
 */
import { Fragment } from 'react'
import Icon from '../layout/icons'
import { usePhone } from '../phone'
import { t } from '../i18n'

export default function WizardSteps({
  steps,
  current,
  className,
}: {
  /** названия шагов по порядку, уже переведённые */
  steps: string[]
  /** номер текущего шага, с единицы */
  current: number
  className?: string
}) {
  const phone = usePhone()
  const root = `steps wizard__steps${phone ? ' steps--phone' : ''}${className ? ` ${className}` : ''}`

  if (phone) {
    return (
      <nav className={root} aria-label={t('Шаги мастера')}>
        <span className="steps__count t-note num">
          {t('Шаг')} {current} {t('из')} {steps.length}
        </span>
        <b className="steps__current">{steps[current - 1]}</b>
      </nav>
    )
  }

  return (
    <nav className={root} aria-label={t('Шаги мастера')}>
      {steps.map((title, index) => {
        const number = index + 1
        const state = number < current ? 'done' : number === current ? 'on' : 'next'
        const line = number < current ? ' steps__line--done' : number === current ? ' steps__line--on' : ''
        return (
          <Fragment key={number}>
            {index > 0 && <span className={`steps__line${line}`} aria-hidden="true" />}
            <span
              className={`steps__item steps__item--${state}`}
              aria-current={state === 'on' ? 'step' : undefined}
            >
              <i className="steps__dot num">{state === 'done' ? <Icon name="check" size={14} /> : number}</i>
              <span className="steps__title">{title}</span>
            </span>
          </Fragment>
        )
      })}
    </nav>
  )
}
