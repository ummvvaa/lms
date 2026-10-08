/**
 * Разбор одного ученика: общий вывод и направления. Тот, кто ведёт тесты,
 * правит текст и решает, показывать ли разбор ученику; остальные читают.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareerAnalysisPatch, type CareerAnalysis, type CareerDirection } from '../../api/career'
import EditDrawer from '../../components/EditDrawer'
import Field from '../../components/Field'
import { Row, Rows } from '../../components/patterns'
import { Chip } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Switch } from '../../components/ui/switch'
import { t } from '../../i18n'
import { formatDateTime } from '../../lib/format'

type Draft = { summary: string; directions: Record<number, Partial<CareerDirection>> }

export default function AnalysisDrawer({ analysis, manage, onClose }: { analysis: CareerAnalysis; manage: boolean; onClose: () => void }) {
  const patch = useCareerAnalysisPatch()
  const [draft, setDraft] = useState<Draft>({ summary: analysis.summary, directions: {} })
  const dirty = draft.summary !== analysis.summary || Object.keys(draft.directions).length > 0
  const field = (direction: CareerDirection, name: keyof CareerDirection) =>
    (draft.directions[direction.id]?.[name] as string | undefined) ?? (direction[name] as string)
  const setField = (direction: CareerDirection, name: keyof CareerDirection, value: string) =>
    setDraft((prev) => ({ ...prev, directions: { ...prev.directions, [direction.id]: { ...prev.directions[direction.id], [name]: value } } }))

  const save = () =>
    patch.mutate(
      {
        id: analysis.id,
        summary: draft.summary,
        directions: Object.entries(draft.directions).map(([id, body]) => ({ id: Number(id), ...body })),
      },
      { onSuccess: () => setDraft({ summary: draft.summary, directions: {} }), onError: (error) => toast.error(error.message) },
    )

  const header = [
    analysis.student?.full_name ?? '',
    analysis.tests.map((test) => test.title).join(', '),
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <EditDrawer
      open
      onClose={onClose}
      title={t('Разбор')}
      sub={header}
      footer={
        <>
          {manage && (
            <Button disabled={!dirty || patch.isPending} onClick={save}>
              {patch.isPending ? t('Сохраняется…') : t('Сохранить правки')}
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>
            {t('Закрыть')}
          </Button>
        </>
      }
    >
      <div className="toolbar mb-0">
        <Chip tone={analysis.status === 'done' ? 'good' : analysis.status === 'failed' ? 'bad' : 'warn'} size="sm">
          {analysis.status_title}
        </Chip>
        <span className="t-note">{formatDateTime(analysis.created_at)}</span>
        {analysis.created_by && <span className="t-note">{t('запустил {name}', { name: analysis.created_by.short })}</span>}
        {analysis.edited_at && analysis.edited_by && <Chip size="sm" tone="info">{t('правил {name}', { name: analysis.edited_by.short })}</Chip>}
      </div>
      {analysis.error && <p className="acad__note">{analysis.error}</p>}
      {manage && analysis.status === 'done' && (
        <label className="field__check">
          <Switch
            checked={analysis.visible_to_student}
            onCheckedChange={(on) => patch.mutate({ id: analysis.id, visible_to_student: Boolean(on) }, { onError: (error) => toast.error(error.message) })}
          />
          <span className="field__checklabel">{t('Показать ученику')}</span>
        </label>
      )}
      {!manage && analysis.visible_to_student && <Chip size="sm" tone="good">{t('показан ученику')}</Chip>}
      {analysis.status === 'done' &&
        (manage ? (
          <Field kind="textarea" name="summary" label={t('Общий вывод')} rows={5} value={draft.summary} onChange={(value) => setDraft((prev) => ({ ...prev, summary: value }))} />
        ) : (
          analysis.summary && <p className="acad__note">{analysis.summary}</p>
        ))}
      {analysis.directions.map((direction) => (
        <div key={direction.id} className="canal__dir">
          {manage ? (
            <>
              <Field kind="text" name={`title-${direction.id}`} label={t('Направление')} value={field(direction, 'title')} onChange={(value) => setField(direction, 'title', value)} />
              <Field kind="textarea" name={`why-${direction.id}`} label={t('Почему подходит')} rows={4} value={field(direction, 'reasoning')} onChange={(value) => setField(direction, 'reasoning', value)} />
              <Field kind="text" name={`prof-${direction.id}`} label={t('Профессии')} value={field(direction, 'professions')} onChange={(value) => setField(direction, 'professions', value)} />
              <Field kind="text" name={`subj-${direction.id}`} label={t('Предметы')} value={field(direction, 'subjects')} onChange={(value) => setField(direction, 'subjects', value)} />
              <Field kind="text" name={`exams-${direction.id}`} label={t('Экзамены')} value={field(direction, 'exams')} onChange={(value) => setField(direction, 'exams', value)} />
            </>
          ) : (
            <>
              <b>{direction.title}</b>
              {direction.reasoning && <p className="acad__note">{direction.reasoning}</p>}
              <p className="t-note">{[direction.professions, direction.subjects, direction.exams].filter(Boolean).join(' · ')}</p>
            </>
          )}
          {direction.programs.length > 0 && (
            <Rows>
              {direction.programs.map((program) => (
                <Row key={program.id} icon="cap" title={program.name} note={`${program.university} · ${program.level_title}`} />
              ))}
            </Rows>
          )}
        </div>
      ))}
    </EditDrawer>
  )
}
