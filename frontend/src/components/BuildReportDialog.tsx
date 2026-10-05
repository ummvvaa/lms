/**
 * Сборка отчёта родителям — одно окно на все пути (30.09.2026): карточки
 * вида на странице «Отчёты родителям», карточка ученика, кабинет куратора.
 *
 * В окне: язык (по умолчанию язык группы), период, кому — вся группа или
 * один ученик, формат файла и «Собрать». Стандартный отчёт LMS — месяц или
 * четверть, только PDF и на русском; шаблоны школы (вариант 1 и 2) — период
 * «с — по», PDF или Word из одного docx. Делают четыре роли — куратор,
 * Кымбат, Салтанат и администратор; кнопку показывают экраны по
 * `REPORT_ROLES`, право держит сервер.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useBuildReports, type BuildReportsInput, type ReportGroup, type ReportTemplate } from '../api/academics'
import { useStudents } from '../api/hooks'
import { todayAlmaty } from '../lib/dates'
import Field from './Field'
import Modal from './Modal'
import { Segmented } from './patterns'
import { t, tk } from '../i18n'
import { Button } from './ui/button'

/** Периоды стандартного отчёта: текущий и прошлый месяц, четверти. */
export function reportPeriods(): { value: string; title: string }[] {
  const today = new Date()
  const month = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  const previous = new Date(today.getFullYear(), today.getMonth() - 1, 1)
  const previousCode = `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, '0')}`
  return [
    { value: month, title: `${t('текущий месяц')} · ${month}` },
    { value: previousCode, title: `${t('прошлый месяц')} · ${previousCode}` },
    { value: 'q1', title: t('1 четверть') },
    { value: 'q2', title: t('2 четверть') },
    { value: 'q3', title: t('3 четверть') },
    { value: 'q4', title: t('4 четверть') },
  ]
}

/** Три вида отчёта: название и одна строка — что внутри. */
export const TEMPLATE_OPTIONS: { value: ReportTemplate; title: string; note: string }[] = [
  { value: 'review', title: tk('Вариант 1 · отзыв об успеваемости'), note: tk('Посещаемость днями, средняя оценка по предметам, отзывы GE/EEP и SAT, характеристика') },
  { value: 'progress', title: tk('Вариант 2 · отчёт о прогрессе'), note: tk('Оценки по предметам списком, последний Mock Test, отзывы учителей, итоги и рекомендации') },
  { value: 'standard', title: tk('Стандартный'), note: tk('Отчёт LMS за месяц или четверть: посещаемость, оценки, экзамены и документы') },
]

export type FileType = 'pdf' | 'docx'

const FORMAT_KEY = 'lms.reports.format'

/** Формат файла, выбранный при сборке: им скачиваются отчёты и архив. Хранится в браузере. */
export function preferredFormat(): FileType {
  try {
    return window.localStorage.getItem(FORMAT_KEY) === 'docx' ? 'docx' : 'pdf'
  } catch {
    return 'pdf'
  }
}

function rememberFormat(type: FileType) {
  try {
    window.localStorage.setItem(FORMAT_KEY, type)
  } catch {
    // браузер не даёт хранить — формат просто не запомнится
  }
}

type Who = 'group' | 'student'

/**
 * Окно сборки. `template` не задан — вид выбирается в окне (карточка ученика);
 * `student` задан — отчёт на этого ученика, выбора «кому» нет.
 */
export default function BuildReportDialog({
  template: fixedTemplate,
  groups = [],
  group = 'all',
  student,
  studentName,
  onClose,
  onBuilt,
}: {
  template?: ReportTemplate
  groups?: ReportGroup[]
  /** группа, выбранная на экране, — с неё окно начинает */
  group?: string
  student?: number
  studentName?: string
  onClose: () => void
  /** собрано по группе: экран переключается на собранный период */
  onBuilt?: (period: string) => void
}) {
  const build = useBuildReports()
  const navigate = useNavigate()
  const today = todayAlmaty()
  const [template, setTemplate] = useState<ReportTemplate>(fixedTemplate ?? 'review')
  const [language, setLanguage] = useState<'' | 'ru' | 'kk'>('')
  const [period, setPeriod] = useState(reportPeriods()[0].value)
  const [from, setFrom] = useState(`${today.slice(0, 8)}01`)
  const [to, setTo] = useState(today)
  const [who, setWho] = useState<Who>('group')
  const [picked, setPicked] = useState(group !== 'all' ? group : groups.length === 1 ? groups[0].code : 'all')
  const [pupil, setPupil] = useState('')
  const [format, setFormat] = useState<FileType>(preferredFormat)
  const [error, setError] = useState('')
  const school = template !== 'standard'
  const oneStudent = student !== undefined || who === 'student'
  // «Отчёт по ученику»: список — ученики выбранной группы. Фильтр списка
  // учеников — по коду группы; видимость (куратор — свои группы) держит сервер
  const pupilGroup = student === undefined && who === 'student' && picked !== 'all' ? picked : ''
  const pupils = useStudents({ group: pupilGroup, page_size: 200 }, Boolean(pupilGroup))
  const pupilRows = pupilGroup ? (pupils.data?.results ?? []) : []
  const chosenGroup = groups.find((row) => row.code === picked)
  const groupLanguage = chosenGroup ? `${t('язык группы')} · ${t(chosenGroup.language_title).toLowerCase()}` : t('язык группы')
  const kind = TEMPLATE_OPTIONS.find((row) => row.value === template)

  const submit = () => {
    setError('')
    if (oneStudent && student === undefined && !pupil) {
      setError(t('Выберите ученика'))
      return
    }
    const base: BuildReportsInput = school ? { template, language, date_from: from, date_to: to } : { template: 'standard', period }
    const target: BuildReportsInput = student !== undefined ? { student } : oneStudent ? { student: Number(pupil) } : { group: picked === 'all' ? '' : picked }
    if (school) rememberFormat(format)
    build.mutate(
      { ...base, ...target },
      {
        onSuccess: (r) => {
          toast.success(`${oneStudent ? t('Отчёт собран') : t('Собрано отчётов: {n}', { n: r.built })} · ${t(r.title)}`)
          onClose()
          if (r.report) navigate(`/reports?${new URLSearchParams({ open: String(r.report), ...(r.period ? { period: r.period } : {}) }).toString()}`)
          else if (r.period) onBuilt?.(r.period)
        },
        onError: (e) => setError(e.message),
      },
    )
  }

  return (
    <Modal title={fixedTemplate && kind ? t(kind.title) : t('Отчёт родителям')} note={studentName ?? (kind ? t(kind.note) : undefined)} onClose={onClose}>
      {!fixedTemplate && (
        <Field kind="select" name="template" label={t('Вид отчёта')} value={template} onChange={(next) => setTemplate(next as ReportTemplate)} options={TEMPLATE_OPTIONS.map((row) => ({ value: row.value, title: t(row.title) }))} />
      )}
      {student === undefined && (
        <>
          <div className="field">
            <span className="field__label t-caps">{t('Кому')}</span>
            <Segmented<Who>
              value={who}
              onChange={setWho}
              label={t('Кому')}
              items={[
                { value: 'group', label: t('Вся группа') },
                { value: 'student', label: t('Один ученик') },
              ]}
            />
          </div>
          <Field
            kind="select"
            name="group"
            label={t('Группа')}
            value={picked}
            onChange={(value) => {
              setPicked(value)
              setPupil('')
            }}
            options={[...(who === 'group' && groups.length > 1 ? [{ value: 'all', title: t('Все группы') }] : who === 'student' && picked === 'all' ? [{ value: 'all', title: t('выберите группу') }] : []), ...groups.map((row) => ({ value: row.code, title: row.code }))]}
          />
          {who === 'student' && (
            <Field
              kind="select"
              name="student"
              label={t('Ученик')}
              value={pupil}
              onChange={setPupil}
              options={[{ value: '', title: pupilGroup ? (pupils.isLoading ? t('загружается…') : pupilRows.length ? t('выберите ученика') : t('в группе нет учеников')) : t('сначала группа') }, ...pupilRows.map((row) => ({ value: String(row.id), title: row.full_name }))]}
              disabled={!pupilGroup}
            />
          )}
        </>
      )}
      {school ? (
        <>
          <Field kind="select" name="language" label={t('Язык')} value={language} onChange={(next) => setLanguage(next as '' | 'ru' | 'kk')} options={[{ value: '', title: groupLanguage }, { value: 'kk', title: t('Казахский') }, { value: 'ru', title: t('Русский') }]} />
          <div className="acad__pair">
            <Field kind="date" name="from" label={t('С')} value={from} max={to} onChange={setFrom} />
            <Field kind="date" name="to" label={t('По')} value={to} min={from} onChange={setTo} />
          </div>
          <div className="field">
            <span className="field__label t-caps">{t('Формат файла')}</span>
            <Segmented<FileType>
              value={format}
              onChange={setFormat}
              label={t('Формат файла')}
              items={[
                { value: 'pdf', label: 'PDF' },
                { value: 'docx', label: 'Word' },
              ]}
            />
          </div>
        </>
      ) : (
        <Field kind="select" name="period" label={t('Период')} value={period} onChange={setPeriod} options={reportPeriods()} hint={t('Стандартный отчёт — на русском, файл PDF')} />
      )}
      {error && <p className="t-note text-bad">{error}</p>}
      <div className="acad__actions">
        <Button disabled={build.isPending} onClick={submit}>
          {t('Собрать')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}
