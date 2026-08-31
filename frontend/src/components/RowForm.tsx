/**
 * Форма одной дочерней строки: заведение и правка.
 *
 * Одна форма на все таблицы карточки — попытки, активности, соревнования,
 * вузы, контакты. Состав полей описывается списком, а не отдельным
 * компонентом на каждую таблицу: пять почти одинаковых форм разъезжаются
 * между собой в первый же месяц.
 */
import { useState } from 'react'
import { t } from '../i18n'
import { NativeSelect } from './ui/native-select'
import { Textarea } from './ui/textarea'
import { Input } from './ui/input'
import { Checkbox } from './ui/checkbox'
import { Button } from './ui/button'
import { Badge } from './ui/badge'

export type FieldKind = 'text' | 'number' | 'date' | 'select' | 'checkbox' | 'textarea'

export interface FieldDef {
  name: string
  label: string
  kind: FieldKind
  options?: { value: string; title: string }[]
  required?: boolean
  placeholder?: string
}

export type RowValues = Record<string, string | number | boolean | null>

function initialOf(fields: FieldDef[], row?: RowValues): RowValues {
  const out: RowValues = {}
  fields.forEach((field) => {
    const value = row?.[field.name]
    if (field.kind === 'checkbox') {
      out[field.name] = Boolean(value)
      return
    }
    const empty = value === null || value === undefined || value === ''
    // обязательный список без пустого варианта показывает первый пункт —
    // значит, и значением должен быть он. Иначе человек видит выбранное
    // «Полное финансирование», жмёт «Завести» и читает «заполните поле»
    if (empty && field.kind === 'select' && field.required && field.options?.length) {
      out[field.name] = field.options[0].value
      return
    }
    out[field.name] = empty ? '' : String(value)
  })
  return out
}

export default function RowForm({
  fields,
  row,
  busy,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  fields: FieldDef[]
  /** прежние значения — при правке; пусто — заведение новой строки */
  row?: RowValues
  busy?: boolean
  submitLabel: string
  /** отдаёт только заполненные поля: пустое значение уходит как null */
  onSubmit: (values: RowValues) => void
  onCancel: () => void
}) {
  const [values, setValues] = useState<RowValues>(() => initialOf(fields, row))
  const [problem, setProblem] = useState<string | null>(null)

  const set = (name: string, value: string | boolean) => setValues((prev) => ({ ...prev, [name]: value }))

  return (
    <div className="rowform">
      {fields.map((field) => (
        <label key={field.name} className={`rowform__field rowform__field--${field.kind}`}>
          <span className="rowform__label">{field.label}</span>
          {field.kind === 'select' && (
            <NativeSelect
              value={String(values[field.name] ?? '')}
              onChange={(event) => set(field.name, event.target.value)}
            >
              {!field.required && <option value="">{t('— не выбрано —')}</option>}
              {(field.options ?? []).map((option) => (
                <option key={option.value} value={option.value}>
                  {option.title}
                </option>
              ))}
            </NativeSelect>
          )}
          {field.kind === 'checkbox' && (
            <Checkbox checked={Boolean(values[field.name])} onCheckedChange={(on) => set(field.name, on)} />
          )}
          {field.kind === 'textarea' && (
            <Textarea
              rows={2}
              value={String(values[field.name] ?? '')}
              onChange={(event) => set(field.name, event.target.value)}
            />
          )}
          {(field.kind === 'text' || field.kind === 'number' || field.kind === 'date') && (
            <Input
              className={field.kind === 'number' ? 'num' : undefined}
              type={field.kind === 'date' ? 'date' : field.kind === 'number' ? 'number' : 'text'}
              step={field.kind === 'number' ? 'any' : undefined}
              placeholder={field.placeholder}
              value={String(values[field.name] ?? '')}
              onChange={(event) => set(field.name, event.target.value)}
            />
          )}
        </label>
      ))}

      {problem && (
        <Badge variant="risk" className="badge--line rowform__problem">
          {problem}
        </Badge>
      )}

      <div className="rowform__actions">
        <Button variant="outline" size="sm" onClick={onCancel}>
          {t('Отмена')}
        </Button>
        <Button
          size="sm"
          disabled={busy}
          onClick={() => {
            const missing = fields.find(
              (field) => field.required && String(values[field.name] ?? '').trim() === '',
            )
            if (missing) {
              setProblem(`Заполните «${missing.label}» — без этого строку не найти в списке`)
              return
            }
            setProblem(null)
            const out: RowValues = {}
            fields.forEach((field) => {
              const value = values[field.name]
              if (field.kind === 'checkbox') out[field.name] = Boolean(value)
              else out[field.name] = String(value ?? '').trim() === '' ? null : String(value).trim()
            })
            onSubmit(out)
          }}
        >
          {submitLabel}
        </Button>
      </div>
    </div>
  )
}
