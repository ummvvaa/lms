/**
 * Время встречи кружка — ЧЧ:ММ, всегда 24 часа (01.11.2026).
 *
 * Родное поле времени берёт формат из языка браузера и показывает «03:00 PM»
 * у английского — задать ему 24 часа нельзя. Здесь обычное поле: цифры
 * и двоеточие, «1500» само становится «15:00», неверное время подсвечивается.
 */
import Field from '../../components/Field'
import { t } from '../../i18n'

const CLOCK = /^([01]\d|2[0-3]):[0-5]\d$/

/** Верно ли время «ЧЧ:ММ». */
export const isClock = (value: string) => CLOCK.test(value)

/** Ввод к виду «ЧЧ:ММ»: только цифры, двоеточие после часов, не длиннее пяти знаков. */
export function toClock(raw: string): string {
  const digits = raw.replace(/\D/g, '').slice(0, 4)
  if (raw.includes(':')) {
    const [hours, minutes = ''] = raw.split(':')
    return `${hours.replace(/\D/g, '').slice(0, 2)}:${minutes.replace(/\D/g, '').slice(0, 2)}`
  }
  return digits.length > 2 ? `${digits.slice(0, 2)}:${digits.slice(2)}` : digits
}

export default function ClockField({
  name,
  label,
  value,
  onChange,
}: {
  name: string
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <Field
      name={name}
      label={label}
      value={value}
      placeholder={t('ЧЧ:ММ')}
      onChange={(next) => onChange(toClock(next))}
      error={value && !isClock(value) ? t('Время — ЧЧ:ММ, например 15:00') : undefined}
    />
  )
}
