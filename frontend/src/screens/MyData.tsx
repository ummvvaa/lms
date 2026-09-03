/**
 * «Портфолио» — ученик рассказывает о себе, школа подтверждает (фаза 38).
 *
 * Обзор: процент заполнения (это «сколько вы о себе рассказали», а не
 * готовность к подаче), следующие шаги, профиль поступления и академические
 * результаты — плюс всё, что школа записала (инвариант №7: видно всё,
 * кроме трёх оценочных ярлыков, которых API ученику не отдаёт).
 *
 * Достижения, спорт и олимпиады вносит ученик — предложением владельцу
 * домена (фаза 37). Документы загружаются напрямую: это документы человека,
 * а не табличные данные, файл живёт вне корня веб-сервера.
 */
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  useAtGoal,
  useAttempts,
  useContacts,
  useDocuments,
  useExamGoals,
  useMyProfile,
  useMyProposals,
  useMyUniversities,
  usePortfolio,
  usePropose,
  useStudentRows,
  type MyProposal,
  type ProposeRow,
} from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import BadgesBlock from '../components/BadgesBlock'
import { useDomainMeta } from '../api/hooks'
import {
  profileModelOf,
  type Domain,
  type DomainField,
  type DomainMeta,
  type DomainModel,
} from '../api/types'
import { DataCard, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { Hero, Row, Rows } from '../components/patterns'
import Icon from '../layout/icons'
import './portfolio.css'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { NativeSelectOption } from '../components/ui/native-select'
import { SelectField } from '../components/SelectField'
import { Textarea } from '../components/ui/textarea'
import { t } from '../i18n'

type Tab = 'overview' | 'achievements' | 'documents' | 'sport' | 'olympiads' | 'cv'

/** Что видно в карточке: значение с подписью поля. */
function shown(profile: Record<string, unknown> | undefined, field: DomainField): string {
  if (field.type === 'reference') return String(profile?.[`${field.name}_name`] || '—')
  const value = profile?.[field.name]
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'да' : 'нет'
  const choice = field.choices?.find((c) => c.value === value)
  return choice ? choice.title : String(value)
}

const DOMAIN_TITLE: Record<string, string> = {
  behavior: 'Учёба и посещаемость',
  admission: 'Профиль поступления',
  exam: 'Ваши баллы',
  talent: 'Портфолио и таланты',
  sport: 'Спорт',
}

const DOMAIN_NOTE: Record<string, string> = {
  behavior: 'Ведёт директор школы',
  admission: 'Подтверждает директор по поступлению',
  exam: 'Подтверждает академический директор',
  talent: 'Подтверждает директор талантов',
  sport: 'Подтверждает директор спорта',
}

/** Модель по метке — из реестра, который отдаёт сервер. */
function modelOf(meta: DomainMeta | undefined, label: string): DomainModel | undefined {
  for (const domain of meta?.domains ?? []) {
    const found = domain.models.find((m) => m.label === label)
    if (found) return found
  }
  return undefined
}

/** Значения, отправленные и ждущие решения директора — по полям профилей. */
function pendingByField(proposals: MyProposal[]): Record<string, string> {
  const out: Record<string, string> = {}
  for (const proposal of proposals) {
    if (proposal.status !== 'pending') continue
    for (const change of proposal.changes) {
      if (change.new_object_key) continue
      out[`${change.model}.${change.field}`] = change.new_value
    }
  }
  return out
}

/** Новые записи (достижения, соревнования), ждущие решения. */
function pendingNewRows(proposals: MyProposal[], model: string): Record<string, string>[] {
  const groups: Record<string, Record<string, string>> = {}
  for (const proposal of proposals) {
    if (proposal.status !== 'pending') continue
    for (const change of proposal.changes) {
      if (!change.new_object_key || change.model !== model) continue
      const key = `${proposal.id}:${change.new_object_key}`
      groups[key] = { ...groups[key], [change.field]: change.new_value }
    }
  }
  return Object.values(groups)
}

/** Форма правки полей профиля: значения уходят предложением (фаза 37). */
function ProposeForm({
  model,
  fields,
  current,
  pending,
  label,
  hint,
}: {
  model: DomainModel
  fields: DomainField[]
  current: Record<string, unknown>
  pending: Record<string, string>
  /** подпись кнопки: «Внести баллы» у академических результатов */
  label?: string
  /** одна строка рядом с кнопкой — о том, что перехода не будет */
  hint?: string
}) {
  const propose = usePropose()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})

  const valueOf = (field: DomainField) =>
    draft[field.name] ?? pending[`${model.label}.${field.name}`] ?? String(current?.[field.name] ?? '')

  const submit = () => {
    const rows = fields
      .filter((f) => draft[f.name] !== undefined && draft[f.name] !== String(current?.[f.name] ?? ''))
      .map((f) => ({ model: model.label, field: f.name, value: draft[f.name] }))
    if (rows.length === 0) {
      setOpen(false)
      return
    }
    propose.mutate(rows, {
      onSuccess: (result) => {
        if (result.accepted > 0) toast.success(t('Отправлено на проверку'))
        result.rejected.forEach((row) => toast.error(row.reason))
        setDraft({})
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
        {t('Значение проверит директор — до этого оно помечено как «ждёт проверки».')}
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
              <NativeSelectOption value="">—</NativeSelectOption>
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
function AddRowForm({
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
              <NativeSelectOption value="">—</NativeSelectOption>
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
          <label className="filepick">
            <input
              type="file"
              accept=".pdf,.jpg,.jpeg,.png"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <Button variant="outline" size="sm" nativeButton={false} render={<span />}>
              {t('Выбрать файл')}
            </Button>
            <span className="muted filepick__name">{file ? file.name : t('Файл не выбран')}</span>
          </label>
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

/**
 * Цели по экзаменам (фаза 39): таблица «экзамен · цель · даты · сохранить».
 *
 * Строка на экзамен из справочника. Сохранение уходит предложением
 * академическому директору; от дат растут календарь и напоминания.
 */
function GoalsCard({ meta, proposals }: { meta: DomainMeta | undefined; proposals: MyProposal[] }) {
  const goals = useExamGoals()
  const atGoal = useAtGoal()
  const propose = usePropose()
  const [draft, setDraft] = useState<Record<string, Record<string, string>>>({})

  const model = modelOf(meta, 'students.ExamGoal')
  const exams = model?.fields.find((f) => f.name === 'exam')?.choices ?? []
  const rows = goals.data?.results ?? []

  // отправленное и нерешённое: новые цели по имени экзамена, правки — по записи
  const pendingNew = new Map<string, Record<string, string>>()
  const pendingEdits = new Map<string, Record<string, string>>()
  for (const proposal of proposals) {
    if (proposal.status !== 'pending') continue
    for (const change of proposal.changes) {
      if (change.model !== 'students.ExamGoal') continue
      if (change.new_object_key) {
        const key = `${proposal.id}:${change.new_object_key}`
        pendingNew.set(key, { ...pendingNew.get(key), [change.field]: change.new_value })
      } else if (change.object_id) {
        pendingEdits.set(change.object_id, {
          ...pendingEdits.get(change.object_id),
          [change.field]: change.new_value,
        })
      }
    }
  }
  const pendingByExam = new Map<string, Record<string, string>>()
  for (const fields of pendingNew.values()) {
    if (fields.exam) pendingByExam.set(fields.exam, fields)
  }

  const save = (examName: string) => {
    const values = draft[examName]
    // Кнопка не выключается: выключенная выглядит сломанной, и человек
    // не понимает, чего от него хотят. Пустую строку она объясняет словами
    if (!values || Object.values(values).every((v) => v === '')) {
      toast.error(t('Укажите балл или дату — тогда будет что отправить'))
      return
    }
    const existing = rows.find((row) => row.exam_name === examName)
    const rowsToSend: ProposeRow[] = Object.entries(values)
      .filter(([, value]) => value !== '')
      .map(([field, value]) =>
        existing
          ? { model: 'students.ExamGoal', field, value, object_id: String(existing.id) }
          : { model: 'students.ExamGoal', field, value, new_object_key: `goal-${examName}` },
      )
    if (!existing)
      rowsToSend.push({
        model: 'students.ExamGoal',
        field: 'exam',
        value: examName,
        new_object_key: `goal-${examName}`,
      })
    propose.mutate(rowsToSend, {
      onSuccess: (result) => {
        if (result.accepted > 0) toast.success(t('Отправлено на проверку'))
        result.rejected.forEach((row) => toast.error(row.reason))
        setDraft((prev) => ({ ...prev, [examName]: {} }))
      },
    })
  }

  return (
    <DataCard
      title={t('Цели по экзаменам')}
      note={t('Укажите желаемый балл и дату — сроки появятся в календаре и в плане')}
      accent="indigo"
    >
      {exams.map((exam) => {
        const existing = rows.find((row) => row.exam_name === exam.value)
        const waiting = pendingByExam.get(exam.value) ?? (existing && pendingEdits.get(String(existing.id)))
        const rowDraft = draft[exam.value] ?? {}
        const valueOf = (field: string, current: string | null) =>
          rowDraft[field] ?? waiting?.[field] ?? current ?? ''
        return (
          <div key={exam.value} className="goals__row" data-exam={exam.value}>
            <span className="goals__exam">
              {exam.title}
              {waiting && <Badge variant="mute">{t('ждёт проверки')}</Badge>}
            </span>
            <Input
              className="num goals__score"
              placeholder={t('Цель')}
              aria-label={`${t('Целевой балл')}: ${exam.title}`}
              value={valueOf('target_score', existing?.target_score ?? null)}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, [exam.value]: { ...rowDraft, target_score: e.target.value } }))
              }
            />
            <Input
              type="date"
              aria-label={`${t('Дата экзамена')}: ${exam.title}`}
              value={valueOf('exam_date', existing?.exam_date ?? null)}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, [exam.value]: { ...rowDraft, exam_date: e.target.value } }))
              }
            />
            <Input
              type="date"
              aria-label={`${t('Дата регистрации')}: ${exam.title}`}
              value={valueOf('registration_date', existing?.registration_date ?? null)}
              onChange={(e) =>
                setDraft((prev) => ({
                  ...prev,
                  [exam.value]: { ...rowDraft, registration_date: e.target.value },
                }))
              }
            />
            <Button className="goals__save" disabled={propose.isPending} onClick={() => save(exam.value)}>
              {t('Сохранить')}
            </Button>
          </div>
        )
      })}
      {atGoal.data?.available && atGoal.data.open_after > atGoal.data.open_before && (
        <p className="muted propose__note" style={{ marginTop: 12 }}>
          {t('Если сдадите на цель, по требованиям откроется программ:')}{' '}
          <b className="num">{atGoal.data.open_after}</b> (+{atGoal.data.open_after - atGoal.data.open_before}
          ). {t('Это соответствие требованиям, а не шанс поступления.')}
        </p>
      )}
    </DataCard>
  )
}

/** Список записей раздела с пометками «ждёт проверки» у отправленных. */
function RowsList({
  rows,
  pendingRows,
  emptyText,
}: {
  rows: { id: number; label: string; note: string }[]
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
              {row.label} <Badge variant="mute">{t('ждёт проверки')}</Badge>
            </span>
            {row.note && <span className="muted rows__note">{row.note}</span>}
          </div>
        </li>
      ))}
      {rows.map((row) => (
        <li key={row.id} className="rows__item">
          <div className="rows__body">
            <span className="rows__label">{row.label}</span>
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
function DocumentsCard({ checklist }: { checklist: { code: string; title: string; done: boolean }[] }) {
  const { uploadDocument } = useDocuments()
  const done = checklist.filter((row) => row.done).length

  const pick = (code: string, file: File | null) => {
    if (!file) return
    uploadDocument.mutate(
      { file, doc_type: code, note: '' },
      {
        onSuccess: () => toast.success(t('Документ загружен')),
        onError: (error) => toast.error(error.message),
      },
    )
  }

  return (
    <DataCard
      title={t('Готовность документов')}
      note={t('Что уже загружено и чего не хватает')}
      accent="ok"
      right={<Badge variant="ok" className="num">{`${done} ${t('из')} ${checklist.length}`}</Badge>}
    >
      <Rows>
        {checklist.map((row) => (
          <Row
            key={row.code}
            lead={
              <span
                className={`portfolio__check${row.done ? ' portfolio__check--on' : ''}`}
                aria-hidden="true"
              >
                {row.done ? <Icon name="check" size={11} /> : null}
              </span>
            }
            title={t(row.title)}
            right={
              row.done ? (
                <Badge variant="ok">{t('Загружен')}</Badge>
              ) : (
                <label className="filepick filepick--row">
                  <input
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png"
                    onChange={(event) => pick(row.code, event.target.files?.[0] ?? null)}
                  />
                  <Button variant="outline" size="sm" nativeButton={false} render={<span />}>
                    {t('Загрузить')}
                  </Button>
                </label>
              )
            }
          />
        ))}
      </Rows>
    </DataCard>
  )
}

function DocumentsTab() {
  const { query, uploadDocument, removeDocument } = useDocuments()
  const portfolio = usePortfolio()
  const [docType, setDocType] = useState('attestat')
  const [note, setNote] = useState('')
  const [file, setFile] = useState<File | null>(null)

  const rows = query.data?.results ?? []
  const checklist = portfolio.data?.documents ?? []

  const submit = () => {
    if (!file) {
      toast.error(t('Выберите файл'))
      return
    }
    uploadDocument.mutate(
      { file, doc_type: docType, note },
      {
        onSuccess: () => {
          toast.success(t('Документ загружен'))
          setFile(null)
          setNote('')
        },
        onError: (error) => toast.error(error.message),
      },
    )
  }

  return (
    <div className="grid grid--two">
      <DataCard
        title={t('Готовность документов')}
        note={t('Чек-лист: сразу видно, чего не хватает')}
        accent="indigo"
      >
        <ul className="rows__list">
          {checklist.map((row) => (
            <li key={row.code} className="rows__item">
              <div className="rows__body">
                <span className="rows__label">
                  {row.done ? '✓ ' : ''}
                  {t(row.title)}
                </span>
                {!row.done && <span className="muted rows__note">{t('не загружен')}</span>}
              </div>
            </li>
          ))}
        </ul>
      </DataCard>

      <DataCard
        title={t('Загрузить документ')}
        note={t('PDF, JPG или PNG — файл виден вам и школе')}
        accent="brand"
      >
        <div className="propose__form">
          <label className="propose__field">
            <span className="muted propose__label">{t('Тип документа')}</span>
            <SelectField size="sm" value={docType} onChange={(e) => setDocType(e.target.value)}>
              {[
                ...checklist.map((c) => ({ value: c.code, title: c.title })),
                { value: 'other', title: 'Прочее' },
              ].map((option) => (
                <NativeSelectOption key={option.value} value={option.value}>
                  {t(option.title)}
                </NativeSelectOption>
              ))}
            </SelectField>
          </label>
          <label className="propose__field">
            <span className="muted propose__label">{t('Примечание')}</span>
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <label className="filepick">
            <input
              type="file"
              accept=".pdf,.jpg,.jpeg,.png"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <Button variant="outline" size="sm" nativeButton={false} render={<span />}>
              {t('Выбрать файл')}
            </Button>
            <span className="muted filepick__name">{file ? file.name : t('Файл не выбран')}</span>
          </label>
          <div className="propose__actions">
            <Button size="sm" disabled={uploadDocument.isPending} onClick={submit}>
              {t('Загрузить')}
            </Button>
          </div>
        </div>
      </DataCard>

      <DataCard title={t('Мои документы')} count={rows.length} accent="teal">
        {rows.length === 0 && <p className="muted rows__empty">{t('Документов пока нет')}</p>}
        <ul className="rows__list">
          {rows.map((row) => (
            <li key={row.id} className="rows__item">
              <div className="rows__body">
                <span className="rows__label">
                  {row.doc_type_title}
                  {row.title ? ` · ${row.title}` : ''}
                </span>
                <span className="muted rows__note">
                  {new Date(row.created_at).toLocaleDateString('ru')}
                  {row.note ? ` · ${row.note}` : ''}
                </span>
              </div>
              <div className="propose__actions">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => window.open(`/api/documents/${row.id}/file/`)}
                >
                  {t('Открыть')}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={removeDocument.isPending}
                  onClick={() =>
                    removeDocument.mutate(row.id, {
                      onSuccess: () => toast.success(t('Документ в архиве')),
                      onError: (error) => toast.error(error.message),
                    })
                  }
                >
                  {t('Убрать')}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </DataCard>
    </div>
  )
}

export default function MyData() {
  const { me } = useAuth()
  const meta = useDomainMeta()
  const profile = useMyProfile()
  const portfolio = usePortfolio()
  const attempts = useAttempts()
  const universities = useMyUniversities()
  const rows = useStudentRows(me?.student_id ?? null)
  const contacts = useContacts({ student: me?.student_id ?? null })
  const proposals = useMyProposals()
  const [tab, setTab] = useState<Tab>('overview')

  const myProposals = useMemo(() => proposals.data?.results ?? [], [proposals.data])
  const pending = useMemo(() => pendingByField(myProposals), [myProposals])

  if (meta.isLoading || profile.isLoading || portfolio.isLoading) return <Loading kind="cards" />
  if (profile.error) return <ErrorNote error={profile.error} />
  if (!profile.data) return null

  const card = profile.data as unknown as Record<string, Record<string, unknown>>
  const domains: Domain[] = meta.data?.domains ?? []
  const state = portfolio.data
  const attemptRows = attempts.data?.results ?? []
  const activities = rows.data?.activities ?? []
  const competitions = rows.data?.competitions ?? []
  const contactRows = contacts.data?.results ?? []
  const declined = myProposals.filter((p) => p.status === 'rejected' && p.reject_reason)

  // Три числа для крупной карточки: сколько разделов начато, сколько
  // документов загружено и сколько предложений директора уже приняли
  const sections = state?.sections ?? []
  const totalSections = sections.length
  const filledSections = sections.filter((section) => section.value > 0).length
  const documentsDone = (state?.documents ?? []).filter((doc) => doc.done).length
  const confirmedCount = myProposals.filter((proposal) =>
    ['applied', 'partially_applied'].includes(proposal.status),
  ).length

  // поля академических результатов, которые ученик вправе предложить:
  // форма внесения баллов открывается прямо в карточке (фаза 49)
  const examDomain = domains.find((d) => d.code === 'exam')
  const examModel = examDomain ? profileModelOf(examDomain) : undefined
  const examProposable = (examModel?.fields ?? []).filter((f) => f.student_proposable)

  const activityModel = modelOf(meta.data, 'students.Activity')
  const competitionModel = modelOf(meta.data, 'students.Competition')

  const domainCard = (code: string) => {
    const domain = domains.find((d) => d.code === code)
    if (!domain) return null
    const model = profileModelOf(domain)
    if (!model) return null
    const values = card[domain.code]
    const proposable = model.fields.filter((f) => f.student_proposable)
    const accent = { behavior: 'brand', admission: 'indigo', exam: 'teal', talent: 'warn', sport: 'ok' }[
      code
    ] as 'brand' | 'indigo' | 'teal' | 'warn' | 'ok'
    return (
      <DataCard
        key={code}
        title={t(DOMAIN_TITLE[code] ?? domain.title)}
        note={t(DOMAIN_NOTE[code] ?? '')}
        accent={accent}
      >
        {/* Пары «подпись → значение»: подпись мелкой капителью серым,
            значение обычным весом. Крупными и жирными на этом экране
            остаются только числа в плитках академических результатов —
            до фазы 49 жирным было всё, и «Computer Science» наезжало
            на соседнюю подпись. Длинное значение занимает всю ширину */}
        <div className="portfolio__kv">
          {model.fields.map((field) => {
            const waiting = pending[`${model.label}.${field.name}`]
            const choice = field.choices?.find((c) => c.value === waiting)
            const value = waiting !== undefined ? choice?.title || waiting : shown(values, field)
            const wide = String(value).length > 18
            return (
              <div key={field.name} className={`portfolio__pair${wide ? ' portfolio__pair--wide' : ''}`}>
                <span className="portfolio__k">{t(field.short || field.title)}</span>
                <span className={`portfolio__v${value === '—' ? ' portfolio__v--empty' : ''}`}>{value}</span>
                {waiting !== undefined && <Badge variant="mute">{t('ждёт проверки')}</Badge>}
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

  const olympiadRows = activities.filter((a) => a.category === 'olympiad')
  const achievementRows = activities.filter((a) => a.category !== 'olympiad')
  const pendingActivities = pendingNewRows(myProposals, 'students.Activity')
  const pendingOlympiads = pendingActivities.filter((r) => r.category === 'olympiad')
  const pendingAchievements = pendingActivities.filter((r) => r.category !== 'olympiad')
  const pendingCompetitions = pendingNewRows(myProposals, 'students.Competition')

  return (
    <div>
      <ScreenHead
        title={t('Портфолио')}
        subtitle={t('Всё, что вы рассказали о себе, и всё, что записала школа.')}
        actions={
          <Button
            variant="outline"
            onClick={() => {
              window.location.href = '/api/portfolio/cv/'
            }}
          >
            {t('Экспорт CV')}
          </Button>
        }
      />

      {declined.length > 0 && (
        <div className="card card-pad card--accent card--warn propose__declined">
          <span className="eyebrow">{t('Возвращено на доработку')}</span>
          <ul className="propose__declinedlist">
            {declined.slice(0, 5).map((proposal) => (
              <li key={proposal.id}>
                <b>{proposal.changes.map((c) => t(c.field_title)).join(', ')}</b>
                <span className="muted"> — {proposal.reject_reason}. </span>
                <span className="muted">{t('Поправьте и внесите заново в карточке ниже.')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <ScreenTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'overview', label: t('Обзор') },
          { value: 'achievements', label: t('Достижения') },
          { value: 'documents', label: t('Документы') },
          { value: 'sport', label: t('Спорт') },
          { value: 'olympiads', label: t('Олимпиады') },
          { value: 'cv', label: 'CV' },
        ]}
      />

      {tab === 'overview' && (
        <div className="portfolio__two">
          {/* Слева — то, что ученик вносит: баллы, цели, документы; справа —
              то, по чему он себя сверяет: заполненность, профиль поступления
              и список вузов. До фазы 49 всё это стояло одной колонкой,
              и правая половина экрана оставалась пустой */}
          <div className="portfolio__main">
            <DataCard
              title={t('Академические результаты')}
              note={t('Внесите значения — директор подтвердит')}
              accent="teal"
              right={<Badge variant="mute">{t('Подтверждает академический директор')}</Badge>}
            >
              <div className="portfolio__academics">
                <div className="portfolio__score">
                  <span className="portfolio__scorelabel">GPA</span>
                  <b className="num portfolio__scorevalue">{state?.academics.gpa ?? '—'}</b>
                  <span className="portfolio__scorenote">{t('из 4.0')}</span>
                </div>
                <div className="portfolio__score">
                  <span className="portfolio__scorelabel">IELTS</span>
                  <b className="num portfolio__scorevalue">{state?.academics.ielts ?? '—'}</b>
                  <span className="portfolio__scorenote">
                    {state?.academics.ielts ? t('внесён') : t('не внесён')}
                  </span>
                </div>
                <div className="portfolio__score">
                  <span className="portfolio__scorelabel">SAT</span>
                  <b className="num portfolio__scorevalue">{state?.academics.sat ?? '—'}</b>
                  <span className="portfolio__scorenote">
                    {state?.academics.sat ? t('внесён') : t('не внесён')}
                  </span>
                </div>
                <div className="portfolio__score">
                  <span className="portfolio__scorelabel">{t('ЕНТ')}</span>
                  <b className="num portfolio__scorevalue">{state?.academics.ent ?? '—'}</b>
                  <span className="portfolio__scorenote">
                    {state?.academics.ent ? t('внесён') : t('не внесён')}
                  </span>
                </div>
              </div>
              {/* Форма открывается прямо здесь: до фазы 49 кнопка внесения
                  уводила на другой экран, откуда надо было возвращаться */}
              {examModel && examProposable.length > 0 && (
                <ProposeForm
                  model={examModel}
                  fields={examProposable}
                  current={card.exam}
                  pending={pending}
                  label={t('Внести баллы')}
                  hint={t('Откроется форма прямо здесь, без перехода')}
                />
              )}
            </DataCard>

            <GoalsCard meta={meta.data} proposals={myProposals} />

            <DocumentsCard checklist={state?.documents ?? []} />

            <DataCard
              title={t('Достижения')}
              note={t('Проекты, конкурсы, волонтёрство')}
              count={achievementRows.length + pendingAchievements.length}
              accent="warn"
              right={
                <Button variant="outline" size="sm" onClick={() => setTab('achievements')}>
                  {t('Смотреть всё')}
                </Button>
              }
            >
              {achievementRows.length + pendingAchievements.length === 0 && (
                <p className="muted rows__empty">{t('Пока пусто — первое достижение вносится вами')}</p>
              )}
              <Rows>
                {achievementRows.slice(0, 4).map((row) => (
                  <Row
                    key={row.id}
                    icon="star"
                    tone="warn"
                    title={row.title}
                    note={[row.subject_name, row.date && new Date(row.date).toLocaleDateString('ru')]
                      .filter(Boolean)
                      .join(' · ')}
                  />
                ))}
              </Rows>
            </DataCard>

            <DataCard
              title={t('Сданные экзамены и пробные')}
              note={t('Каждая попытка с датой и баллом')}
              count={attemptRows.length}
              accent="teal"
            >
              {attemptRows.length === 0 && (
                <p className="muted rows__empty">{t('Попыток пока нет — они появятся после первой сдачи')}</p>
              )}
              <Rows>
                {attemptRows.slice(0, 10).map((row) => (
                  <Row
                    key={row.id}
                    icon="target"
                    tone="teal"
                    title={`${row.exam_type} ${row.total_score ?? '—'}`}
                    note={`${new Date(row.date).toLocaleDateString('ru')} · ${
                      row.attempt_format === 'mock' ? t('пробный') : t('официальный')
                    }`}
                  />
                ))}
              </Rows>
            </DataCard>

            {domainCard('exam')}
            {domainCard('behavior')}
            {domainCard('talent')}
            {domainCard('sport')}

            <DataCard
              title={t('Контакты родителей')}
              note={t('Кого школа набирает по вашим вопросам')}
              count={contactRows.length}
              accent="brand"
            >
              {contactRows.length === 0 && (
                <p className="muted rows__empty">{t('Контактов пока не записано')}</p>
              )}
              <Rows>
                {contactRows.map((row) => (
                  <Row
                    key={row.id}
                    icon="person"
                    tone="brand"
                    title={`${row.full_name}${row.is_primary ? ` · ${t('основной')}` : ''}`}
                    note={[row.relation_title, row.phone].filter(Boolean).join(' · ')}
                  />
                ))}
              </Rows>
            </DataCard>
          </div>

          <div className="portfolio__side">
            {/* Заполненность: процент, полоса и что именно заполнить.
                Это «сколько рассказал», а не готовность к подаче —
                величины разные, и путать их нельзя */}
            <DataCard
              title={`${t('Заполнено на')} ${state?.percent ?? 0}%`}
              note={t('Сколько вы о себе рассказали')}
              accent="brand"
            >
              <div className="bar portfolio__fillbar">
                {/* цвет полосы задаётся явно: у `.bar > i` своего фона нет,
                    и без него заполненная часть невидима */}
                <i style={{ width: `${state?.percent ?? 0}%`, background: 'var(--brand)' }} />
              </div>
              {(state?.next_steps ?? []).length === 0 && (
                <p className="muted rows__empty">{t('Всё заполнено — портфолио рассказано целиком')}</p>
              )}
              <Rows>
                {(state?.next_steps ?? []).map((step, index) => (
                  <Row
                    key={index}
                    title={t(step.text)}
                    right={<Badge variant="warn">{t('Нет')}</Badge>}
                    onOpen={() => setTab(step.tab as Tab)}
                    openLabel={t('Заполнить')}
                  />
                ))}
              </Rows>
              <div className="portfolio__fillfacts">
                <div>
                  <span className="eyebrow">{t('Заполнено')}</span>
                  <b className="num">
                    {filledSections} {t('из')} {totalSections}
                  </b>
                </div>
                <div>
                  <span className="eyebrow">{t('Документов')}</span>
                  <b className="num">{documentsDone}</b>
                </div>
                <div>
                  <span className="eyebrow">{t('Подтверждено')}</span>
                  <b className="num">{confirmedCount}</b>
                </div>
              </div>
            </DataCard>

            {domainCard('admission')}

            <DataCard
              title={t('Вузы в вашем списке')}
              note={t('И насколько вы подходите по требованиям')}
              count={universities.data?.length ?? 0}
              accent="indigo"
            >
              {(universities.data?.length ?? 0) === 0 && (
                <p className="muted rows__empty">{t('Список пуст — выберите программы в каталоге')}</p>
              )}
              <Rows>
                {(universities.data ?? []).slice(0, 10).map((row) => (
                  <Row
                    key={row.program}
                    title={row.university_name}
                    note={row.program_name}
                    right={
                      <span className="num portfolio__percent">
                        {row.percent}
                        {t('% соответствия')}
                      </span>
                    }
                  />
                ))}
              </Rows>
            </DataCard>
          </div>
        </div>
      )}

      {tab === 'achievements' && (
        <div className="grid grid--two">
          <DataCard
            title={t('Достижения')}
            note={t('Проекты, конкурсы, волонтёрство — подтверждает директор талантов')}
            count={achievementRows.length}
            accent="warn"
          >
            <RowsList
              rows={achievementRows.map((row) => ({
                id: row.id,
                label: row.title,
                note: row.is_confirmed ? t('подтверждено') : t('ждёт подтверждения'),
              }))}
              pendingRows={pendingAchievements.map((row) => ({ label: row.title ?? '', note: '' }))}
              emptyText={t('Достижений пока нет — добавьте первое')}
            />
            {activityModel && (
              <AddRowForm
                model="students.Activity"
                fields={activityModel.fields.filter(
                  (f) => f.student_proposable && !['subject', 'proof_url'].includes(f.name),
                )}
                submitLabel={t('Добавить достижение')}
                withFile
              />
            )}
          </DataCard>
          {/* бейджи школы — рядом, но своим именем: два блока «Достижения»
              на одном экране путают (фаза 46) */}
          <BadgesBlock limit={4} />
        </div>
      )}

      {tab === 'sport' && (
        <div className="grid grid--two">
          {domainCard('sport')}
          <DataCard
            title={t('Спортивные соревнования')}
            note={t('Подтверждает директор спорта')}
            count={competitions.length}
            accent="ok"
          >
            <RowsList
              rows={competitions.map((row) => ({ id: row.id, label: row.name, note: row.result || '' }))}
              pendingRows={pendingCompetitions.map((row) => ({
                label: row.name ?? '',
                note: row.result ?? '',
              }))}
              emptyText={t('Соревнований пока нет')}
            />
            {competitionModel && (
              <AddRowForm
                model="students.Competition"
                fields={competitionModel.fields.filter((f) => f.student_proposable && f.name !== 'proof_url')}
                submitLabel={t('Добавить соревнование')}
                withFile
              />
            )}
          </DataCard>
        </div>
      )}

      {tab === 'olympiads' && (
        <div className="grid grid--two">
          <DataCard
            title={t('Олимпиады')}
            note={t('Предмет, этап и результат — подтверждает директор талантов')}
            count={olympiadRows.length}
            accent="warn"
          >
            <RowsList
              rows={olympiadRows.map((row) => ({
                id: row.id,
                label: row.title,
                note: [row.subject_name, row.is_confirmed ? t('подтверждено') : t('ждёт подтверждения')]
                  .filter(Boolean)
                  .join(' · '),
              }))}
              pendingRows={pendingOlympiads.map((row) => ({
                label: row.title ?? '',
                note: row.subject ?? '',
              }))}
              emptyText={t('Олимпиад пока нет — даже школьный этап считается')}
            />
            {activityModel && (
              <AddRowForm
                model="students.Activity"
                fields={activityModel.fields.filter(
                  (f) => f.student_proposable && !['category', 'proof_url'].includes(f.name),
                )}
                fixed={{ category: 'olympiad' }}
                submitLabel={t('Добавить олимпиаду')}
                withFile
              />
            )}
          </DataCard>
        </div>
      )}

      {tab === 'documents' && <DocumentsTab />}

      {/* CV собирается на сервере из портфолио и на нём не хранится:
          профиль меняется каждый день, копия резюме устаревала бы молча */}
      {tab === 'cv' && (
        <div className="portfolio__col">
          <Hero
            tone="indigo"
            eyebrow={t('Резюме')}
            title={t('CV собирается из портфолио')}
            note={t(
              'Всё внесённое — учёба, достижения, спорт и олимпиады — в одном документе. Он собирается заново при каждой выгрузке, поэтому всегда свежий.',
            )}
            figure="dots"
            action={
              <Button
                onClick={() => {
                  window.location.href = '/api/portfolio/cv/'
                }}
              >
                {t('Открыть CV')}
              </Button>
            }
          />
          <DataCard title={t('Что попадёт в CV')} note={t('Разделы портфолио и их заполненность')}>
            <Rows>
              {sections.map((section) => (
                <Row
                  key={section.code}
                  icon="checklist"
                  tone={section.value > 0 ? 'ok' : 'mute'}
                  title={t(section.title)}
                  right={<span className="num portfolio__percent">{section.value}%</span>}
                />
              ))}
            </Rows>
          </DataCard>
        </div>
      )}
    </div>
  )
}
