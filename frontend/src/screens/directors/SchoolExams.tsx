/**
 * «Результаты экзаменов» — академический директор (макет EExams, 24.10.2026).
 *
 * Mock Test и официальные IELTS/SAT одной таблицей по ученикам 11 класса:
 * последний Mock Test с секциями, лучший официальный, цель и сколько до неё.
 * На чтение: пробники файлом грузит администратор (решение владельца, 24.10.2026).
 * Строка открывает историю попыток в окне.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { downloadFile } from '../../api/client'
import { useExamHistory, useExamResults, type ExamResultRow } from '../../api/directors'
import DataTable, { type Column } from '../../components/DataTable'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Segmented } from '../../components/patterns'
import { EmptyNote, Bar, Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { formatDate, formatDayMonth } from '../../lib/format'
import { usePhone } from '../../phone'
import './directors.css'

type Exam = 'IELTS' | 'SAT'

/** Корзины распределения: у IELTS — полубаллы, у SAT — сотни. */
const BUCKETS: Record<Exam, { label: string; test: (v: number) => boolean }[]> = {
  IELTS: [
    { label: '5.5 −', test: (v) => v <= 5.5 },
    { label: '6.0', test: (v) => v === 6 },
    { label: '6.5', test: (v) => v === 6.5 },
    { label: '7.0', test: (v) => v === 7 },
    { label: '7.5 +', test: (v) => v >= 7.5 },
  ],
  SAT: [
    { label: '− 1290', test: (v) => v < 1300 },
    { label: '1300–1390', test: (v) => v >= 1300 && v < 1400 },
    { label: '1400–1490', test: (v) => v >= 1400 && v < 1500 },
    { label: '1500 +', test: (v) => v >= 1500 },
  ],
}

export default function SchoolExams() {
  const phone = usePhone()
  const [exam, setExam] = useState<Exam>('IELTS')
  const [group, setGroup] = useState('')
  const { data, isLoading, error } = useExamResults(exam, group)
  const [opened, setOpened] = useState<ExamResultRow | null>(null)
  const [saving, setSaving] = useState(false)
  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const s = data.summary
  const last = data.rows
    .map((row) => row.mock_date)
    .filter(Boolean)
    .sort()
    .at(-1)
  const values = data.rows.map((row) => Number(row.mock)).filter((v) => isScore(v))
  const buckets = BUCKETS[exam].map((bucket) => ({ ...bucket, n: values.filter(bucket.test).length }))
  const top = Math.max(1, ...buckets.map((b) => b.n))

  const columns: Column<ExamResultRow>[] = [
    {
      key: 'name',
      title: t('Ученик'),
      width: 'auto',
      phone: 'head',
      // фамилия и имя не разрываются посреди слова — переносится только между словами
      cell: (row) => <b className="dir__name">{row.full_name}</b>,
      sortBy: (row) => row.full_name,
    },
    {
      key: 'group',
      title: t('Группа'),
      width: '110px',
      cell: (row) => <Chip size="sm">{row.group}</Chip>,
      sortBy: (row) => row.group,
    },
    {
      key: 'mock',
      title: t('Последний Mock'),
      hint: exam === 'IELTS' ? t('Последний Mock · L / R / W / S') : t('Последний Mock · M / V'),
      width: '200px',
      cell: (row) =>
        row.mock ? (
          <>
            <b className="num">{row.mock}</b>
            {row.sections && <span className="t-note">{` · ${row.sections}`}</span>}
          </>
        ) : (
          <span className="t-note">{t('не сдавал(а)')}</span>
        ),
      sortBy: (row) => (row.mock ? Number(row.mock) : null),
    },
    {
      key: 'official',
      title: t('Официальный'),
      width: '150px',
      align: 'right',
      cell: (row) => <span className="num">{row.official || t('нет')}</span>,
      sortBy: (row) => (row.official ? Number(row.official) : null),
    },
    {
      // цель и разница — одной пометкой: «Цель: нет» и «До цели: цели нет» говорили одно дважды
      key: 'goal',
      title: t('Цель'),
      width: '170px',
      cell: (row) =>
        row.gap === null || !row.goal ? (
          <span className="t-note">{t('цели нет')}</span>
        ) : row.gap === 0 ? (
          <Chip tone="good" size="sm">
            {t('{goal} · достигнута', { goal: row.goal })}
          </Chip>
        ) : (
          <Chip tone={row.gap >= (exam === 'IELTS' ? 1 : 100) ? 'bad' : 'warn'} size="sm">
            {t('{goal} · до цели −{gap}', { goal: row.goal, gap: row.gap })}
          </Chip>
        ),
      sortBy: (row) => row.gap,
    },
  ]

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Результаты экзаменов')}
        subtitle={
          last
            ? t('11 параллель · последний Mock Test {date}', { date: formatDayMonth(last) })
            : t('11 параллель')
        }
        actions={
          <Button
            variant="outline"
            disabled={saving}
            onClick={() => {
              setSaving(true)
              downloadFile(
                `/directors/exam-results/export/?exam=${exam}${group ? `&group=${encodeURIComponent(group)}` : ''}`,
                `${exam}.xlsx`,
              )
                .then(() => toast.success(t('Файл xlsx скачан')))
                .catch((reason: unknown) =>
                  toast.error(reason instanceof Error ? reason.message : String(reason)),
                )
                .finally(() => setSaving(false))
            }}
          >
            {t('Выгрузить xlsx')}
          </Button>
        }
      />
      <div className="filters">
        <Segmented
          value={exam}
          onChange={setExam}
          label={t('Экзамен')}
          items={[
            { value: 'IELTS', label: 'IELTS' },
            { value: 'SAT', label: 'SAT' },
          ]}
        />
        <Field
          usageFilter
          kind="select"
          name="group"
          label={t('Группа')}
          value={group}
          onChange={setGroup}
          placeholder={t('Все группы 11 параллели')}
          options={data.groups.map((code) => ({ value: code, title: code }))}
        />
      </div>
      <div className="lay-4">
        <Kpi label={t('Сдавали Mock Test')} value={s.took} note={t('из {n} учеников', { n: s.students })} />
        {/* показатель без числа и «0 из 0» без целей плиткой не рисуются */}
        {s.average && <Kpi label={t('Средний балл')} value={s.average} note={t('по последнему Mock Test')} />}
        {s.with_goal > 0 && (
          <Kpi
            label={t('Достигли цели')}
            value={t('{n} из {total}', { n: s.reached, total: s.with_goal })}
            note={t('с целью по {exam}', { exam })}
          />
        )}
        {s.with_goal > 0 && (
          <Kpi
            label={exam === 'IELTS' ? t('Ниже цели на 1.0+') : t('Ниже цели на 100+')}
            value={s.far}
            chip={s.far ? { label: t('нужна помощь'), tone: 'warn' } : undefined}
            note={t('официальные: {n}', { n: s.official })}
          />
        )}
      </div>
      <div className="lay-main lay-main--even">
        <DataCard
          className="card--beam"
          title={t('Ученики')}
          count={data.rows.length}
          empty={data.rows.length === 0 && t('учеников 11 параллели нет')}
        >
          <DataTable
            columns={columns}
            rows={data.rows}
            rowKey={(row) => row.id}
            onRowClick={setOpened}
            limit={8}
            fit={!phone}
          />
        </DataCard>
        <div className="lay-stack">
          <DataCard
            title={t('Распределение баллов · {exam}', { exam })}
            note={t('по последнему Mock Test')}
            empty={values.length === 0 && t('Mock Test ещё не сдавали')}
          >
            <div className="dir__bars">
              {buckets.map((bucket) => (
                <div key={bucket.label} className="dir__bar">
                  <span className="num">{bucket.label}</span>
                  <Bar percent={(bucket.n * 100) / top} />
                  <b className="num">{bucket.n}</b>
                </div>
              ))}
            </div>
          </DataCard>
        </div>
      </div>
      {opened && <HistoryDialog row={opened} onClose={() => setOpened(null)} />}
    </div>
  )
}

function isScore(value: number): boolean {
  return Number.isFinite(value) && value > 0
}

function HistoryDialog({ row, onClose }: { row: ExamResultRow; onClose: () => void }) {
  const { data, isLoading, error } = useExamHistory(row.id)
  return (
    <Modal
      title={row.full_name}
      note={t('История попыток · {group}', { group: row.group })}
      onClose={onClose}
    >
      {isLoading && <Loading />}
      {error && <ErrorNote error={error} />}
      {data && (
        <div className="dir__lines">
          {data.attempts.length === 0 && <EmptyNote what={tk('попыток пока нет')} />}
          {data.attempts.map((attempt) => (
            <div key={attempt.id} className="dir__line">
              <span>
                {`${attempt.exam} · ${attempt.format_title}`}
                <span className="t-note">{` · ${attempt.date ? formatDate(attempt.date) : t('дата не указана')}${attempt.sections ? ` · ${attempt.sections}` : ''}`}</span>
              </span>
              <b className="num">{attempt.total}</b>
            </div>
          ))}
        </div>
      )}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Закрыть')}
        </Button>
      </div>
    </Modal>
  )
}
