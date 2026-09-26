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
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { daysFromToday } from '../../lib/dates'

/** Частые формулировки — из прототипа кабинета. */
const HINTS = [
  'Поставить цель по экзаменам',
  'Загрузить паспорт',
  'Записаться на пробник',
  'Обновить балл IELTS',
]

/** Срок по умолчанию — через неделю: столько занимает обычное поручение. */
function inAWeek(): string {
  return daysFromToday(7)
}

export default function TaskDialog({
  groups,
  defaultGroup,
  student,
  studentName,
  label,
  open: openOutside,
  onOpenChange,
}: {
  groups: CuratorGroup[]
  defaultGroup?: string
  /** задача одному ученику: адресат уже выбран, списка нет */
  student?: number
  studentName?: string
  label?: string
  /** окно открывает кнопка снаружи (фаза 75): на телефоне она в меню
      «Действия», и состояние живёт у экрана, а не у кнопки */
  open?: boolean
  onOpenChange?: (open: boolean) => void
}) {
  const [openInside, setOpenInside] = useState(false)
  const controlled = openOutside !== undefined
  const open = controlled ? openOutside : openInside
  const setOpen = (next: boolean) => {
    if (controlled) onOpenChange?.(next)
    else setOpenInside(next)
  }
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
      {!controlled && (
        <Button size="sm" onClick={() => setOpen(true)}>
          {label ?? t('Задача')}
        </Button>
      )}
      {open && (
        <Modal title={t('Задача ученику')} onClose={() => setOpen(false)}>
          {student ? (
            <Field.Static label={t('Кому')}>{studentName}</Field.Static>
          ) : (
            <Field
              kind="select"
              name="group"
              label={t('Кому')}
              value={group}
              onChange={setGroup}
              options={groups.map((row) => ({ value: row.code, title: `${t('Всей группе')} ${row.code} (${row.students})` }))}
            />
          )}

          <Field kind="text" name="title" label={t('Что сделать')} value={title} onChange={setTitle} placeholder={t('Например: загрузить транскрипт')} error={problem ?? undefined} autoFocus />

          <div className="acad__chips">
            {HINTS.map((hint) => (
              <Button key={hint} variant="secondary" size="sm" onClick={() => setTitle(t(hint))}>
                {t(hint)}
              </Button>
            ))}
          </div>

          <Field kind="date" name="due" label={t('Срок')} value={due} onChange={setDue} />

          <div className="acad__actions">
            <Button disabled={assign.isPending} onClick={send}>
              {t('Отправить')}
            </Button>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t('Отмена')}
            </Button>
          </div>
        </Modal>
      )}
    </>
  )
}
