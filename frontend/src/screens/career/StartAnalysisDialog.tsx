/**
 * Запуск разбора по группе: какие сданные тесты взять (два из пяти, все),
 * пересчитывать ли готовые. Один набор попыток второй раз не разбирается —
 * готовый разбор возвращается как есть, пока не нажато «Пересчитать».
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareerStartAnalyses, type CareerAnalyses } from '../../api/career'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows } from '../../components/patterns'
import { Button } from '../../components/ui/button'
import { t, tn } from '../../i18n'

export default function StartAnalysisDialog({ group, tests, onClose }: { group: number; tests: CareerAnalyses['tests']; onClose: () => void }) {
  const [picked, setPicked] = useState<Set<number>>(new Set(tests.map((test) => test.id)))
  const [force, setForce] = useState(false)
  const start = useCareerStartAnalyses()
  const toggle = (id: number, on: boolean) =>
    setPicked((prev) => {
      const next = new Set(prev)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })
  const run = () =>
    start.mutate(
      { group, tests: [...picked], force },
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
    <Modal title={t('Разобрать результаты')} note={t('Разбор получит каждый ученик группы, сдавший все выбранные тесты')} onClose={onClose}>
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
      <Field kind="checkbox" name="force" label={t('Пересчитать и уже готовые разборы по этому набору')} checked={force} onChange={setForce} hint={t('Без галочки готовый разбор по тем же попыткам не запрашивается у модели второй раз')} />
      <div className="toolbar mb-0">
        <Button disabled={picked.size === 0 || start.isPending} onClick={run}>
          {start.isPending ? t('Запускаю…') : t('Разобрать')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}
