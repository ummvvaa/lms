/**
 * Поле формы нового языка.
 *
 * Образец — `F.text`, `F.select`, `F.area`, `F.date`, `F.check`, `F.static`
 * и `F.row` из `docs/ui/reference.html`, вид — панель правки
 * в `docs/ui/language/Directory.html`: подпись капителью над полем, само
 * поле высотой `--control-h` с рамкой `--line-2` на подложке `--surface-2`,
 * под ним подсказка и — если есть — ошибка цветом `--bad`.
 *
 * Поле внутри — из реестра (`Input`, `Textarea`, `Checkbox`) или наш
 * `SelectField` (на телефоне он открывает лист снизу). Здесь только
 * подпись, рамка, подсказка и их связь с полем через `aria-*`.
 * Значение и его смысл — у вызывающего: компонент отдаёт строку
 * (у галочки — да или нет), ничего не переводит и не проверяет.
 *
 * `Field.Row` ставит два или три поля в ряд, на телефоне — друг под другом.
 * `Field.Static` — подпись и значение без поля, когда править нечего.
 */
import { useId, type ReactNode } from 'react'
import { Checkbox } from './ui/checkbox'
import { Input } from './ui/input'
import { Textarea } from './ui/textarea'
import { SelectField } from './SelectField'

export interface FieldOption {
  value: string
  title: string
}

interface FieldBase {
  name: string
  label: string
  /** подпись под полем: формат, пример, откуда берётся значение */
  hint?: ReactNode
  /** отказ, адресованный этому полю; поле помечается `aria-invalid` */
  error?: ReactNode
  required?: boolean
  disabled?: boolean
  id?: string
  className?: string
}

export interface TextFieldProps extends FieldBase {
  kind?: 'text' | 'number' | 'date' | 'password' | 'email'
  value: string | number | null | undefined
  onChange?: (value: string) => void
  placeholder?: string
  min?: number | string
  max?: number | string
  step?: number | string
  readOnly?: boolean
  autoFocus?: boolean
  autoComplete?: string
}

export interface TextareaFieldProps extends FieldBase {
  kind: 'textarea'
  value: string | null | undefined
  onChange?: (value: string) => void
  placeholder?: string
  rows?: number
  readOnly?: boolean
  autoFocus?: boolean
}

export interface SelectFieldProps extends FieldBase {
  kind: 'select'
  value: string | number | null | undefined
  onChange?: (value: string) => void
  options: FieldOption[]
  /** подпись пустого пункта; без неё пустого пункта в списке нет */
  placeholder?: string
}

export interface CheckboxFieldProps extends FieldBase {
  kind: 'checkbox'
  checked: boolean
  onChange?: (checked: boolean) => void
}

export type FieldProps = TextFieldProps | TextareaFieldProps | SelectFieldProps | CheckboxFieldProps

function Field(props: FieldProps) {
  const generated = useId()
  const id = props.id ?? `field-${generated}`
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const invalid = Boolean(props.error)
  const describedBy =
    [props.hint ? hintId : '', props.error ? errorId : ''].filter(Boolean).join(' ') || undefined
  const classes = `field${invalid ? ' field--invalid' : ''}${props.className ? ` ${props.className}` : ''}`

  // одно и то же у любого поля: имя, состояние и связь с подсказкой
  const shared = {
    id,
    name: props.name,
    disabled: props.disabled,
    required: props.required,
    'aria-invalid': invalid || undefined,
    'aria-describedby': describedBy,
  }

  const foot = (
    <>
      {props.hint && (
        <span id={hintId} className="field__hint t-note">
          {props.hint}
        </span>
      )}
      {props.error && (
        <span id={errorId} className="field__error t-note" role="alert">
          {props.error}
        </span>
      )}
    </>
  )

  if (props.kind === 'checkbox') {
    return (
      <div className={`${classes} field--check`}>
        <label className="field__check" htmlFor={id}>
          <Checkbox
            {...shared}
            checked={props.checked}
            onCheckedChange={(checked) => props.onChange?.(Boolean(checked))}
          />
          <span className="field__checklabel">{props.label}</span>
        </label>
        {foot}
      </div>
    )
  }

  let control: ReactNode
  if (props.kind === 'textarea') {
    control = (
      <Textarea
        {...shared}
        value={props.value ?? ''}
        placeholder={props.placeholder}
        rows={props.rows}
        readOnly={props.readOnly}
        autoFocus={props.autoFocus}
        onChange={(event) => props.onChange?.(event.target.value)}
      />
    )
  } else if (props.kind === 'select') {
    control = (
      <SelectField
        {...shared}
        aria-label={props.label}
        value={props.value === null || props.value === undefined ? '' : String(props.value)}
        onChange={(event) => props.onChange?.(event.target.value)}
      >
        {props.placeholder !== undefined && <option value="">{props.placeholder}</option>}
        {props.options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.title}
          </option>
        ))}
      </SelectField>
    )
  } else {
    const kind = props.kind ?? 'text'
    control = (
      <Input
        {...shared}
        type={kind}
        inputMode={kind === 'number' ? 'decimal' : undefined}
        value={props.value ?? ''}
        placeholder={props.placeholder}
        min={props.min}
        max={props.max}
        step={props.step}
        readOnly={props.readOnly}
        autoFocus={props.autoFocus}
        autoComplete={props.autoComplete}
        onChange={(event) => props.onChange?.(event.target.value)}
      />
    )
  }

  return (
    <div className={classes}>
      <label className="field__label t-caps" htmlFor={id}>
        {props.label}
      </label>
      <div className="field__control">{control}</div>
      {foot}
    </div>
  )
}

/** Ряд полей: два по умолчанию, три — `cols={3}`; на телефоне — столбиком. */
export function FieldRow({
  children,
  cols = 2,
  className,
}: {
  children: ReactNode
  cols?: 2 | 3
  className?: string
}) {
  return (
    <div className={`field-row${cols === 3 ? ' field-row--3' : ''}${className ? ` ${className}` : ''}`}>
      {children}
    </div>
  )
}

/** Подпись и значение без поля — для того, что показывают, но не правят. */
export function FieldStatic({
  label,
  children,
  className,
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`field${className ? ` ${className}` : ''}`}>
      <span className="field__label t-caps">{label}</span>
      <div className="field__static">{children}</div>
    </div>
  )
}

Field.Row = FieldRow
Field.Static = FieldStatic

export default Field
