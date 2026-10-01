/**
 * Формы кабинета ученика: предложение значений профиля, новая запись
 * (олимпиада, соревнование, достижение), список записей с пометками
 * и карточка домена. Одни и те же у «Портфолио» 11 и у разделов 8–10
 * «Олимпиады» и «Спорт»: значения уходят предложением владельцу домена.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useDocuments, usePropose, type ProposeRow } from '../api/hooks'
import { profileModelOf, type Domain, type DomainField, type DomainModel } from '../api/types'
import { Chip, DataCard } from './ui'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { NativeSelectOption } from './ui/native-select'
import { SelectField } from './SelectField'
import { Textarea } from './ui/textarea'
import { t } from '../i18n'
import { todayAlmaty } from '../lib/dates'
import { CERT_SECTIONS, DOMAIN_TITLE, SECTION_LABELS, shown } from '../screens/portfolioData'

/** Форма правки полей профиля: значения уходят предложением (фаза 37). */
export function ProposeForm({
  model,
  fields,
  current,
  pending,
  label,
  hint,
  certificate = false,
}: {
  model: DomainModel
  fields: DomainField[]
  current: Record<string, unknown>
  pending: Record<string, string>
  /** подпись кнопки: «Внести баллы» у академических результатов */
  label?: string
  /** одна строка рядом с кнопкой — о том, что перехода не будет */
  hint?: string
  /** спрашивать ли секции IELTS с сертификата (фаза 63) */
  certificate?: boolean
}) {
  const propose = usePropose()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [cert, setCert] = useState<Record<string, string>>({})

  const valueOf = (field: DomainField) =>
    draft[field.name] ?? pending[`${model.label}.${field.name}`] ?? String(current?.[field.name] ?? '')

  const submit = () => {
    const rows: ProposeRow[] = fields
      .filter((f) => draft[f.name] !== undefined && draft[f.name] !== String(current?.[f.name] ?? ''))
      .map((f) => ({ model: model.label, field: f.name, value: draft[f.name] }))

    // Секции с сертификата (фаза 63): если ученик их заполнил, к баллу
    // добавляется официальная попытка. Домен тот же, поэтому в очередь
    // это уйдёт одной строкой — балл и секции подтвердятся вместе
    const filled = CERT_SECTIONS.filter((name) => (cert[name] ?? '').trim())
    if (certificate && filled.length > 0) {
      const attempt = (field: string, value: string) => ({
        model: 'students.ExamAttempt',
        field,
        value,
        new_object_key: 'certificate',
      })
      rows.push(attempt('exam_type', 'IELTS'))
      rows.push(attempt('date', cert.date || todayAlmaty()))
      if (draft.ielts_current) rows.push(attempt('total_score', draft.ielts_current))
      filled.forEach((name) => rows.push(attempt(name, cert[name].trim())))
    }

    if (rows.length === 0) {
      setOpen(false)
      return
    }
    propose.mutate(rows, {
      onSuccess: (result) => {
        if (result.accepted > 0) toast.success(t('Отправлено на проверку'))
        result.rejected.forEach((row) => toast.error(row.reason))
        setDraft({})
        setCert({})
        setOpen(false)
      },
    })
  }

  if (!open) {
    return (
      <div className="propose__toggle">
        <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
          {label ?? t('Внести данные')}
        </Button>
        {hint && <span className="muted propose__hint">{hint}</span>}
      </div>
    )
  }

  return (
    <div className="propose__form">
      <p className="muted propose__note">
        {t('Значение проверит директор — до этого оно помечено «на проверке у директора».')}
      </p>
      {fields.map((field) => (
        <label key={field.name} className="propose__field">
          <span className="muted propose__label">{t(field.title)}</span>
          {field.choices ? (
            <SelectField
              size="sm"
              value={valueOf(field)}
              onChange={(e) => setDraft((prev) => ({ ...prev, [field.name]: e.target.value }))}
            >
              <NativeSelectOption value="">{t('не выбрано')}</NativeSelectOption>
              {field.choices.map((choice) => (
                <NativeSelectOption key={choice.value} value={choice.value}>
                  {choice.title}
                </NativeSelectOption>
              ))}
            </SelectField>
          ) : (
            <Input
              value={valueOf(field)}
              placeholder={field.range_hint}
              onChange={(e) => setDraft((prev) => ({ ...prev, [field.name]: e.target.value }))}
            />
          )}
        </label>
      ))}
      {certificate && (
        <div className="propose__cert">
          <span className="muted propose__label">{t('Секции IELTS — с сертификата, если он на руках')}</span>
          <div className="propose__sections">
            {CERT_SECTIONS.map((name) => (
              <label key={name} className="propose__field">
                <span className="muted propose__label">{SECTION_LABELS[name]}</span>
                <Input
                  value={cert[name] ?? ''}
                  inputMode="decimal"
                  placeholder="0–9"
                  onChange={(e) => setCert((prev) => ({ ...prev, [name]: e.target.value }))}
                  aria-label={SECTION_LABELS[name]}
                />
              </label>
            ))}
          </div>
          <label className="propose__field">
            <span className="muted propose__label">{t('Дата сдачи по сертификату')}</span>
            <Input
              type="date"
              value={cert.date ?? ''}
              onChange={(e) => setCert((prev) => ({ ...prev, date: e.target.value }))}
              aria-label={t('Дата сдачи по сертификату')}
            />
          </label>
          <p className="muted propose__note">
            {t('Заполнять необязательно. Секции подтвердятся вместе с баллом — одной строкой.')}
          </p>
        </div>
      )}
      <div className="propose__actions">
        <Button size="sm" disabled={propose.isPending} onClick={submit}>
          {t('Отправить на проверку')}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
          {t('Отмена')}
        </Button>
      </div>
    </div>
  )
}

/**
 * Форма новой записи (достижение, олимпиада, соревнование).
 *
 * Файл-подтверждение сначала уходит в документы (закрытое хранилище),
 * а в предложение попадает ссылка на него — сама запись едет предложением
 * владельцу домена и до решения в базе не появляется.
 */
export function AddRowForm({
  model,
  fields,
  fixed,
  submitLabel,
  withFile,
}: {
  model: string
  fields: DomainField[]
  /** значения, которые форма не спрашивает: категория олимпиады и т.п. */
  fixed?: Record<string, string>
  submitLabel: string
  withFile?: boolean
}) {
  const propose = usePropose()
  const { uploadDocument } = useDocuments()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    const rows: ProposeRow[] = []
    const key = `new-${Date.now()}`
    for (const [field, value] of Object.entries({ ...fixed, ...draft })) {
      if (value !== '') rows.push({ model, field, value, new_object_key: key })
    }
    if (rows.length === Object.keys(fixed ?? {}).length) {
      toast.error(t('Заполните хотя бы название'))
      return
    }
    setBusy(true)
    try {
      if (file) {
        const doc = await uploadDocument.mutateAsync({
          file,
          doc_type: 'other',
          title: draft.title || draft.name || file.name,
        })
        rows.push({ model, field: 'proof_url', value: `/api/documents/${doc.id}/file/`, new_object_key: key })
      }
      propose.mutate(rows, {
        onSuccess: (result) => {
          if (result.accepted > 0) toast.success(t('Отправлено на проверку'))
          result.rejected.forEach((row) => toast.error(row.reason))
          setDraft({})
          setFile(null)
          setOpen(false)
        },
      })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <div className="propose__toggle">
        <Button size="sm" onClick={() => setOpen(true)}>
          {submitLabel}
        </Button>
      </div>
    )
  }

  return (
    <div className="propose__form">
      {fields.map((field) => (
        <label key={field.name} className="propose__field">
          <span className="muted propose__label">{t(field.title)}</span>
          {field.choices ? (
            <SelectField
              size="sm"
              value={draft[field.name] ?? ''}
              onChange={(e) => setDraft((prev) => ({ ...prev, [field.name]: e.target.value }))}
            >
              <NativeSelectOption value="">{t('не выбрано')}</NativeSelectOption>
              {field.choices.map((choice) => (
                <NativeSelectOption key={choice.value} value={choice.value}>
                  {choice.title}
                </NativeSelectOption>
              ))}
            </SelectField>
          ) : field.name === 'description' ? (
            <Textarea
              value={draft[field.name] ?? ''}
              rows={2}
              onChange={(e) => setDraft((prev) => ({ ...prev, [field.name]: e.target.value }))}
            />
          ) : (
            <Input
              type={field.type === 'date' ? 'date' : 'text'}
              value={draft[field.name] ?? ''}
              placeholder={field.range_hint}
              onChange={(e) => setDraft((prev) => ({ ...prev, [field.name]: e.target.value }))}
            />
          )}
        </label>
      ))}
      {withFile && (
        <div className="propose__field">
          <span className="muted propose__label">{t('Файл-подтверждение (не обязательно)')}</span>
          <Input type="file" accept=".pdf,.jpg,.jpeg,.png" aria-label={t('Файл-подтверждение')} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
      )}
      <div className="propose__actions">
        <Button size="sm" disabled={busy || propose.isPending} onClick={() => void submit()}>
          {t('Отправить на проверку')}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
          {t('Отмена')}
        </Button>
      </div>
    </div>
  )
}

/** Список записей раздела с пометкой «на проверке у директора» у отправленных. */
export function RowsList({
  rows,
  pendingRows,
  emptyText,
}: {
  rows: { id: number; label: string; note: string; byCurator?: boolean }[]
  pendingRows: { label: string; note: string }[]
  emptyText: string
}) {
  if (rows.length === 0 && pendingRows.length === 0) {
    return <p className="muted rows__empty">{emptyText}</p>
  }
  return (
    <ul className="rows__list">
      {pendingRows.map((row, index) => (
        <li key={`pending-${index}`} className="rows__item">
          <div className="rows__body">
            <span className="rows__label">
              {row.label} <Chip tone="neutral">{t('на проверке у директора')}</Chip>
            </span>
            {row.note && <span className="muted rows__note">{row.note}</span>}
          </div>
        </li>
      ))}
      {rows.map((row) => (
        <li key={row.id} className="rows__item">
          <div className="rows__body">
            <span className="rows__label">
              {row.label} {row.byCurator && <ByCurator />}
            </span>
            {row.note && <span className="muted rows__note">{row.note}</span>}
          </div>
        </li>
      ))}
    </ul>
  )
}

/**
 * Готовность документов на обзоре: чек-лист с загрузкой прямо в строке.
 *
 * До фазы 49 кнопка «Загрузить» переключала вкладку, и человек уходил
 * со страницы, чтобы вернуться обратно. Здесь файл выбирается в самой
 * строке чек-листа: тип документа уже известен из неё.
 */
/** «Внёс куратор»: значение внесли за ученика — он должен это видеть. Имени нет. */
export const ByCurator = () => <Chip tone="neutral">{t('внёс куратор')}</Chip>


/**
 * Карточка домена в кабинете ученика: ровно колонки таблицы владельца
 * домена (фаза 70), значения с пометками «на проверке у директора» и «внёс куратор»,
 * форма предложения для полей, которые ученик вносит сам.
 */
export function ProfileCard({
  code,
  domains,
  card,
  pending,
}: {
  code: string
  domains: Domain[]
  card: Record<string, Record<string, unknown>>
  pending: Record<string, string>
}) {
  const domain = domains.find((d) => d.code === code)
  if (!domain) return null
  const model = profileModelOf(domain)
  if (!model) return null
  const values = card[domain.code]
  // какие значения внёс куратор за ученика — признак приходит с профилем
  const enteredByCurator = ((values as { entered_by_curator?: string[] } | undefined)?.entered_by_curator ??
    []) as string[]
  // блок показывает ровно колонки таблицы владельца домена (фаза 70):
  // карточки под поля, которых в таблице нет, больше не заводим
  const shownFields = model.fields.filter((f) => f.card === 'main')
  if (shownFields.length === 0) return null
  const proposable = shownFields.filter((f) => f.student_proposable)
  return (
    <DataCard
      key={code}
      title={t(DOMAIN_TITLE[code] ?? domain.title)}
    >
      {/* Пары «подпись → значение»: подпись мелкой капителью серым,
          значение обычным весом. Крупными и жирными на этом экране
          остаются только числа в плитках академических результатов —
          до фазы 49 жирным было всё, и «Computer Science» наезжало
          на соседнюю подпись. Длинное значение занимает всю ширину */}
      <div className="portfolio__kv">
        {shownFields.map((field) => {
          const waiting = pending[`${model.label}.${field.name}`]
          const choice = field.choices?.find((c) => c.value === waiting)
          const value = waiting !== undefined ? choice?.title || waiting : shown(values, field)
          const wide = String(value).length > 18
          const byCurator = waiting === undefined && enteredByCurator.includes(field.name)
          return (
            <div key={field.name} className={`portfolio__pair${wide ? ' portfolio__pair--wide' : ''}`}>
              <span className="portfolio__k">{t(field.short || field.title)}</span>
              <span className={`portfolio__v${value === t('нет') ? ' portfolio__v--empty' : ''}`}>{value}</span>
              {waiting !== undefined && <Chip tone="neutral">{t('на проверке у директора')}</Chip>}
              {byCurator && <ByCurator />}
            </div>
          )
        })}
      </div>
      {proposable.length > 0 && (
        <ProposeForm model={model} fields={proposable} current={values} pending={pending} />
      )}
    </DataCard>
  )
}
