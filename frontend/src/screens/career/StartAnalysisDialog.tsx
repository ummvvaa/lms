/**
 * Запуск разбора по группе: какие сданные тесты взять (два из пяти, все),
 * пересчитывать ли готовые. Один набор попыток второй раз не разбирается —
 * готовый разбор возвращается как есть, пока не нажато «Пересчитать».
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareerResults, useCareerStartAnalyses, type CareerAnalyses } from '../../api/career'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows } from '../../components/patterns'
import { Chip } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tn } from '../../i18n'

export default function StartAnalysisDialog({ group, tests, onClose }: { group: number; tests: CareerAnalyses['tests']; onClose: () => void }) {
  const [picked, setPicked] = useState<Set<number>>(new Set(tests.map((test) => test.id)))
  const [force, setForce] = useState(false)
  const [students, setStudents] = useState<Set<number> | null>(null)
  const [search, setSearch] = useState('')
  const results = useCareerResults(group)
  const start = useCareerStartAnalyses()
  // кто сдал все выбранные тесты — тем разбор возможен; остальные показаны серым с причиной
  const rows = (results.data?.students ?? []).map((row) => ({
    id: row.id,
    full_name: row.full_name,
    ready: [...picked].every((testId) => row.cells[String(testId)]?.status === 'done'),
  }))
  const ready = rows.filter((row) => row.ready)
  const chosen = students ?? new Set(ready.map((row) => row.id))
  const chosenReady = ready.filter((row) => chosen.has(row.id))
  const shown = rows.filter((row) => !search || row.full_name.toLowerCase().includes(search.toLowerCase()))
  const toggleStudent = (id: number, on: boolean) =>
    setStudents(() => {
      const next = new Set(chosen)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })
  const toggle = (id: number, on: boolean) =>
    setPicked((prev) => {
      const next = new Set(prev)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })
  const run = () =>
    start.mutate(
      { group, tests: [...picked], students: chosenReady.map((row) => row.id), force },
      {
        onSuccess: (result) => {
          const parts = [
            result.created ? tn(result.created, 'запущен {n} разбор|запущено {n} разбора|запущено {n} разборов') : '',
            result.reused ? tn(result.reused, '{n} уже готов|{n} уже готовы|{n} уже готовы') : '',
            result.skipped.length ? tn(result.skipped.length, '{n} пропущен|{n} пропущено|{n} пропущено') : '',
          ].filter(Boolean)
          toast.success(parts.join(' · ') || t('Разбирать некого: никто не сдал выбранные тесты'))
          if (result.skipped.length) toast.message(result.skipped.map((row) => `${row.student.short}: ${row.reason}`).join('\n'))
          onClose()
        },
        onError: (error) => toast.error(error.message),
      },
    )
  return (
    <Modal wide title={t('Разобрать результаты')} note={t('Разбор получит каждый ученик группы, сдавший все выбранные тесты')} onClose={onClose}>
      {tests.length === 0 ? (
        <p className="acad__note">{t('В этой группе ещё никто не сдал ни одного теста')}</p>
      ) : (
        <Rows>
          {tests.map((test) => (
            <Row
              key={test.id}
              title={test.title}
              note={tn(test.done, 'сдал {n} ученик|сдали {n} ученика|сдали {n} учеников')}
              right={<Field kind="checkbox" name={`test-${test.id}`} label={t('взять')} checked={picked.has(test.id)} onChange={(on) => toggle(test.id, on)} />}
            />
          ))}
        </Rows>
      )}
      {tests.length > 0 && (
        <>
          <div className="toolbar mb-0">
            <span className="eyebrow">{t('Кому разбор')}</span>
            <Chip size="sm" className="num">{t('выбрано {done} из {total}', { done: chosenReady.length, total: ready.length })}</Chip>
            <Button variant="link" size="sm" onClick={() => setStudents(new Set(ready.map((row) => row.id)))}>
              {t('Все')}
            </Button>
            <Button variant="link" size="sm" onClick={() => setStudents(new Set())}>
              {t('Никого')}
            </Button>
          </div>
          <Field kind="text" name="student-search" label={t('Найти ученика')} value={search} onChange={setSearch} />
          <Rows>
            {shown.map((row) => (
              <Row
                key={row.id}
                avatar={row.full_name}
                title={row.full_name}
                note={row.ready ? undefined : t('сданы не все выбранные тесты')}
                muted={!row.ready}
                right={row.ready ? <Field kind="checkbox" name={`student-${row.id}`} label={t('взять')} checked={chosen.has(row.id)} onChange={(on) => toggleStudent(row.id, on)} /> : undefined}
              />
            ))}
          </Rows>
        </>
      )}
      <Field kind="checkbox" name="force" label={t('Пересчитать и уже готовые разборы по этому набору')} checked={force} onChange={setForce} hint={t('Без галочки готовый разбор по тем же попыткам не запрашивается у модели второй раз')} />
      <div className="toolbar mb-0">
        <Button disabled={picked.size === 0 || chosenReady.length === 0 || start.isPending} onClick={run}>
          {start.isPending ? t('Запускаю…') : t('Разобрать')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}
