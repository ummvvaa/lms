/**
 * Выпадающий список формы (фаза 51).
 *
 * На ноутбуке это `NativeSelect` из реестра — ровно то, что было
 * построено раньше, до пикселя: браузерный список, клавиатура,
 * поиск по первым буквам.
 *
 * На телефоне браузер рисует его сам — крошечным колесом или списком
 * в углу экрана, — и выбрать пункт пальцем в форме, где полей десять,
 * труднее, чем набрать значение руками. Поэтому там же, где везде,
 * открывается обычный лист снизу: пункты строками по 44 пикселя,
 * выбранный отмечен, лист закрывается по фону и по выбору.
 *
 * Компонент один на весь интерфейс намеренно: разное поведение списков
 * в разных разделах — источник дефектов на годы вперёд.
 */
import { Children, isValidElement, useState, type ChangeEvent, type ReactNode } from 'react'
import Icon from '../layout/icons'
import { usePhone } from '../phone'
import { t } from '../i18n'
import { NativeSelect } from './ui/native-select'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from './ui/sheet'

type SelectProps = Omit<React.ComponentProps<'select'>, 'size'> & {
  size?: 'sm' | 'default'
}

interface Choice {
  value: string
  title: string
}

/** Пункты списка из разметки: и `<option>`, и `<optgroup>` внутри. */
function choicesOf(children: ReactNode): Choice[] {
  const out: Choice[] = []
  Children.forEach(children, (child) => {
    if (!isValidElement(child)) return
    const props = child.props as { value?: unknown; children?: ReactNode }
    // группа: пункты лежат внутри неё
    if (props.value === undefined && props.children !== undefined) {
      const nested = choicesOf(props.children)
      if (nested.length > 0) {
        out.push(...nested)
        return
      }
    }
    if (props.value === undefined) return
    out.push({ value: String(props.value), title: textOf(props.children) })
  })
  return out
}

/** Подпись пункта строкой: внутри `<option>` бывает и число, и вставка. */
function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children)
  return ''
}

export function SelectField({ children, value, onChange, className, disabled, ...rest }: SelectProps) {
  const phone = usePhone()
  const [open, setOpen] = useState(false)

  if (!phone)
    return (
      <NativeSelect value={value} onChange={onChange} className={className} disabled={disabled} {...rest}>
        {children}
      </NativeSelect>
    )

  const choices = choicesOf(children)
  const current = choices.find((choice) => choice.value === String(value ?? ''))

  const pick = (next: string) => {
    setOpen(false)
    // вызывающий код читает `event.target.value` — отдаём ему ровно это
    onChange?.({ target: { value: next } } as ChangeEvent<HTMLSelectElement>)
  }

  return (
    <>
      <button
        type="button"
        className={`selfield${className ? ` ${className}` : ''}`}
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={rest['aria-label']}
        onClick={() => setOpen(true)}
      >
        <span className="selfield__value">{current?.title ?? t('— не выбрано —')}</span>
        <Icon name="chevronRight" size={15} />
      </button>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="bottom" className="selsheet">
          <span className="moresheet__grabber" aria-hidden="true" />
          <SheetHeader className="moresheet__head">
            <SheetTitle>{rest['aria-label'] ?? t('Выберите значение')}</SheetTitle>
          </SheetHeader>
          <div className="selsheet__list">
            {choices.map((choice) => (
              <button
                key={choice.value}
                type="button"
                className={`selsheet__item${choice.value === current?.value ? ' selsheet__item--on' : ''}`}
                onClick={() => pick(choice.value)}
              >
                <span className="selsheet__title">{choice.title}</span>
                {choice.value === current?.value && <Icon name="check" size={15} />}
              </button>
            ))}
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}
