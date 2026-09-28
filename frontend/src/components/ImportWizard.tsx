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
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import {
  useAdmissionApply,
  useAdmissionPreview,
  useStudyGroups,
  type AdmissionImportReport,
  type AdmissionPreview,
} from '../api/hooks'
import { downloadFile } from '../api/client'
import { Chip, DataCard, ErrorNote } from './ui'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Checkbox } from './ui/checkbox'
import { SelectField } from './SelectField'
import WizardSteps from './WizardSteps'
import DataTable from './DataTable'
import { t } from '../i18n'

type Fix = { key: string; student?: number | null; skip?: boolean }
type Step = 1 | 2 | 3 | 4

const STEPS: { step: Step; title: string }[] = [
  { step: 1, title: 'Файл' },
  { step: 2, title: 'Что заполняем' },
  { step: 3, title: 'Проверка строк' },
  { step: 4, title: 'Готово' },
]

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
  const [onlyBad, setOnlyBad] = useState(false)
  const [report, setReport] = useState<AdmissionImportReport | null>(null)
  const check = useAdmissionPreview()
  const apply = useAdmissionApply()
  const groups = useStudyGroups()

  const fixList = (next = fixes): Fix[] => Object.values(next).filter((fix) => fix.skip || fix.student)

  const run = (selected: File, nextFixes: Fix[] = [], forGroup = group) => {
    setReport(null)
    check.mutate(
      { file: selected, fixes: nextFixes, group: forGroup },
      {
        onSuccess: (data) => {
          setPreview(data)
          setFile(selected)
          // по умолчанию выбраны все найденные домены — из тех, что можно этому человеку
          if (!chosen.length) setChosen(data.writable_domains)
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

  const applyAll = () => {
    if (!file) return
    apply.mutate(
      { file, fixes: fixList(), group, domains: chosen },
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

  return (
    <>
      <WizardSteps steps={STEPS.map((row) => t(row.title))} current={step} />

      {step === 1 && (
        <DataCard
          title={t('Файл')}
          note={t('Книга Excel: лист — учебная группа, строка — ученик. CSV — одна группа, её выбирают здесь')}
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
              {t('Формат: колонки узнаются по заголовкам, пустая ячейка ничего не стирает — guides/ADMISSION_IMPORT.md в репозитории')}
            </span>
          </div>
          <label className="wizard__group">
            <span className="eyebrow">{t('Группа для CSV')}</span>
            <SelectField aria-label={t('Группа для CSV')} value={group} onChange={(e) => setGroup(e.target.value)}>
              <option value="">{t('— для книги Excel не нужна —')}</option>
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
                  run(selected, [])
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
                <Chip tone={preview.groups.length ? 'good' : 'warn'}>
                  {t('Группы:')} {preview.groups.join(', ') || t('не распознаны')}
                </Chip>
                {counts.sheets_skipped > 0 && (
                  <Chip tone="warn" className="num">
                    {t('Листов без группы:')} {counts.sheets_skipped}
                  </Chip>
                )}
                <span className="toolbar__spacer" />
                <Button size="sm" onClick={() => setStep(2)} disabled={counts.rows === 0}>
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
              { key: 'title', title: t('Колонка в файле'), width: '26%', cell: (column: WizardColumn) => column.title },
              { key: 'field', title: t('Поле'), width: '24%', cell: (column: WizardColumn) => column.field_title },
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

          {preview.unknown_columns.length > 0 && (
            <p className="muted wizard__unknown">
              {t('Не распознаны, будут пропущены:')}{' '}
              {preview.unknown_columns.map((title) => `«${title}»`).join(', ')}
            </p>
          )}

          <div className="toolbar">
            <span className="wizard__sum">
              {t('Будет записано:')} <b className="num">{summary.fields}</b> {t('полей в')}{' '}
              <b className="num">{summary.domains}</b> {t('домена,')} <b className="num">{summary.rows}</b>{' '}
              {t('строк')}
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
            <label className="users__check">
              <Checkbox checked={onlyBad} onCheckedChange={(on) => setOnlyBad(Boolean(on))} />
              {t('только с ошибками')}
            </label>
            <span className="toolbar__spacer" />
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
                    {t('группа')} {sheet.group_code} · {t('готово')} {sheet.ready} · {t('пропуск')}{' '}
                    {sheet.skipped}
                  </span>
                )}
              </h3>
              {sheet.rows.length > 0 && (
                <DataTable
                  columns={[
                    { key: 'n', title: t('Строка'), width: '8%', align: 'right', cell: (row: SheetRow) => <span className="num">{row.index}</span> },
                    { key: 'raw', title: t('ФИО в таблице'), width: '20%', cell: (row: SheetRow) => row.raw_name },
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
                          row.links.length ? `${t('ссылок')} ${row.links.length}` : '',
                          row.has_email_password || row.has_common_app_password ? t('пароли есть') : '',
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
              title="Отчёт импорта"
              label="Скачать отчёт"
            />
          </div>

          {/* по доменам — числами: строки «домен» из отчёта */}
          <ul className="wizard__domains">
            {report.rows
              .filter((row) => row.kind === 'домен')
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

          {report.rows.filter((row) => row.kind !== 'домен').length === 0 && (
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
