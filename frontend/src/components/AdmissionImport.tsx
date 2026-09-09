/**
 * Мастер загрузки таблицы поступления Асем (фаза 65).
 *
 * Порядок тот же, что у пробников: файл → проверка → применить → отчёт.
 * Проверка ничего не пишет в базу: она показывает, что нашлось на каждом
 * листе, и где строку придётся поправить руками — не нашёлся ученик,
 * похожих несколько, не разобрался телефон. Такую строку можно отнести
 * нужному ученику или пропустить; строк с ошибками применение не берёт.
 *
 * Паролей на шаге проверки нет — только «есть». Открытый пароль не
 * должен появляться на экране, где рядом стоит вся группа: показывают
 * его по одному, в карточке ученика, и каждый показ пишется в журнал.
 *
 * Таблица одноразовая, но повторный запуск обновляет, а не дублирует:
 * то же место в таблице правит ту же запись.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import {
  useAdmissionApply,
  useAdmissionPreview,
  type AdmissionImportReport,
  type AdmissionPreview,
} from '../api/hooks'
import { downloadFile } from '../api/client'
import { DataCard, ErrorNote } from './ui'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { SelectField } from './SelectField'
import { t } from '../i18n'

type Fix = { key: string; student?: number | null; skip?: boolean }

export default function AdmissionImport() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<AdmissionPreview | null>(null)
  const [report, setReport] = useState<AdmissionImportReport | null>(null)
  const [fixes, setFixes] = useState<Record<string, Fix>>({})
  const check = useAdmissionPreview()
  const apply = useAdmissionApply()

  const fixList = (): Fix[] => Object.values(fixes).filter((fix) => fix.skip || fix.student)

  const run = (selected: File, nextFixes: Fix[] = []) => {
    setReport(null)
    check.mutate(
      { file: selected, fixes: nextFixes },
      {
        onSuccess: (data) => {
          setPreview(data)
          setFile(selected)
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
    if (file)
      run(
        file,
        Object.values(next).filter((row) => row.skip || row.student),
      )
  }

  const applyAll = () => {
    if (!file) return
    apply.mutate(
      { file, fixes: fixList() },
      {
        onSuccess: (data) => {
          setReport(data)
          setPreview(null)
          toast.success(`${t('Обновлено учеников:')} ${data.students_updated}`)
        },
        onError: (error) => toast.error(error.message),
      },
    )
  }

  const counts = preview?.counts

  return (
    <>
      <DataCard
        title={t('Таблица поступления')}
        note={t('Книга Excel: лист — учебная группа, строка — ученик')}
        hint={t(
          'Колонки определяются по заголовкам первой строки, а не по порядку: ФИО, телефон, почта, пароли, ссылки на папку, паспорт, табель и рекомендацию, срок паспорта, GPA, IELTS-1..3 и SAT-1..3. Пустая ячейка ничего не стирает.',
        )}
      >
        <label className="filepick">
          <input
            type="file"
            accept=".xlsx,.xlsm"
            onChange={(event) => {
              const selected = event.target.files?.[0]
              if (selected) {
                setFixes({})
                run(selected)
              }
            }}
          />
          <Button size="sm" nativeButton={false} render={<span />}>
            {t('Выбрать файл')}
          </Button>
          <span className="muted filepick__name">{file ? file.name : t('Файл не выбран')}</span>
        </label>
        {check.isPending && <p className="muted">{t('Читаю книгу…')}</p>}
        {check.error && <ErrorNote error={check.error} />}
        <p className="muted">
          {t('Пароли из таблицы шифруются при загрузке. На этом экране они не показываются.')}
        </p>
      </DataCard>

      {preview && counts && (
        <DataCard title={t('Что будет загружено')} note={`${t('Листов:')} ${counts.sheets}`}>
          <div className="toolbar">
            <Badge variant="ok" className="num">
              {t('Строк готово:')} {counts.ready}
            </Badge>
            {counts.errors > 0 && (
              <Badge variant="warn" className="num">
                {t('Строк с ошибкой:')} {counts.errors}
              </Badge>
            )}
            {counts.sheets_skipped > 0 && (
              <Badge variant="mute" className="num">
                {t('Листов без группы:')} {counts.sheets_skipped}
              </Badge>
            )}
            <Badge variant="mute" className="num">
              {t('Попыток:')} {counts.attempts}
            </Badge>
            <Badge variant="mute" className="num">
              {t('Документов-ссылок:')} {counts.links}
            </Badge>
            <Badge variant="mute" className="num">
              {t('Паролей:')} {counts.passwords}
            </Badge>
            <span className="toolbar__spacer" />
            <Button size="sm" disabled={apply.isPending || counts.ready === 0} onClick={applyAll}>
              {t('Применить')}
            </Button>
          </div>

          {preview.sheets.map((sheet) => (
            <div key={sheet.name} className="aimp__sheet">
              <h3 className="aimp__title">
                {sheet.name}
                {sheet.error ? (
                  <Badge variant="warn">{sheet.error}</Badge>
                ) : (
                  <span className="muted">
                    {t('группа')} {sheet.group_code} · {t('готово')} {sheet.ready} · {t('пропуск')}{' '}
                    {sheet.skipped}
                  </span>
                )}
              </h3>
              {sheet.rows.length > 0 && (
                <div className="tblwrap">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>{t('Строка')}</th>
                        <th>{t('ФИО в таблице')}</th>
                        <th>{t('Ученик')}</th>
                        <th>{t('Что нашлось')}</th>
                        <th>{t('Замечания')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sheet.rows.map((row) => {
                        const key = `${sheet.name}:${row.index}`
                        const found = [
                          row.phone,
                          row.gpa === null ? '' : `GPA ${row.gpa}`,
                          row.scores.map((score) => `${score.exam} ${score.value}`).join(' · '),
                          row.links.length ? `${t('ссылок')} ${row.links.length}` : '',
                          row.has_email_password || row.has_common_app_password ? t('пароли есть') : '',
                        ]
                          .filter(Boolean)
                          .join(' · ')
                        return (
                          <tr key={key} className={row.error ? 'aimp__row--bad' : undefined}>
                            <td data-label={t('Строка')} className="num">
                              {row.index}
                            </td>
                            <td data-label={t('ФИО в таблице')}>{row.raw_name}</td>
                            {/* ученик не найден — его выбирают из похожих;
                                строку с любой другой бедой (телефон не
                                разобрался) правят в самой таблице, а здесь
                                её можно только пропустить осознанно */}
                            <td data-label={t('Ученик')}>
                              {row.skip ? (
                                <span className="muted">{t('пропущена')}</span>
                              ) : (
                                <div className="aimp__fix">
                                  {row.student_name ? (
                                    <span>{row.student_name}</span>
                                  ) : (
                                    <SelectField
                                      aria-label={t('Кому отнести строку')}
                                      value={String(fixes[key]?.student ?? '')}
                                      onChange={(event) =>
                                        setFix(key, {
                                          key,
                                          student: event.target.value ? Number(event.target.value) : null,
                                        })
                                      }
                                    >
                                      <option value="">{t('— выберите ученика —')}</option>
                                      {row.candidates.map((candidate) => (
                                        <option key={candidate.student} value={candidate.student}>
                                          {candidate.full_name}
                                        </option>
                                      ))}
                                    </SelectField>
                                  )}
                                  {row.error && (
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      onClick={() => setFix(key, { key, skip: true })}
                                    >
                                      {t('Пропустить')}
                                    </Button>
                                  )}
                                </div>
                              )}
                            </td>
                            <td data-label={t('Что нашлось')}>{found || '—'}</td>
                            <td data-label={t('Замечания')}>
                              {row.error && <Badge variant="warn">{row.error}</Badge>}
                              {row.warnings.map((warning) => (
                                <div key={warning} className="muted">
                                  {warning}
                                </div>
                              ))}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </DataCard>
      )}

      {report && (
        <DataCard
          title={t('Отчёт о загрузке')}
          note={`${t('Листов:')} ${report.sheets} · ${report.file_name}`}
        >
          <div className="toolbar">
            <Badge variant="ok" className="num">
              {t('Учеников обновлено:')} {report.students_updated}
            </Badge>
            <Badge variant="mute" className="num">
              {t('Попыток создано:')} {report.attempts_created}
            </Badge>
            <Badge variant="mute" className="num">
              {t('Документов-ссылок:')} {report.documents_created}
            </Badge>
            <Badge variant="mute" className="num">
              {t('Паролей записано:')} {report.credentials_saved}
            </Badge>
            {report.rows_skipped > 0 && (
              <Badge variant="warn" className="num">
                {t('Строк пропущено:')} {report.rows_skipped}
              </Badge>
            )}
            <span className="toolbar__spacer" />
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                void downloadFile(`/admission-imports/${report.id}/export/`, 'таблица-поступления.xlsx')
              }
            >
              {t('Скачать отчёт')}
            </Button>
          </div>
          {report.rows.length === 0 && <p className="muted">{t('Всё загрузилось без замечаний')}</p>}
          {report.rows.length > 0 && (
            <div className="tblwrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>{t('Лист')}</th>
                    <th>{t('Строка')}</th>
                    <th>{t('Ученик')}</th>
                    <th>{t('Что')}</th>
                    <th>{t('Подробности')}</th>
                  </tr>
                </thead>
                <tbody>
                  {report.rows.map((row, index) => (
                    <tr key={`${row.sheet}-${row.row}-${index}`}>
                      <td data-label={t('Лист')}>{row.sheet}</td>
                      <td data-label={t('Строка')} className="num">
                        {row.row}
                      </td>
                      <td data-label={t('Ученик')}>{row.student}</td>
                      <td data-label={t('Что')}>
                        <Badge variant={row.kind === 'внимание' ? 'mute' : 'warn'}>{row.kind}</Badge>
                      </td>
                      <td data-label={t('Подробности')}>{row.text}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DataCard>
      )}
    </>
  )
}
