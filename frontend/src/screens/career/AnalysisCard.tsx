/**
 * Разбор одного ученика — окно по центру. Две версии текста (Г1, решение
 * владельца, 09.10.2026): «Для учителя» — как написала модель, в третьем лице;
 * «Для ученика» — на «ты», пишется моделью при первом «Показать ученику»,
 * учитель правит обе. Ученик видит только свою версию. Профиля интересов
 * по каждой шкале нет (решение владельца, 06.11.2026); профессии и объяснения
 * программ одни на обе версии и правятся во вкладке «Для учителя».
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareerAnalysisPatch, useCareerStartAnalyses, type CareerAnalysis, type CareerDirection } from '../../api/career'
import { isActiveRun } from '../../api/hooks'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import RunState from '../../components/RunState'
import { Chip, ScreenTabs } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Switch } from '../../components/ui/switch'
import { t } from '../../i18n'
import { formatDateTime } from '../../lib/format'
import DirectionView, { DIRECTION_FIELDS, DirectionFacts, DirectionHead, DirectionPrograms, programLine } from './DirectionView'
import ExportDialog from './ExportDialog'
import { analysisTone } from './tone'

type Version = 'teacher' | 'student'
type ItemDraft = { direction: number; title?: string; text?: string }
type Draft = { summary: string; summary_student: string; directions: Record<number, Partial<CareerDirection>>; items: Record<number, ItemDraft> }

export default function AnalysisCard({ analysis, manage, studentSees = false, onClose }: { analysis: CareerAnalysis; manage: boolean; /** ученику разборы показываются (флаг сервера); нет — переключатель и вкладка «Для ученика» скрыты */ studentSees?: boolean; onClose: () => void }) {
  const patch = useCareerAnalysisPatch()
  const [version, setVersion] = useState<Version>('teacher')
  const [exporting, setExporting] = useState(false)
  const [draft, setDraft] = useState<Draft>({ summary: analysis.summary, summary_student: analysis.summary_student ?? '', directions: {}, items: {} })
  const dirty =
    draft.summary !== analysis.summary ||
    draft.summary_student !== (analysis.summary_student ?? '') ||
    Object.keys(draft.directions).length > 0 ||
    Object.keys(draft.items).length > 0
  const field = (direction: CareerDirection, name: keyof CareerDirection) =>
    (draft.directions[direction.id]?.[name] as string | undefined) ?? ((direction[name] as string | undefined) ?? '')
  const setField = (direction: CareerDirection, name: keyof CareerDirection, value: string) =>
    setDraft((prev) => ({ ...prev, directions: { ...prev.directions, [direction.id]: { ...prev.directions[direction.id], [name]: value } } }))
  // профессия или объяснение программы: черновик по номеру строки
  const itemField = (id: number, name: 'title' | 'text', saved: string) => draft.items[id]?.[name] ?? saved
  const setItem = (direction: CareerDirection, id: number, name: 'title' | 'text', value: string) =>
    setDraft((prev) => ({ ...prev, items: { ...prev.items, [id]: { ...prev.items[id], direction: direction.id, [name]: value } } }))
  const save = () => {
    const changed = new Set([...Object.keys(draft.directions).map(Number), ...Object.values(draft.items).map((item) => item.direction)])
    patch.mutate(
      {
        id: analysis.id,
        summary: draft.summary,
        summary_student: draft.summary_student,
        directions: [...changed].map((id) => ({
          id,
          ...draft.directions[id],
          items: Object.entries(draft.items)
            .filter(([, item]) => item.direction === id)
            .map(([itemId, { title, text }]) => ({ id: Number(itemId), ...(title !== undefined ? { title } : {}), ...(text !== undefined ? { text } : {}) })),
        })),
      },
      { onSuccess: () => setDraft((prev) => ({ ...prev, directions: {}, items: {} })), onError: (error) => toast.error(error.message) },
    )
  }
  // версия для ученика пишется в фоне: пришла опросом — в черновик, если его не трогали
  const [seenVersion, setSeenVersion] = useState(analysis.summary_student ?? '')
  if ((analysis.summary_student ?? '') !== seenVersion) {
    setSeenVersion(analysis.summary_student ?? '')
    if (draft.summary_student === seenVersion) setDraft((prev) => ({ ...prev, summary_student: analysis.summary_student ?? '' }))
  }
  const versionRun = analysis.version_run ?? null
  const writing = isActiveRun(versionRun)
  const show = (on: boolean) =>
    patch.mutate(
      { id: analysis.id, visible_to_student: on },
      {
        onSuccess: (fresh) => {
          const started = fresh.version_run
          if (started && isActiveRun(started)) {
            toast.message(t('Версия для ученика пишется — окно можно закрыть, про готовность скажет колокольчик'))
            return
          }
          if (started?.status === 'failed') {
            toast.error(started.error || t('не получилось'))
            return
          }
          setDraft((prev) => ({ ...prev, summary_student: fresh.summary_student ?? prev.summary_student }))
          if (on) {
            setVersion('student')
            toast.success(t('Версия для ученика готова — проверьте текст'))
          }
        },
        onError: (error) => toast.error(error.message),
      },
    )
  // «Пересчитать» — тот же запуск разбора группы, по тем же тестам, для этого ученика
  const start = useCareerStartAnalyses()
  const recalc = () =>
    start.mutate(
      { group: analysis.group_id ?? 0, tests: analysis.tests.map((test) => test.id), students: analysis.student ? [analysis.student.id] : [], force: true },
      {
        onSuccess: (result) => {
          toast.success(result.already ? t('Разбор этой группы уже идёт') : t('Пересчёт запущен — новый разбор появится в списке'))
          onClose()
        },
        onError: (error) => toast.error(error.message),
      },
    )
  // новые поля у старого разбора пусты — не выводятся, пока их не заполнили
  const legacyOnly = new Set<keyof CareerDirection>(['title_abroad', 'next_steps'])
  const shows = (direction: CareerDirection, name: keyof CareerDirection) => !analysis.legacy || !legacyOnly.has(name) || Boolean(field(direction, name))
  const studentReady = Boolean(analysis.has_student_version)
  const forStudent = version === 'student'
  const summaryText = forStudent ? analysis.summary_student ?? '' : analysis.summary
  const reasonOf = (d: CareerDirection) => (forStudent ? (d.reasoning_student ?? '') : d.reasoning)
  const header = [analysis.student?.full_name ?? '', analysis.tests.map((test) => test.title).join(', ')].filter(Boolean).join(' · ')

  return (
    <Modal wide title={t('Разбор')} note={header} onClose={onClose}>
      <div className="toolbar mb-0">
        <Chip tone={analysisTone(analysis.status)} size="sm">
          {analysis.status_title}
        </Chip>
        <span className="t-note">{formatDateTime(analysis.created_at)}</span>
        {analysis.created_by && <span className="t-note">{t('запустил {name}', { name: analysis.created_by.short })}</span>}
        {analysis.edited_at && analysis.edited_by && <Chip size="sm" tone="info">{t('правил {name}', { name: analysis.edited_by.short })}</Chip>}
        {studentSees && analysis.visible_to_student && <Chip size="sm" tone="good">{t('показан ученику')}</Chip>}
      </div>
      {analysis.error && <p className="acad__note">{analysis.error}</p>}
      {analysis.legacy && analysis.status === 'done' && (
        <div className="warnline">
          <span className="warnline__what">{t('Разбор по старым правилам')}</span>
          <span>{t('Посчитан до перехода на поступление за рубеж и показан как есть')}</span>
          {manage && analysis.group_id && (
            <Button variant="outline" size="sm" disabled={start.isPending} onClick={recalc}>
              {start.isPending ? t('Запускаю…') : t('Пересчитать')}
            </Button>
          )}
        </div>
      )}
      {manage && studentSees && analysis.status === 'done' && (
        <label className="field__check">
          <Switch checked={analysis.visible_to_student} disabled={patch.isPending || writing} onCheckedChange={(on) => show(Boolean(on))} />
          <span className="field__checklabel">{t('Показать ученику')}</span>
        </label>
      )}
      {manage && studentSees && !analysis.visible_to_student && (
        <RunState run={versionRun} running={t('Модель пишет версию для ученика…')} onRestart={() => show(true)} restarting={patch.isPending} />
      )}
      {analysis.status === 'done' && studentSees && (
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
        analysis.directions.map((direction) =>
          manage ? (
            <div key={direction.id} className="canal__dir">
              {forStudent ? (
                <DirectionHead direction={direction} />
              ) : (
                <>
                  <Field kind="textarea" rows={1} name={`title-${direction.id}`} label={t('Направление')} value={field(direction, 'title')} onChange={(value) => setField(direction, 'title', value)} />
                  {shows(direction, 'title_abroad') && (
                    <Field kind="textarea" rows={1} name={`abroad-${direction.id}`} label={t('Как называется за рубежом')} value={field(direction, 'title_abroad')} onChange={(value) => setField(direction, 'title_abroad', value)} />
                  )}
                </>
              )}
              <Field
                kind="textarea"
                name={`why-${direction.id}-${version}`}
                label={t('Почему подходит')}
                rows={3}
                value={field(direction, forStudent ? 'reasoning_student' : 'reasoning')}
                onChange={(value) => setField(direction, forStudent ? 'reasoning_student' : 'reasoning', value)}
              />
              {forStudent ? (
                <DirectionFacts direction={direction} legacy={analysis.legacy} />
              ) : (
                <>
                  {direction.profession_items.length > 0 ? (
                    <div className="canal__fact">
                      <span className="eyebrow">{t('Профессии')}</span>
                      {direction.profession_items.map((job) => (
                        <div key={job.id} className="canal__item canal__item--edit">
                          <Field kind="textarea" rows={1} name={`job-${job.id}`} label={t('Профессия')} value={itemField(job.id, 'title', job.title)} onChange={(value) => setItem(direction, job.id, 'title', value)} />
                          <Field kind="textarea" rows={2} name={`job-text-${job.id}`} label={t('Чем занимается и почему подходит')} value={itemField(job.id, 'text', job.text)} onChange={(value) => setItem(direction, job.id, 'text', value)} />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <Field kind="textarea" rows={2} name={`professions-${direction.id}`} label={t('Профессии')} value={field(direction, 'professions')} onChange={(value) => setField(direction, 'professions', value)} />
                  )}
                  {DIRECTION_FIELDS.filter(({ name }) => shows(direction, name)).map(({ name, label }) => (
                    <Field key={name} kind="textarea" rows={2} name={`${name}-${direction.id}`} label={t(label)} value={field(direction, name)} onChange={(value) => setField(direction, name, value)} />
                  ))}
                  {direction.programs.some((program) => program.item !== null) ? (
                    <div className="canal__fact">
                      <span className="eyebrow">{t('Программы каталога')}</span>
                      {direction.programs.map((program) =>
                        program.item === null ? null : (
                          <div key={program.item} className="canal__item canal__item--edit">
                            <Field kind="textarea" rows={2} name={`program-${program.item}`} label={programLine(program)} value={itemField(program.item, 'text', program.why)} onChange={(value) => setItem(direction, program.item as number, 'text', value)} />
                          </div>
                        ),
                      )}
                    </div>
                  ) : (
                    <DirectionPrograms direction={direction} legacy={analysis.legacy} />
                  )}
                </>
              )}
            </div>
          ) : (
            <DirectionView key={direction.id} direction={direction} reasoning={reasonOf(direction)} legacy={analysis.legacy} />
          ),
        )}
      <div className="toolbar ctest__foot">
        {manage && (
          <Button disabled={!dirty || patch.isPending} onClick={save}>
            {patch.isPending ? t('Сохраняется…') : t('Сохранить правки')}
          </Button>
        )}
        {manage && analysis.status === 'done' && analysis.student && (
          // в файл идёт сохранённый текст: несохранённые правки сначала сохраняются кнопкой рядом
          <Button variant="outline" disabled={dirty} onClick={() => setExporting(true)}>
            {t('Скачать Word')}
          </Button>
        )}
        <Button variant="outline" onClick={onClose}>
          {t('Закрыть')}
        </Button>
      </div>
      {exporting && analysis.student && (
        <ExportDialog
          note={analysis.student.full_name}
          sourceLanguage={analysis.language}
          scopes={[{ value: 'one', label: analysis.student.full_name, request: { students: [analysis.student.id] } }]}
          onClose={() => setExporting(false)}
        />
      )}
    </Modal>
  )
}
