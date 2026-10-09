/**
 * Разбор одного ученика — окно по центру. Две версии текста (Г1, решение
 * владельца, 09.10.2026): «Для учителя» — как написала модель, в третьем лице;
 * «Для ученика» — на «ты», пишется моделью при первом «Показать ученику»,
 * учитель правит обе. Ученик видит только свою версию.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareerAnalysisPatch, type CareerAnalysis, type CareerDirection } from '../../api/career'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows } from '../../components/patterns'
import { Chip, ScreenTabs } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Switch } from '../../components/ui/switch'
import { t } from '../../i18n'
import { formatDateTime } from '../../lib/format'

type Version = 'teacher' | 'student'
type Draft = { summary: string; summary_student: string; directions: Record<number, Partial<CareerDirection>> }

export default function AnalysisCard({ analysis, manage, onClose }: { analysis: CareerAnalysis; manage: boolean; onClose: () => void }) {
  const patch = useCareerAnalysisPatch()
  const [version, setVersion] = useState<Version>('teacher')
  const [draft, setDraft] = useState<Draft>({ summary: analysis.summary, summary_student: analysis.summary_student ?? '', directions: {} })
  const dirty = draft.summary !== analysis.summary || draft.summary_student !== (analysis.summary_student ?? '') || Object.keys(draft.directions).length > 0
  const field = (direction: CareerDirection, name: keyof CareerDirection) =>
    (draft.directions[direction.id]?.[name] as string | undefined) ?? ((direction[name] as string | undefined) ?? '')
  const setField = (direction: CareerDirection, name: keyof CareerDirection, value: string) =>
    setDraft((prev) => ({ ...prev, directions: { ...prev.directions, [direction.id]: { ...prev.directions[direction.id], [name]: value } } }))
  const save = () =>
    patch.mutate(
      {
        id: analysis.id,
        summary: draft.summary,
        summary_student: draft.summary_student,
        directions: Object.entries(draft.directions).map(([id, body]) => ({ id: Number(id), ...body })),
      },
      { onSuccess: () => setDraft((prev) => ({ ...prev, directions: {} })), onError: (error) => toast.error(error.message) },
    )
  const show = (on: boolean) =>
    patch.mutate(
      { id: analysis.id, visible_to_student: on },
      {
        onSuccess: (fresh) => {
          setDraft((prev) => ({ ...prev, summary_student: fresh.summary_student ?? prev.summary_student }))
          if (on) {
            setVersion('student')
            toast.success(t('Версия для ученика готова — проверьте текст'))
          }
        },
        onError: (error) => toast.error(error.message),
      },
    )
  const studentReady = Boolean(analysis.has_student_version)
  const forStudent = version === 'student'
  const summaryText = forStudent ? analysis.summary_student ?? '' : analysis.summary
  const reasonOf = (d: CareerDirection) => (forStudent ? (d.reasoning_student ?? '') : d.reasoning)
  const header = [analysis.student?.full_name ?? '', analysis.tests.map((test) => test.title).join(', ')].filter(Boolean).join(' · ')

  return (
    <Modal wide title={t('Разбор')} note={header} onClose={onClose}>
      <div className="toolbar mb-0">
        <Chip tone={analysis.status === 'done' ? 'good' : analysis.status === 'failed' ? 'bad' : 'warn'} size="sm">
          {analysis.status_title}
        </Chip>
        <span className="t-note">{formatDateTime(analysis.created_at)}</span>
        {analysis.created_by && <span className="t-note">{t('запустил {name}', { name: analysis.created_by.short })}</span>}
        {analysis.edited_at && analysis.edited_by && <Chip size="sm" tone="info">{t('правил {name}', { name: analysis.edited_by.short })}</Chip>}
        {analysis.visible_to_student && <Chip size="sm" tone="good">{t('показан ученику')}</Chip>}
      </div>
      {analysis.error && <p className="acad__note">{analysis.error}</p>}
      {manage && analysis.status === 'done' && (
        <label className="field__check">
          <Switch checked={analysis.visible_to_student} disabled={patch.isPending} onCheckedChange={(on) => show(Boolean(on))} />
          <span className="field__checklabel">{patch.isPending && !analysis.visible_to_student ? t('Модель пишет версию для ученика…') : t('Показать ученику')}</span>
        </label>
      )}
      {analysis.status === 'done' && (
        <ScreenTabs
          value={version}
          onChange={setVersion}
          items={[
            { value: 'teacher', label: t('Для учителя') },
            { value: 'student', label: studentReady ? t('Для ученика') : t('Для ученика — ещё не написана') },
          ]}
        />
      )}
      {forStudent && !studentReady && <p className="acad__note">{t('Версия для ученика появится после первого «Показать ученику»: модель перепишет разбор на «ты», без слов про обсуждение с учителем.')}</p>}
      {analysis.status === 'done' && (forStudent ? studentReady : true) && (
        manage ? (
          <Field
            kind="textarea"
            name={forStudent ? 'summary_student' : 'summary'}
            label={t('Общий вывод')}
            rows={5}
            value={forStudent ? draft.summary_student : draft.summary}
            onChange={(value) => setDraft((prev) => (forStudent ? { ...prev, summary_student: value } : { ...prev, summary: value }))}
          />
        ) : (
          summaryText && <p className="acad__note">{summaryText}</p>
        )
      )}
      {(forStudent ? studentReady : true) &&
        analysis.directions.map((direction) => (
          <div key={direction.id} className="canal__dir">
            {manage ? (
              <>
                {!forStudent && <Field kind="text" name={`title-${direction.id}`} label={t('Направление')} value={field(direction, 'title')} onChange={(value) => setField(direction, 'title', value)} />}
                {forStudent && <b>{field(direction, 'title')}</b>}
                <Field
                  kind="textarea"
                  name={`why-${direction.id}-${version}`}
                  label={t('Почему подходит')}
                  rows={4}
                  value={field(direction, forStudent ? 'reasoning_student' : 'reasoning')}
                  onChange={(value) => setField(direction, forStudent ? 'reasoning_student' : 'reasoning', value)}
                />
                {!forStudent && (
                  <>
                    <Field kind="text" name={`prof-${direction.id}`} label={t('Профессии')} value={field(direction, 'professions')} onChange={(value) => setField(direction, 'professions', value)} />
                    <Field kind="text" name={`subj-${direction.id}`} label={t('Предметы')} value={field(direction, 'subjects')} onChange={(value) => setField(direction, 'subjects', value)} />
                    <Field kind="text" name={`exams-${direction.id}`} label={t('Экзамены')} value={field(direction, 'exams')} onChange={(value) => setField(direction, 'exams', value)} />
                  </>
                )}
              </>
            ) : (
              <>
                <b>{direction.title}</b>
                {reasonOf(direction) && <p className="acad__note">{reasonOf(direction)}</p>}
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
      <div className="toolbar ctest__foot">
        {manage && (
          <Button disabled={!dirty || patch.isPending} onClick={save}>
            {patch.isPending ? t('Сохраняется…') : t('Сохранить правки')}
          </Button>
        )}
        <Button variant="outline" onClick={onClose}>
          {t('Закрыть')}
        </Button>
      </div>
    </Modal>
  )
}
