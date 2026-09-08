/**
 * Постановка задачи ученику или всей группе (фаза 61).
 *
 * Группе — по задаче на каждого: закрывает её каждый сам, и «сделано»
 * у одного не снимает её с остальных. Четыре подсказки текста — то,
 * что куратор пишет чаще всего; нажатие подставляет текст в поле,
 * а не отправляет: срок и адресата всё равно выбирать руками.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useAssignTask, type CuratorGroup } from '../../api/hooks'
import Modal from '../../components/Modal'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { SelectField } from '../../components/SelectField'
import { t } from '../../i18n'

/** Частые формулировки — из прототипа кабинета. */
const HINTS = [
  'Поставить цель по экзаменам',
  'Загрузить паспорт',
  'Записаться на пробник',
  'Обновить балл IELTS',
]

/** Срок по умолчанию — через неделю: столько занимает обычное поручение. */
function inAWeek(): string {
  const date = new Date()
  date.setDate(date.getDate() + 7)
  return date.toISOString().slice(0, 10)
}

export default function TaskDialog({
  groups,
  defaultGroup,
  student,
  studentName,
  label,
}: {
  groups: CuratorGroup[]
  defaultGroup?: string
  /** задача одному ученику: адресат уже выбран, списка нет */
  student?: number
  studentName?: string
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [due, setDue] = useState(inAWeek())
  const [group, setGroup] = useState(defaultGroup && defaultGroup !== 'all' ? defaultGroup : (groups[0]?.code ?? ''))
  const [problem, setProblem] = useState<string | null>(null)
  const assign = useAssignTask()

  const send = () => {
    if (!title.trim()) {
      setProblem(t('Напишите, что сделать'))
      return
    }
    setProblem(null)
    assign.mutate(
      student ? { student, title, due_date: due } : { group, title, due_date: due },
      {
        onSuccess: (result) => {
          toast.success(
            result.created === 1
              ? t('Задача отправлена')
              : `${t('Задача отправлена ученикам:')} ${result.created}`,
          )
          setTitle('')
          setOpen(false)
        },
        onError: (error) => setProblem(error instanceof Error ? error.message : t('Не удалось поставить задачу')),
      },
    )
  }

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        {label ?? t('Задача')}
      </Button>
      {open && (
        <Modal title={t('Задача ученику')} onClose={() => setOpen(false)}>
          <div className="ctask">
            <label className="ctask__field">
              <span className="eyebrow">{t('Кому')}</span>
              {student ? (
                <b>{studentName}</b>
              ) : (
                <SelectField value={group} onChange={(e) => setGroup(e.target.value)} aria-label={t('Кому')}>
                  {groups.map((row) => (
                    <option key={row.id} value={row.code}>
                      {t('Всей группе')} {row.code} ({row.students})
                    </option>
                  ))}
                </SelectField>
              )}
            </label>

            <label className="ctask__field">
              <span className="eyebrow">{t('Что сделать')}</span>
              <Input
                value={title}
                placeholder={t('Например: загрузить транскрипт')}
                onChange={(e) => setTitle(e.target.value)}
                aria-label={t('Что сделать')}
              />
            </label>

            <div className="ctask__hints">
              {HINTS.map((hint) => (
                <button key={hint} type="button" className="squeue__hint" onClick={() => setTitle(t(hint))}>
                  {t(hint)}
                </button>
              ))}
            </div>

            <label className="ctask__field">
              <span className="eyebrow">{t('Срок')}</span>
              <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} aria-label={t('Срок')} />
            </label>

            {problem && <p className="ctask__problem">{problem}</p>}

            <div className="ctask__actions">
              <Button variant="outline" onClick={() => setOpen(false)}>
                {t('Отмена')}
              </Button>
              <Button disabled={assign.isPending} onClick={send}>
                {t('Отправить')}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}
