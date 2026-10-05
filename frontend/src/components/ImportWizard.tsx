/**
 * Мастер импорта — один на все домены (фаза 72).
 *
 * До 72-й у таблицы поступления был свой мастер, а человек жал
 * «Применить» вслепую: что в какое поле и чей домен ляжет, экран
 * не показывал. Теперь четыре шага, и главный — второй:
 *
 * 1. файл — xlsx или csv, шаблон и формат, сразу листы и группы;
 * 2. что заполняем — таблица «колонка → поле → домен → владелец →
 *    строк с данными» из реестра, чипы доменов, нераспознанное поимённо,
 *    счёт «будет записано»;
 * 3. проверка строк — ошибки, правка, пропуск, фильтр «только с ошибками»;
 * 4. готово — отчёт по доменам, пропуски по видам, выгрузка, карточка.
 *
 * Владелец домена видит все колонки, но чужие помечены «домен не ваш,
 * будет пропущен» — что можно, говорит сервер (`writable_domains`), экран
 * права не считает. Правила разбора живут в реестре и здесь не трогаются.
 */
import ExportButton from './ExportPreview'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import {
  useAdmissionApply,
  useAdmissionPreview,
  useStudyGroups,
  type AdmissionImportReport,
  type AdmissionPreview,
} from '../api/hooks'
import { downloadFile } from '../api/client'
import { Chip, DataCard, ErrorNote, withNumbers } from './ui'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Checkbox } from './ui/checkbox'
import { SelectField } from './SelectField'
import WizardSteps from './WizardSteps'
import DataTable from './DataTable'
import { t, tk, tn } from '../i18n'

type Fix = { key: string; student?: number | null; skip?: boolean }
type Step = 1 | 2 | 3 | 4

const STEPS: { step: Step; title: string }[] = [
  { step: 1, title: tk('Файл') },
  { step: 2, title: tk('Что заполняем') },
  { step: 3, title: tk('Проверка строк') },
  { step: 4, title: tk('Готово') },
]

/** Вид строки отчёта «по домену», как его пишет сервер, — сравнение, человеку не показывается. */
// eslint-disable-next-line i18n-text -- метка вида строки из ответа сервера, не показывается
const DOMAIN_ROW = 'домен'

type WizardColumn = AdmissionPreview['columns'][number]
type SheetRow = AdmissionPreview['sheets'][number]['rows'][number]

export default function ImportWizard() {
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>(1)
  const [file, setFile] = useState<File | null>(null)
  const [group, setGroup] = useState('')
  const [preview, setPreview] = useState<AdmissionPreview | null>(null)
  const [chosen, setChosen] = useState<string[]>([])
  const [fixes, setFixes] = useState<Record<string, Fix>>({})
  // назначения человека: заголовок файла → колонка реестра; пусто — «не загружать»
  const [assigned, setAssigned] = useState<Record<string, string>>({})
  const [onlyBad, setOnlyBad] = useState(false)
  const [report, setReport] = useState<AdmissionImportReport | null>(null)
  const check = useAdmissionPreview()
  const apply = useAdmissionApply()
  const groups = useStudyGroups()

  const fixList = (next = fixes): Fix[] => Object.values(next).filter((fix) => fix.skip || fix.student)

  const run = (selected: File, nextFixes: Fix[] = [], forGroup = group, nextAssigned = assigned, resetDomains = false) => {
    setReport(null)
    check.mutate(
      { file: selected, fixes: nextFixes, group: forGroup, assigned: nextAssigned },
      {
        onSuccess: (data) => {
          setPreview(data)
          setFile(selected)
          // по умолчанию выбраны все найденные домены — из тех, что можно этому человеку;
          // новый файл и новое назначение колонки пересобирают выбор: домены могли смениться
          setChosen((old) => (resetDomains || !old.length ? data.writable_domains : old))
        },
        onError: (error) => {
          setPreview(null)
          toast.error(error.message)
        },
      },
    )
  }

  const setFix = (key: string, fix: Fix) => {
    const next = { ...fixes, [key]: { ...fix, key } }
    setFixes(next)
    if (file) run(file, fixList(next))
  }

  // колонку, которую мастер не узнал или узнал не так, человек назначает сам:
  // файл разбирается заново, домены пересчитываются
  const assign = (header: string, key: string) => {
    const next = { ...assigned, [header]: key }
    setAssigned(next)
    if (file) run(file, fixList(), group, next, true)
  }

  // одна кривая строка не держит файл: все строки с ошибкой пропускаются разом,
  // остальные загружаются — так работала вкладка «Поля по CSV»
  const skipAllBad = () => {
    if (!preview || !file) return
    const next = { ...fixes }
    for (const sheet of preview.sheets)
      for (const row of sheet.rows) {
        const key = `${sheet.name}:${row.index}`
        if (row.error && !row.skip) next[key] = { key, skip: true }
      }
    setFixes(next)
    run(file, fixList(next))
  }

  const applyAll = () => {
    if (!file) return
    apply.mutate(
      { file, fixes: fixList(), group, domains: chosen, assigned },
      {
        onSuccess: (data) => {
          setReport(data)
          setStep(4)
          toast.success(`${t('Обновлено учеников:')} ${data.students_updated}`)
        },
        onError: (error) => toast.error(error.message),
      },
    )
  }

  const toggleDomain = (code: string) =>
    setChosen((old) => (old.includes(code) ? old.filter((c) => c !== code) : [...old, code]))

  // счёт внизу шага 2: поля выбранных доменов и строки, которые они затронут
  const summary = useMemo(() => {
    if (!preview) return { fields: 0, domains: 0, rows: 0 }
    const active = preview.columns.filter((c) => chosen.includes(c.domain))
    return {
      fields: active.length,
      domains: new Set(active.map((c) => c.domain)).size,
      rows: preview.counts.ready,
    }
  }, [preview, chosen])

  const counts = preview?.counts
  const errorsLeft = counts ? counts.errors : 0
  // строки ручного назначения: неузнанные заголовки и те, что человек уже назначил
  const assignRows = useMemo(() => [...new Set([...Object.keys(assigned), ...(preview?.unknown_columns ?? [])])], [assigned, preview])
  // список выбора — весь реестр сервера, по доменам; «Ученик» и ФИО — отдельной группой
  const assignGroups = useMemo(() => {
    const groups = new Map<string, { key: string; title: string }[]>()
    for (const option of preview?.assignable ?? []) {
      const title = option.domain_title || t('Ученик')
      groups.set(title, [...(groups.get(title) ?? []), option])
    }
    return [...groups.entries()].map(([title, options]) => ({ title, options }))
  }, [preview])

  return (
    <>
      <WizardSteps steps={STEPS.map((row) => t(row.title))} current={step} />

      {step === 1 && (
        <DataCard
          title={t('Файл')}
          note={t('Таблица с ФИО: лист книги Excel — учебная группа, для CSV группу выбирают здесь. Список с почтой или логином ученика — любой лист или CSV, группа не нужна')}
        >
          <div className="toolbar">
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                void downloadFile('/admission-imports/template/', 'shablon-importa.xlsx').catch(
                  (error: Error) => toast.error(error.message),
                )
              }
            >
              {t('Шаблон')}
            </Button>
            <span className="muted">
              {t('Формат: колонки узнаются по заголовкам, пустая ячейка ничего не стирает — guides/ADMISSION_IMPORT.md и guides/FIELDS_IMPORT.md в репозитории')}
            </span>
          </div>
          <label className="wizard__group">
            <span className="eyebrow">{t('Группа для CSV')}</span>
            <SelectField aria-label={t('Группа для CSV')} value={group} onChange={(e) => setGroup(e.target.value)}>
              <option value="">{t('— для книги Excel и списка по почте не нужна —')}</option>
              {(groups.data?.results ?? []).map((row) => (
                <option key={row.id} value={row.code}>
                  {row.code}
                </option>
              ))}
            </SelectField>
          </label>
          <label className="filepick">
            <Input
              type="file"
              accept=".xlsx,.xlsm,.csv"
              onChange={(event) => {
                const selected = event.target.files?.[0]
                if (selected) {
                  setFixes({})
                  setChosen([])
                  setAssigned({})
                  run(selected, [], group, {}, true)
                }
              }}
            />
            <Button size="sm" nativeButton={false} render={<span />}>
              {t('Выбрать файл')}
            </Button>
            <span className="muted filepick__name">{file ? file.name : t('Файл не выбран')}</span>
          </label>
          {check.isPending && <p className="muted">{t('Читаю файл…')}</p>}
          {check.error && <ErrorNote error={check.error} />}
          <p className="muted">
            {t('Пароли из таблицы шифруются при загрузке. На этом экране они не показываются.')}
          </p>

          {preview && counts && (
            <>
              <div className="toolbar">
                <Chip tone="neutral" className="num">
                  {t('Листов:')} {counts.sheets}
                </Chip>
                <Chip tone="neutral" className="num">
                  {t('Строк:')} {counts.rows}
                </Chip>
                {/* у списка по почте или логину групп нет: предупреждать о них незачем */}
                {(preview.groups.length > 0 || !preview.list_rows) && (
                  <Chip tone={preview.groups.length ? 'good' : 'warn'}>
                    {t('Группы:')} {preview.groups.join(', ') || t('не распознаны')}
                  </Chip>
                )}
                {preview.list_rows > 0 && (
                  <Chip tone="good" className="num">
                    {t('Список по почте или логину:')} {preview.list_rows}
                  </Chip>
                )}
                {counts.sheets_skipped > 0 && (
                  <Chip tone="warn" className="num">
                    {t('Листов без группы:')} {counts.sheets_skipped}
                  </Chip>
                )}
                <span className="toolbar__spacer" />
                {/* строк нет, но есть неузнанные колонки — дальше можно: колонку ученика назначают на шаге 2 */}
                <Button size="sm" onClick={() => setStep(2)} disabled={counts.rows === 0 && preview.unknown_columns.length === 0}>
                  {t('Дальше')}
                </Button>
              </div>
            </>
          )}
        </DataCard>
      )}

      {step === 2 && preview && (
        <DataCard title={t('Что заполняем')} note={t('Колонка → поле → домен: из реестра соответствий')}>
          {/* чипы доменов: выбрать или снять; чужой домен снять нельзя — он и так не пишется */}
          <div className="wizard__chips">
            {preview.domains.map((code) => {
              const column = preview.columns.filter((c) => c.domain === code)
              const mine = preview.writable_domains.includes(code)
              const on = chosen.includes(code)
              return (
                <Button
                  key={code}
                  variant={on ? 'default' : 'outline'}
                  size="sm"
                  disabled={!mine}
                  aria-pressed={on}
                  title={mine ? undefined : t('домен не ваш, будет пропущен')}
                  onClick={() => toggleDomain(code)}
                >
                  {column[0]?.domain_title ?? code} <b className="num">{column.length}</b>
                </Button>
              )
            })}
          </div>

          <DataTable
            columns={[
              { key: 'title', title: t('Колонка в файле'), width: '26%', cell: (column: WizardColumn) => column.header || column.title },
              {
                key: 'field',
                title: t('Поле'),
                width: '24%',
                cell: (column: WizardColumn) => (
                  <span className="acad__wrapline">
                    {column.field_title}
                    {column.header && !(column.header in assigned) && (
                      <Button variant="link" size="sm" onClick={() => assign(column.header, column.key)}>
                        {t('Переназначить')}
                      </Button>
                    )}
                  </span>
                ),
              },
              { key: 'domain', title: t('Домен'), width: '16%', cell: (column: WizardColumn) => column.domain_title },
              { key: 'owner', title: t('Владелец'), width: '14%', cell: (column: WizardColumn) => column.owner },
              {
                key: 'rows',
                title: t('Строк с данными'),
                width: '20%',
                align: 'right',
                cell: (column: WizardColumn) => {
                  const mine = preview.writable_domains.includes(column.domain)
                  const on = mine && chosen.includes(column.domain)
                  return (
                    <>
                      <span className="num">{column.rows_with_data}</span>
                      {!mine && <Chip size="sm">{t('домен не ваш, будет пропущен')}</Chip>}
                      {mine && !on && <Chip size="sm">{t('не будет записано')}</Chip>}
                    </>
                  )
                },
              },
            ]}
            rows={preview.columns}
            rowKey={(column) => column.key}
          />

          {/* колонки, которые мастер не узнал, и те, что человек взялся переназначить:
              у каждой — список всего реестра соответствий; без назначения колонка пропускается */}
          {assignRows.length > 0 && (
            <>
              <p className="muted wizard__unknown">
                {t('Эти колонки мастер не узнал или вы переназначаете их сами. Выберите, куда положить колонку; без выбора она будет пропущена.')}
              </p>
              <DataTable
                fit
                columns={[
                  { key: 'header', title: t('Колонка в файле'), width: '40%', cell: (header: string) => header },
                  {
                    key: 'target',
                    title: t('Куда положить'),
                    width: '60%',
                    cell: (header: string) => (
                      <SelectField aria-label={header} value={assigned[header] ?? ''} disabled={check.isPending} onChange={(event) => assign(header, event.target.value)}>
                        <option value="">{t('— не загружать —')}</option>
                        {assignGroups.map((group) => (
                          <optgroup key={group.title} label={group.title}>
                            {group.options.map((option) => (
                              <option key={option.key} value={option.key}>
                                {option.title}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </SelectField>
                    ),
                  },
                ]}
                rows={assignRows}
                rowKey={(header) => header}
              />
            </>
          )}

          <div className="toolbar">
            <span className="wizard__sum">
              {withNumbers(t('Будет записано — полей: {fields}, доменов: {domains}, строк: {rows}'), summary)}
            </span>
            <span className="toolbar__spacer" />
            <Button size="sm" variant="outline" onClick={() => setStep(1)}>
              {t('Назад')}
            </Button>
            <Button size="sm" onClick={() => setStep(3)} disabled={summary.fields === 0}>
              {t('Дальше')}
            </Button>
          </div>
        </DataCard>
      )}

      {step === 3 && preview && counts && (
        <DataCard title={t('Проверка строк')} note={`${t('Листов:')} ${counts.sheets}`}>
          <div className="toolbar">
            <Chip tone="good" className="num">
              {t('Строк готово:')} {counts.ready}
            </Chip>
            {counts.errors > 0 && (
              <Chip tone="warn" className="num">
                {t('Строк с ошибкой:')} {counts.errors}
              </Chip>
            )}
            {counts.overwrites > 0 && (
              <Chip tone="info" className="num">
                {t('Перезапишется:')} {counts.overwrites}
              </Chip>
            )}
            <label className="users__check">
              <Checkbox checked={onlyBad} onCheckedChange={(on) => setOnlyBad(Boolean(on))} />
              {t('только с ошибками')}
            </label>
            <span className="toolbar__spacer" />
            {errorsLeft > 0 && (
              <Button size="sm" variant="outline" disabled={check.isPending} onClick={skipAllBad}>
                {t('Пропустить строки с ошибкой')}
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setStep(2)}>
              {t('Назад')}
            </Button>
            {/* пока есть неразобранные ошибки — не применяем: строку правят или пропускают */}
            <Button size="sm" disabled={apply.isPending || counts.ready === 0 || errorsLeft > 0} onClick={applyAll}>
              {t('Применить')}
            </Button>
          </div>
          {errorsLeft > 0 && (
            <p className="muted">{t('Пока есть строки с ошибкой, применить нельзя: отнесите их ученику или пропустите')}</p>
          )}

          {preview.sheets.map((sheet) => (
            <div key={sheet.name} className="aimp__sheet">
              <h3 className="aimp__title">
                {sheet.name}
                {sheet.error ? (
                  <Chip tone="warn">{sheet.error}</Chip>
                ) : (
                  <span className="muted">
                    {sheet.by_key
                      ? t('список по почте или логину · готово {ready} · пропуск {skipped}', { ready: sheet.ready, skipped: sheet.skipped })
                      : t('группа {group} · готово {ready} · пропуск {skipped}', {
                          group: sheet.group_code,
                          ready: sheet.ready,
                          skipped: sheet.skipped,
                        })}
                  </span>
                )}
              </h3>
              {sheet.rows.length > 0 && (
                <DataTable
                  columns={[
                    { key: 'n', title: t('Строка'), width: '8%', align: 'right', cell: (row: SheetRow) => <span className="num">{row.index}</span> },
                    { key: 'raw', title: sheet.by_key ? t('Почта или логин в файле') : t('ФИО в таблице'), width: '20%', cell: (row: SheetRow) => row.raw_name },
                    {
                      key: 'student',
                      title: t('Ученик'),
                      width: '26%',
                      cell: (row: SheetRow) => {
                        const key = `${sheet.name}:${row.index}`
                        if (row.skip) return <span className="t-note">{t('пропущена')}</span>
                        return (
                          <div className="aimp__fix">
                            {row.student_name ? (
                              <span>{row.student_name}</span>
                            ) : row.candidates.length === 0 ? (
                              // по почте или логину ученик либо найден, либо нет: выбирать не из кого
                              <span className="t-note">{t('не найден')}</span>
                            ) : (
                              <SelectField aria-label={t('Кому отнести строку')} value={String(fixes[key]?.student ?? '')} onChange={(event) => setFix(key, { key, student: event.target.value ? Number(event.target.value) : null })}>
                                <option value="">{t('— выберите ученика —')}</option>
                                {row.candidates.map((candidate) => (
                                  <option key={candidate.student} value={candidate.student}>
                                    {candidate.full_name}
                                  </option>
                                ))}
                              </SelectField>
                            )}
                            {row.error && (
                              <Button size="sm" variant="ghost" onClick={() => setFix(key, { key, skip: true })}>
                                {t('Пропустить')}
                              </Button>
                            )}
                          </div>
                        )
                      },
                    },
                    {
                      key: 'found',
                      title: t('Что нашлось'),
                      width: '24%',
                      cell: (row: SheetRow) =>
                        [
                          row.phone,
                          row.gpa === null ? '' : `GPA ${row.gpa}`,
                          row.scores.map((score) => `${score.exam} ${score.value}`).join(' · '),
                          row.links.length ? tn(row.links.length, '{n} ссылка|{n} ссылки|{n} ссылок') : '',
                          row.has_email_password || row.has_common_app_password ? t('пароли есть') : '',
                          ...row.fields.map((field) => `${field.title}: ${field.value}`),
                        ]
                          .filter(Boolean)
                          .join(' · ') || <span className="t-note">{t('ничего')}</span>,
                    },
                    {
                      key: 'notes',
                      title: t('Замечания'),
                      width: '22%',
                      cell: (row: SheetRow) => (
                        <>
                          {row.error && (
                            <Chip tone="warn" size="sm">
                              {row.error}
                            </Chip>
                          )}
                          {row.warnings.map((warning) => (
                            <div key={warning} className="t-note">
                              {warning}
                            </div>
                          ))}
                          {row.overwrites.map((change) => (
                            <div key={change.key} className="t-note">
                              {t('Перезапишется: {field} {old} → {new}', { field: change.title, old: change.old, new: change.new })}
                            </div>
                          ))}
                        </>
                      ),
                    },
                  ]}
                  rows={sheet.rows.filter((row) => !onlyBad || row.error)}
                  rowKey={(row) => `${sheet.name}:${row.index}`}
                  rowClass={(row) => (row.error ? 'aimp__row--bad' : undefined)}
                />
              )}
            </div>
          ))}
        </DataCard>
      )}

      {step === 4 && report && (
        <DataCard title={t('Готово')} note={`${t('Листов:')} ${report.sheets} · ${report.file_name}`}>
          <div className="toolbar">
            <Chip tone="good" className="num">
              {t('Учеников обновлено:')} {report.students_updated}
            </Chip>
            <Chip tone="neutral" className="num">
              {t('Попыток создано:')} {report.attempts_created}
            </Chip>
            <Chip tone="neutral" className="num">
              {t('Документов-ссылок:')} {report.documents_created}
            </Chip>
            <Chip tone="neutral" className="num">
              {t('Паролей записано:')} {report.credentials_saved}
            </Chip>
            <span className="toolbar__spacer" />
            {report.first_student && (
              <Button size="sm" variant="outline" onClick={() => navigate(`/students/${report.first_student}`)}>
                {t('Открыть карточку')}
              </Button>
            )}
            <ExportButton
              path={`/admission-imports/${report.id}/export/`}
              fallback="otchet-importa.xlsx"
              title={tk('Отчёт импорта')}
              label={tk('Скачать отчёт')}
            />
          </div>

          {/* по доменам — числами: строки «домен» из отчёта */}
          <ul className="wizard__domains">
            {report.rows
              .filter((row) => row.kind === DOMAIN_ROW)
              .map((row) => (
                <li key={row.text}>{row.text}</li>
              ))}
          </ul>

          {report.skipped_by_kind.length > 0 && (
            <>
              <p className="muted cadm__note">{t('Пропущено — по видам')}</p>
              <ul className="wizard__domains">
                {report.skipped_by_kind.map((row) => (
                  <li key={row.kind}>
                    {t(row.title)}: <b className="num">{row.count}</b>
                  </li>
                ))}
              </ul>
            </>
          )}

          {report.rows.filter((row) => row.kind !== DOMAIN_ROW).length === 0 && (
            <p className="muted">{t('Всё загрузилось без замечаний')}</p>
          )}
          <div className="toolbar">
            <span className="toolbar__spacer" />
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setStep(1)
                setFile(null)
                setPreview(null)
                setReport(null)
                setFixes({})
                setChosen([])
              }}
            >
              {t('Загрузить ещё файл')}
            </Button>
          </div>
        </DataCard>
      )}
    </>
  )
}
