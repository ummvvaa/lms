/**
 * Отчёт по шаблону школы в панели отчётов: данные снимка, пометки куратору,
 * тексты и отзывы учителей (решение владельца, 30.09.2026).
 *
 * Черновик текстов пишет ИИ только из данных отчёта; куратор правит любой
 * текст до скачивания. ИИ недоступен — поля пустые, куратор пишет сам.
 * Пустой блок отзыва в файл не попадает; блок другого предмета можно убрать.
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
  useDropReportReview,
  useRedraftReport,
  useSaveReportTexts,
  type ReportDetail,
  type SchoolReport as SchoolData,
  type SchoolReportLine,
  type SchoolTextField,
} from '../../api/academics'
import DataTable, { type Column } from '../../components/DataTable'
import Field from '../../components/Field'
import { Row, Rows } from '../../components/patterns'
import { DataCard } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'

const FIELD_TITLES: Record<SchoolTextField, string> = {
  mock_comment: 'Комментарий по результатам пробника',
  character: 'Общий отзыв: поведение и адаптация',
  summary: 'Итоги и рекомендации',
}

type Line = SchoolReportLine & { key: number }

const LINE_COLUMNS: Column<Line>[] = [
  { key: 'title', title: t('Предмет'), width: '70%', cell: (line) => <b>{line.title}</b> },
  { key: 'value', title: t('Оценки'), width: '30%', align: 'right', cell: (line) => (line.value ? <span className="num">{line.value}</span> : <span className="t-note">{t('оценок нет')}</span>) },
]

const SCORE_COLUMNS: Column<Line>[] = [
  { key: 'title', title: t('Раздел'), width: '60%', cell: (line) => line.title },
  { key: 'value', title: t('Балл'), width: '40%', align: 'right', cell: (line) => <b className="num">{line.value || t('нет')}</b> },
]

function withKeys(lines: SchoolReportLine[]): Line[] {
  return lines.map((line, index) => ({ ...line, key: index }))
}

export default function SchoolReport({ report, editable }: { report: ReportDetail; editable: boolean }) {
  const data = report.school as SchoolData
  const save = useSaveReportTexts()
  const drop = useDropReportReview()
  const redraft = useRedraftReport()
  const [texts, setTexts] = useState(data.texts)
  const [reviews, setReviews] = useState<Record<number, string>>({})
  useEffect(() => {
    setTexts(data.texts)
    setReviews(Object.fromEntries(data.reviews.map((row) => [row.id, row.text])))
  }, [data])
  const fail = (e: Error) => toast.error(e.message)
  const dirtyTexts = data.fields.some((name) => (texts[name] ?? '') !== (data.texts[name] ?? ''))
  const dirtyReviews = data.reviews.filter((row) => (reviews[row.id] ?? '') !== row.text)
  const dirty = dirtyTexts || dirtyReviews.length > 0
  const mock = [...(data.ielts.length ? [{ title: 'IELTS', lines: data.ielts }] : []), ...(data.sat.length ? [{ title: 'SAT', lines: data.sat }] : [])]
  const saveAll = () =>
    save.mutate(
      {
        id: report.id,
        texts: Object.fromEntries(data.fields.map((name) => [name, texts[name] ?? ''])),
        reviews: dirtyReviews.map((row) => ({ id: row.id, text: reviews[row.id] ?? '' })),
      },
      { onSuccess: () => toast.success(t('Тексты сохранены')), onError: fail },
    )

  return (
    <>
      {data.gaps.length > 0 && (
        <Rows>
          {data.gaps.map((gap) => (
            <Row key={gap} icon="alert" tone="warn" title={t(gap)} />
          ))}
        </Rows>
      )}
      <DataCard title={t('Посещаемость')}>
        <Rows>
          {data.attendance.map((line) => (
            <Row key={line.code} title={t(line.title)} value={line.value || null} none={t('нет')} />
          ))}
        </Rows>
      </DataCard>
      <DataCard title={t('Оценки ФО по предметам табеля')}>
        <DataTable columns={LINE_COLUMNS} rows={withKeys(data.grades)} rowKey={(line) => line.key} empty={<span className="t-note">{t('журналов с табелем нет')}</span>} />
      </DataCard>
      {data.profile.length > 0 && (
        <DataCard title={t('Английский и спорт')}>
          <Rows>
            {data.profile.map((line) => (
              <Row key={line.code} title={t(line.title)} value={line.value || null} none={t('не внесено')} />
            ))}
          </Rows>
        </DataCard>
      )}
      {mock.map((block) => (
        <DataCard key={block.title} title={`${t('Пробник')} ${block.title}`} right={<span className="t-note num">{block.lines[0]?.note}</span>}>
          <DataTable columns={SCORE_COLUMNS} rows={withKeys(block.lines)} rowKey={(line) => line.key} />
        </DataCard>
      ))}

      <DataCard
        title={t('Тексты отчёта')}
        right={
          editable ? (
            <Button
              variant="link"
              size="sm"
              disabled={redraft.isPending || data.draft.state === 'pending'}
              onClick={() => {
                if (!window.confirm(t('ИИ перепишет все тексты по данным отчёта — ваша правка заменится. Продолжить?'))) return
                redraft.mutate(report.id, { onSuccess: () => toast.success(t('ИИ пишет черновик')), onError: fail })
              }}
            >
              {t('Написать заново')}
            </Button>
          ) : undefined
        }
      >
        <Rows>
          <Row
            icon={data.draft.state === 'failed' || data.draft.state === 'skipped' ? 'alert' : 'sparkle'}
            tone={data.draft.state === 'failed' ? 'warn' : data.draft.state === 'done' ? 'good' : undefined}
            title={data.draft.state === 'pending' ? t('ИИ пишет черновик — тексты появятся здесь') : `${t('Черновик ИИ')}: ${t(data.draft.title)}`}
            note={data.draft.note ? t(data.draft.note) : t('Черновик — только из данных отчёта. Проверьте и поправьте перед скачиванием')}
          />
        </Rows>
        <div className="acad__form">
          {data.fields.map((name) => (
            <Field key={name} kind="textarea" name={name} label={t(FIELD_TITLES[name])} value={texts[name] ?? ''} onChange={(value) => setTexts({ ...texts, [name]: value })} rows={4} readOnly={!editable} />
          ))}
          {data.reviews.map((row) => (
            <div key={row.id} className="acad__form">
              <Field
                kind="textarea"
                name={`review-${row.id}`}
                label={row.kind === 'subject' ? [row.teacher, row.subject].filter(Boolean).join(' — ') : `${t('Отзыв')} · ${row.kind_title}${row.teacher ? ` · ${row.teacher}` : ''}`}
                value={reviews[row.id] ?? ''}
                onChange={(value) => setReviews({ ...reviews, [row.id]: value })}
                rows={3}
                readOnly={!editable}
                hint={row.text ? (row.by_ai ? t('написал ИИ') : undefined) : t('пустой блок в файл не попадёт')}
              />
              {editable && row.removable && (
                <div className="acad__actions">
                  <Button variant="outline" size="sm" disabled={drop.isPending} onClick={() => drop.mutate({ id: report.id, review: row.id }, { onSuccess: () => toast.success(t('Блок убран')), onError: fail })}>
                    {t('Убрать блок')}
                  </Button>
                </div>
              )}
            </div>
          ))}
          {editable && (
            <div className="acad__actions">
              <Button size="sm" disabled={!dirty || save.isPending} onClick={saveAll}>
                {t('Сохранить тексты')}
              </Button>
            </div>
          )}
        </div>
      </DataCard>
    </>
  )
}
