/**
 * Мастер «Загрузить пробник» (фаза 63) — четыре шага, как в прототипе.
 *
 * 1. Что за пробник: экзамен, группа, дата, учитель.
 * 2. Файл: xlsx или csv, рядом — «какой формат» и «скачать шаблон».
 * 3. Проверка: строки файла со статусами. Кривую строку человек либо
 *    исправляет (выбрать ученика, ввести балл), либо пропускает; пока
 *    есть неразобранные, «Применить» неактивна.
 * 4. Готово: сколько записано, сколько пропущено, куда идти дальше.
 *
 * Разбирает и применяет сервер, причём один и тот же файл: шаг 3 ничего
 * не пишет в базу, шаг 4 читает файл заново и накладывает правки. Поэтому
 * между шагами нечему разъехаться, а черновиков в базе не остаётся.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { downloadFile } from '../../api/client'
import {
  useMockApply,
  useMockPreview,
  type MockDraft,
  type MockPreview,
  type MockPreviewRow,
  type MockRowFix,
} from '../../api/hooks'
import DataTable, { type Column } from '../../components/DataTable'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import WizardSteps from '../../components/WizardSteps'
import { t } from '../../i18n'
import { todayAlmaty } from '../../lib/dates'
import { formatDate } from '../../lib/format'
import './mocks.css'

const STEPS = ['Что за пробник', 'Файл', 'Проверка', 'Готово']

/** Ошибка именно про баллы: тогда подсвечиваем числа, а не имя. */
const scoreBroken = (row: MockPreviewRow): boolean =>
  ['score_range', 'sections_range', 'sections_mismatch', 'sections_missing', 'no_score'].includes(row.error)

/** Короткая подпись секции в шапке таблицы: места на слово нет. */
const SECTION_SHORT: Record<string, string> = {
  listening: 'L',
  reading: 'R',
  writing: 'W',
  speaking: 'S',
}

export function FormatDialog({ onClose }: { onClose: () => void }) {
  return (
    <Modal title={t('Формат файла пробника')} note={t('Полное описание для учителя — guides/MOCK_IMPORT.md в репозитории. Коротко:')} onClose={onClose}>
      <Rows>
        <Row title={t('ФИО')} note={t('обязательна')} value="Сериков Данияр" />
        <Row title={t('Балл')} note={t('обязательна')} value="6.5 / 1310" />
        <Row title="Listening, Reading, Writing, Speaking" note={t('только IELTS')} value="6.0 / 6.5 / 7.0 / 6.5" />
        <Row title={t('Примечание')} note={t('по желанию')} value={t('опоздал на Listening')} />
      </Rows>
      <ul className="mocks__rules t-note">
        <li>{t('Одна таблица — один пробник одной группы.')}</li>
        <li>{t('ФИО как в списке школы; если ученик не нашёлся, спросим при загрузке.')}</li>
        <li>{t('Балл вне шкалы остановит строку, пока её не исправят.')}</li>
        <li>{t('Пробники бывают по IELTS и SAT — других экзаменов школа не проводит.')}</li>
      </ul>
      <div className="acad__actions">
        <Button onClick={onClose}>{t('Понятно')}</Button>
      </div>
    </Modal>
  )
}

/** Диалог правки одной строки: выбрать ученика или ввести балл из бланка. */
function FixRow({
  row,
  preview,
  onSave,
  onClose,
}: {
  row: MockPreviewRow
  preview: MockPreview
  onSave: (fix: MockRowFix) => void
  onClose: () => void
}) {
  const [student, setStudent] = useState(String(row.candidates[0]?.student ?? preview.students[0]?.id ?? ''))
  const [total, setTotal] = useState(row.total !== null ? String(row.total) : '')
  const [sections, setSections] = useState<Record<string, string>>(
    Object.fromEntries(preview.sections.map((name) => [name, String(row.sections[name] ?? '')])),
  )
  const byStudent = row.fix === 'student'

  return (
    <Modal
      title={byStudent ? t('Кто это?') : t('Балл из бланка')}
      note={byStudent ? `${t('В файле написано')} «${row.raw_name || t('пусто')}»` : `${row.error_title}. ${preview.scale}`}
      onClose={onClose}
    >
      {byStudent ? (
        <Field
          kind="select"
          name="student"
          label={`${t('Ученик группы')} ${preview.group}`}
          value={student}
          onChange={setStudent}
          options={preview.students.map((person) => ({ value: String(person.id), title: person.full_name }))}
        />
      ) : (
        <>
          {preview.sections.length > 0 && (
            <Field.Row cols={2}>
              {preview.sections.map((name) => (
                <Field key={name} kind="text" name={name} label={name} value={sections[name] ?? ''} onChange={(value) => setSections({ ...sections, [name]: value })} />
              ))}
            </Field.Row>
          )}
          <Field kind="text" name="total" label={t('Общий балл')} value={total} onChange={setTotal} />
        </>
      )}
      <div className="acad__actions">
        <Button
          onClick={() =>
            onSave(
              byStudent
                ? { index: row.index, student: Number(student) }
                : { index: row.index, total, sections },
            )
          }
        >
          {byStudent ? t('Сопоставить') : t('Сохранить балл')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}

export default function MockWizard({
  groups,
  exams,
  group,
  onClose,
  onDone,
}: {
  groups: { code: string }[]
  exams: { code: string; title: string }[]
  group: string
  onClose: () => void
  onDone: (id: number) => void
}) {
  const [step, setStep] = useState(1)
  const [draft, setDraft] = useState<MockDraft>({
    exam_type: exams[0]?.code ?? 'IELTS',
    group: group !== 'all' ? group : (groups[0]?.code ?? ''),
    date: todayAlmaty(),
    teacher: '',
    file: null,
    fixes: [],
  })
  const [preview, setPreview] = useState<MockPreview | null>(null)
  const [fixing, setFixing] = useState<MockPreviewRow | null>(null)
  const [made, setMade] = useState<{ import: number; applied: number; skipped: number } | null>(null)
  const [format, setFormat] = useState(false)

  const check = useMockPreview()
  const apply = useMockApply()

  const run = (next: MockDraft) => {
    setDraft(next)
    check.mutate(next, {
      onSuccess: (result) => {
        setPreview(result)
        setStep(3)
      },
      onError: (error) => toast.error(error.message),
    })
  }

  const saveFix = (fix: MockRowFix) => {
    const fixes = [...draft.fixes.filter((row) => row.index !== fix.index), fix]
    setFixing(null)
    run({ ...draft, fixes })
  }

  const toggleSkip = (row: MockPreviewRow) => {
    const previous = draft.fixes.find((f) => f.index === row.index)
    const fixes = [
      ...draft.fixes.filter((f) => f.index !== row.index),
      { ...(previous ?? { index: row.index }), skip: !row.skip },
    ]
    run({ ...draft, fixes })
  }

  const download = () => {
    const params = new URLSearchParams({ exam: draft.exam_type })
    if (draft.group) params.set('group', draft.group)
    void downloadFile(`/mock-imports/template/?${params.toString()}`, `шаблон-${draft.exam_type}.xlsx`).catch(
      () => toast.error(t('Не удалось собрать файл')),
    )
  }

  const rowColumns: Column<MockPreviewRow>[] = preview
    ? [
        { key: 'index', title: '#', width: '6%', cell: (row) => <span className="t-note num">{row.index}</span> },
        { key: 'raw', title: t('ФИО из файла'), width: '24%', cell: (row) => row.raw_name || <span className="t-note">{t('пусто')}</span> },
        {
          key: 'found',
          title: t('Найден'),
          width: '22%',
          cell: (row) =>
            row.student_name ? <Chip tone="good" size="sm">{row.student_name}</Chip> : <Chip tone="bad" size="sm">{t(row.error_title || 'не найден')}</Chip>,
        },
        ...preview.sections.map((name) => ({
          key: name,
          title: SECTION_SHORT[name] ?? name,
          width: '7%',
          align: 'right' as const,
          cell: (row: MockPreviewRow) => <span className={`num${scoreBroken(row) ? ' mocks__bad' : ''}`}>{row.sections[name] ?? t('нет')}</span>,
        })),
        { key: 'total', title: t('Балл'), width: '8%', align: 'right', cell: (row) => <span className={`num${scoreBroken(row) ? ' mocks__bad' : ''}`}>{row.total ?? t('нет')}</span> },
        {
          key: 'acts',
          title: '',
          width: '20%',
          align: 'right',
          cell: (row) => (
            <span className="ctasks__acts">
              {/* почему строка красная — словами у самой строки, а не только цветом */}
              {row.error && !row.skip && <span className="t-note">{t(row.error_title)}</span>}
              {row.error && !row.skip && row.fix !== 'skip' && (
                <Button variant="outline" size="sm" onClick={() => setFixing(row)}>
                  {t('Исправить')}
                </Button>
              )}
              {row.error && !row.skip && (
                <Button variant="ghost" size="sm" onClick={() => toggleSkip(row)}>
                  {t('Пропустить')}
                </Button>
              )}
              {row.skip && (
                <Button variant="ghost" size="sm" onClick={() => toggleSkip(row)}>
                  {t('Вернуть')}
                </Button>
              )}
            </span>
          ),
        },
      ]
    : []

  const body = (
    <div className="mocks">
      <WizardSteps steps={STEPS.map((title) => t(title))} current={step} />

      {step === 1 && (
        <>
          <Field.Row>
            <Field kind="select" name="exam_type" label={t('Экзамен')} value={draft.exam_type} onChange={(value) => setDraft({ ...draft, exam_type: value })} options={exams.map((exam) => ({ value: exam.code, title: exam.title }))} />
            <Field kind="select" name="group" label={t('Группа')} value={draft.group} onChange={(value) => setDraft({ ...draft, group: value })} options={groups.map((item) => ({ value: item.code, title: item.code }))} />
          </Field.Row>
          <Field.Row>
            <Field kind="date" name="date" label={t('Дата пробника')} value={draft.date} onChange={(value) => setDraft({ ...draft, date: value })} />
            <Field kind="text" name="teacher" label={t('Кто проверял (учитель)')} value={draft.teacher} onChange={(value) => setDraft({ ...draft, teacher: value })} placeholder={t('Имя учителя из таблицы')} />
          </Field.Row>
        </>
      )}

      {step === 2 && (
        <>
          <label className="mocks__drop">
            <Input
              type="file"
              accept=".xlsx,.xlsm,.csv"
              aria-label={t('Файл пробника')}
              onChange={(e) => setDraft({ ...draft, file: e.target.files?.[0] ?? null, fixes: [] })}
            />
            <span>{draft.file ? draft.file.name : t('Выберите таблицу: .xlsx или .csv')}</span>
          </label>
          <div className="acad__actions">
            <Button variant="link" size="sm" onClick={() => setFormat(true)}>
              {t('Какой формат')}
            </Button>
            <Button variant="link" size="sm" onClick={download}>
              {t('Скачать шаблон')}
            </Button>
          </div>
          <p className="acad__note">
            {t(
              'Ученик ищется по ФИО из таблицы среди своей группы. Не нашёлся — строка покажется с ошибкой.',
            )}
          </p>
        </>
      )}

      {step === 3 && preview && (
        <>
          <div className="mocks__summary">
            <span>
              {preview.counts.total} {t('строк')} · {preview.counts.ready} {t('готовы')}
              {preview.counts.skipped > 0 && ` · ${preview.counts.skipped} ${t('пропущено')}`}
            </span>
            {preview.counts.broken > 0 && (
              <Chip tone="bad">
                {preview.counts.broken} {t('с ошибками')}
              </Chip>
            )}
            {preview.counts.broken > 0 && (
              <span className="t-note">{t('исправьте или пропустите, чтобы применить')}</span>
            )}
          </div>
          <DataTable columns={rowColumns} rows={preview.rows} rowKey={(row) => row.index} selected={(row) => row.skip} rowClass={(row) => (row.skip ? 'cmock__row--skip' : undefined)} />
        </>
      )}

      {step === 4 && made && (
        <DataCard title={t('Готово')}>
          <p className="mocks__done">
            <b className="num mocks__big">{made.applied}</b>
            <span>
              {t('результатов записано')}. {draft.exam_type} · {draft.group} · {formatDate(draft.date)}.
            </span>
          </p>
          {made.skipped > 0 && (
            <p className="t-note">
              {t('Пропущено строк:')} {made.skipped} — {t('они остались в отчёте загрузки')}
            </p>
          )}
          <p className="t-note">{t('Записано в журнал. Ученики увидят свой балл с пометкой «пробник школы».')}</p>
        </DataCard>
      )}
    </div>
  )

  const footer = (
    <div className="acad__actions mocks__foot">
      {step === 1 && (
        <Button disabled={!draft.group} onClick={() => setStep(2)}>
          {t('Дальше')}
        </Button>
      )}
      {step === 2 && (
        <Button disabled={!draft.file || check.isPending} onClick={() => run({ ...draft, fixes: [] })}>
          {t('Проверить файл')}
        </Button>
      )}
      {step === 3 && preview && (
        <Button
          disabled={!preview.can_apply || apply.isPending}
          onClick={() =>
            apply.mutate(draft, {
              onSuccess: (result) => {
                setMade(result)
                setStep(4)
              },
              onError: (error) => toast.error(error.message),
            })
          }
        >
          {t('Применить')}
        </Button>
      )}
      {step === 4 && made && (
        <>
          <Button onClick={() => onDone(made.import)}>{t('Открыть результаты')}</Button>
          <Button variant="outline" onClick={onClose}>
            {t('К списку')}
          </Button>
        </>
      )}
      {step > 1 && step < 4 && (
        <Button variant="outline" onClick={() => setStep(step - 1)}>
          {t('Назад')}
        </Button>
      )}
    </div>
  )

  return (
    <>
      <Modal title={t('Загрузить пробник')} onClose={onClose} wide>
        {body}
        {footer}
      </Modal>
      {fixing && preview && (
        <FixRow row={fixing} preview={preview} onSave={saveFix} onClose={() => setFixing(null)} />
      )}
      {format && <FormatDialog onClose={() => setFormat(false)} />}
    </>
  )
}
