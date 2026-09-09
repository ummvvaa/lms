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
import Modal from '../../components/Modal'
import { SelectField } from '../../components/SelectField'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { t } from '../../i18n'
import './curator.css'

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
    <Modal title={t('Формат файла пробника')} onClose={onClose}>
      <div className="ctask">
        <p className="muted">{t('Полное описание для учителя — в docs/MOCK_IMPORT.md. Коротко:')}</p>
        <div className="tblwrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>{t('Колонка')}</th>
                <th>{t('Обязательна')}</th>
                <th>{t('Пример')}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td data-head="">{t('ФИО')}</td>
                <td data-label={t('Обязательна')}>{t('да')}</td>
                <td data-label={t('Пример')}>Сериков Данияр</td>
              </tr>
              <tr>
                <td data-head="">{t('Балл')}</td>
                <td data-label={t('Обязательна')}>{t('да')}</td>
                <td data-label={t('Пример')}>6.5 / 1310</td>
              </tr>
              <tr>
                <td data-head="">Listening, Reading, Writing, Speaking</td>
                <td data-label={t('Обязательна')}>{t('только IELTS')}</td>
                <td data-label={t('Пример')}>6.0 / 6.5 / 7.0 / 6.5</td>
              </tr>
              <tr>
                <td data-head="">{t('Примечание')}</td>
                <td data-label={t('Обязательна')}>{t('нет')}</td>
                <td data-label={t('Пример')}>{t('опоздал на Listening')}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <ul className="muted cmock__rules">
          <li>{t('Одна таблица — один пробник одной группы.')}</li>
          <li>{t('ФИО как в списке школы; если ученик не нашёлся, спросим при загрузке.')}</li>
          <li>{t('Балл вне шкалы остановит строку, пока её не исправят.')}</li>
          <li>{t('Пробники бывают по IELTS и SAT — других экзаменов школа не проводит.')}</li>
        </ul>
        <div className="ctask__actions">
          <Button onClick={onClose}>{t('Понятно')}</Button>
        </div>
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
    <Modal title={byStudent ? t('Кто это?') : t('Балл из бланка')} onClose={onClose}>
      <div className="ctask">
        {byStudent ? (
          <>
            <p className="muted">
              {t('В файле написано')} «{row.raw_name || t('пусто')}». {t('Выберите ученика группы')}{' '}
              {preview.group}:
            </p>
            <SelectField
              value={student}
              onChange={(e) => setStudent(e.target.value)}
              aria-label={t('Ученик')}
            >
              {preview.students.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.full_name}
                </option>
              ))}
            </SelectField>
          </>
        ) : (
          <>
            <p className="muted">
              {row.error_title}. {preview.scale}. {t('Введите значение из бланка:')}
            </p>
            {preview.sections.length > 0 && (
              <div className="cmock__sections">
                {preview.sections.map((name) => (
                  <label key={name} className="ctask__field">
                    <span className="eyebrow">{name}</span>
                    <Input
                      value={sections[name] ?? ''}
                      inputMode="decimal"
                      onChange={(e) => setSections({ ...sections, [name]: e.target.value })}
                      aria-label={name}
                    />
                  </label>
                ))}
              </div>
            )}
            <label className="ctask__field">
              <span className="eyebrow">{t('Общий балл')}</span>
              <Input
                value={total}
                inputMode="decimal"
                onChange={(e) => setTotal(e.target.value)}
                aria-label={t('Общий балл')}
              />
            </label>
          </>
        )}
        <div className="ctask__actions">
          <Button variant="outline" onClick={onClose}>
            {t('Отмена')}
          </Button>
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
        </div>
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
  groups: { code: string; grade: number }[]
  exams: { code: string; title: string }[]
  group: string
  onClose: () => void
  onDone: (id: number) => void
}) {
  const [step, setStep] = useState(1)
  const [draft, setDraft] = useState<MockDraft>({
    exam_type: exams[0]?.code ?? 'IELTS',
    group: group !== 'all' ? group : (groups[0]?.code ?? ''),
    date: new Date().toISOString().slice(0, 10),
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

  const body = (
    <div className="cmock">
      <ol className="cmock__steps">
        {STEPS.map((title, index) => (
          <li key={title} className={step === index + 1 ? 'on' : step > index + 1 ? 'done' : ''}>
            {index + 1}. {t(title)}
          </li>
        ))}
      </ol>

      {step === 1 && (
        <div className="ctask">
          <label className="ctask__field">
            <span className="eyebrow">{t('Экзамен')}</span>
            <SelectField
              value={draft.exam_type}
              onChange={(e) => setDraft({ ...draft, exam_type: e.target.value })}
              aria-label={t('Экзамен')}
            >
              {exams.map((exam) => (
                <option key={exam.code} value={exam.code}>
                  {exam.title}
                </option>
              ))}
            </SelectField>
          </label>
          <label className="ctask__field">
            <span className="eyebrow">{t('Группа')}</span>
            <SelectField
              value={draft.group}
              onChange={(e) => setDraft({ ...draft, group: e.target.value })}
              aria-label={t('Группа')}
            >
              {groups.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.code} · {item.grade} {t('класс')}
                </option>
              ))}
            </SelectField>
          </label>
          <label className="ctask__field">
            <span className="eyebrow">{t('Дата пробника')}</span>
            <Input
              type="date"
              value={draft.date}
              onChange={(e) => setDraft({ ...draft, date: e.target.value })}
              aria-label={t('Дата пробника')}
            />
          </label>
          <label className="ctask__field">
            <span className="eyebrow">{t('Кто проверял (учитель)')}</span>
            <Input
              value={draft.teacher}
              placeholder={t('Имя учителя из таблицы')}
              onChange={(e) => setDraft({ ...draft, teacher: e.target.value })}
              aria-label={t('Кто проверял (учитель)')}
            />
          </label>
        </div>
      )}

      {step === 2 && (
        <div className="ctask">
          <label className="cmock__drop">
            <input
              type="file"
              accept=".xlsx,.xlsm,.csv"
              onChange={(e) => setDraft({ ...draft, file: e.target.files?.[0] ?? null, fixes: [] })}
            />
            <span>{draft.file ? draft.file.name : t('Выберите таблицу: .xlsx или .csv')}</span>
          </label>
          <p className="muted">
            <button type="button" className="linkish" onClick={() => setFormat(true)}>
              {t('Какой формат')}
            </button>
            {' · '}
            <button type="button" className="linkish" onClick={download}>
              {t('Скачать шаблон')}
            </button>
          </p>
          <p className="muted">
            {t(
              'Ученик ищется по ФИО из таблицы среди своей группы. Не нашёлся — строка покажется с ошибкой.',
            )}
          </p>
        </div>
      )}

      {step === 3 && preview && (
        <div>
          <div className="cmock__summary">
            <span>
              {preview.counts.total} {t('строк')} · {preview.counts.ready} {t('готовы')}
              {preview.counts.skipped > 0 && ` · ${preview.counts.skipped} ${t('пропущено')}`}
            </span>
            {preview.counts.broken > 0 && (
              <Badge variant="risk">
                {preview.counts.broken} {t('с ошибками')}
              </Badge>
            )}
            {preview.counts.broken > 0 && (
              <span className="muted">{t('исправьте или пропустите, чтобы применить')}</span>
            )}
          </div>
          <div className="tblwrap">
            <table className="tbl cmock__rows">
              <thead>
                <tr>
                  <th>#</th>
                  <th>{t('ФИО из файла')}</th>
                  <th>{t('Найден')}</th>
                  {preview.sections.map((name) => (
                    <th key={name} className="r">
                      {SECTION_SHORT[name] ?? name}
                    </th>
                  ))}
                  <th className="r">{t('Балл')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => (
                  <tr key={row.index} className={row.skip ? 'cmock__row--skip' : ''}>
                    <td data-head="" className="muted">
                      {row.index}
                    </td>
                    <td data-label={t('ФИО из файла')}>{row.raw_name || '—'}</td>
                    <td data-label={t('Найден')}>
                      {row.student_name ? (
                        <Badge variant="ok">{row.student_name}</Badge>
                      ) : (
                        <Badge variant="risk">{t(row.error_title || 'не найден')}</Badge>
                      )}
                    </td>
                    {preview.sections.map((name) => (
                      <td
                        key={name}
                        data-label={name}
                        className={`r num${scoreBroken(row) ? ' cmock__bad' : ''}`}
                      >
                        {row.sections[name] ?? '—'}
                      </td>
                    ))}
                    <td data-label={t('Балл')} className={`r num${scoreBroken(row) ? ' cmock__bad' : ''}`}>
                      {row.total ?? '—'}
                    </td>
                    <td className="r">
                      {/* почему строка красная — словами у самой строки, а не
                          только цветом: цвет не объясняет, что делать */}
                      {row.error && !row.skip && (
                        <span className="ctasks__acts">
                          <span className="muted cmock__why">{t(row.error_title)}</span>
                          {row.fix !== 'skip' && (
                            <Button variant="outline" size="sm" onClick={() => setFixing(row)}>
                              {t('Исправить')}
                            </Button>
                          )}
                          <Button variant="ghost" size="sm" onClick={() => toggleSkip(row)}>
                            {t('Пропустить')}
                          </Button>
                        </span>
                      )}
                      {row.skip && (
                        <Button variant="ghost" size="sm" onClick={() => toggleSkip(row)}>
                          {t('Вернуть')}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {step === 4 && made && (
        <div className="cmock__done">
          <b className="num cmock__big">{made.applied}</b>
          <p>
            {t('результатов записано')}. {draft.exam_type} · {draft.group} ·{' '}
            {new Date(draft.date).toLocaleDateString('ru')}.
          </p>
          {made.skipped > 0 && (
            <p className="muted">
              {t('Пропущено строк:')} {made.skipped} — {t('они остались в отчёте загрузки')}
            </p>
          )}
          <p className="muted">
            {t('Записано в журнал. Ученики увидят свой балл с пометкой «пробник школы».')}
          </p>
        </div>
      )}
    </div>
  )

  const footer = (
    <div className="ctask__actions">
      {step > 1 && step < 4 && (
        <Button variant="outline" onClick={() => setStep(step - 1)}>
          {t('Назад')}
        </Button>
      )}
      <span className="cfilters__spacer" />
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
          <Button variant="outline" onClick={onClose}>
            {t('К списку')}
          </Button>
          <Button onClick={() => onDone(made.import)}>{t('Открыть результаты')}</Button>
        </>
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
