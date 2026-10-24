/**
 * Окна куратора на карточке ученика и в очереди (фаза 62).
 *
 * «Родителям» — телефон с пометкой владельца контакта и поле «о чём говорили»:
 * с текстом уходит заметка с префиксом «Звонок родителям:» и запись в журнал,
 * без текста — только журнал. «Передать» — вопрос владельцу домена, Кымбат
 * или Асем, комментарий обязателен: без него владелец не поймёт, зачем ему
 * строка. Строка очереди передаётся владельцу своего домена — адресат
 * от домена, а не всегда Кымбат.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useNavigate } from 'react-router'
import { useEscalateStudent, useEscalateSuggestion, useParentCall, useTransferStudent, type CuratorCard } from '../../api/hooks'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { SelectField } from '../../components/SelectField'
import { Row, Rows } from '../../components/patterns'
import { Chip } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'

/** Владелец домена по коду — подпись кнопок и адресат. Из реестра, не выдумка экрана.
 *  Имя — ключ перевода: показывается через `t()`. */
export const OWNER_OF: Record<string, string> = { exam: tk('Кымбат'), documents: tk('Асем') }

/** Кому куратор передаёт строку очереди: только документы — Асем. Экзамены подтверждает
 *  сам куратор, Кымбат ученические правки не разбирает (решение владельца, 25.10.2026). */
export const HANDOVER_DOMAINS = ['documents']

/** Состояние окна снаружи или внутри: снаружи — когда кнопка в меню «Действия» (фаза 75). */
function useOpenState(outside: boolean | undefined, onChange?: (open: boolean) => void) {
  const [inside, setInside] = useState(false)
  const controlled = outside !== undefined
  const open = controlled ? outside : inside
  const setOpen = (next: boolean) => {
    if (controlled) onChange?.(next)
    else setInside(next)
  }
  return { open, setOpen, controlled }
}

export interface OwnedDialog {
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

/** Перевод ученика в другую группу той же параллели (решение владельца, 19.10.2026):
 *  без подтверждения второго куратора; ученик сразу в уроках новой группы. */
export function TransferDialog({ card, open: outside, onOpenChange }: { card: CuratorCard } & OwnedDialog) {
  const { open, setOpen, controlled } = useOpenState(outside, onOpenChange)
  const navigate = useNavigate()
  const transfer = useTransferStudent()
  const targets = card.transfer_targets ?? []
  const [group, setGroup] = useState('')
  const picked = group || targets[0]?.code || ''
  return (
    <>
      {!controlled && (
        <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
          {t('Перевести в группу')}
        </Button>
      )}
      {open && (
        <Modal title={t('Перевести в группу')} note={`${card.full_name} · ${card.group}`} onClose={() => setOpen(false)}>
          {targets.length === 0 ? (
            <p className="t-note">{t('Групп той же параллели для перевода нет')}</p>
          ) : (
            <>
              <SelectField name="group" aria-label={t('Куда перевести')} value={picked} onChange={(event) => setGroup(event.target.value)}>
                {targets.map((row) => (
                  <option key={row.id} value={row.code}>
                    {row.code}
                  </option>
                ))}
              </SelectField>
              <p className="t-note">{t('Ученик сразу попадёт в уроки новой группы; оценки и отметки остаются у него. Перевод запишется в журнал обеих групп.')}</p>
              <div className="acad__actions">
                <Button
                  disabled={transfer.isPending || !picked}
                  onClick={() =>
                    transfer.mutate(
                      { student: card.id, group: picked },
                      {
                        onSuccess: (result) => {
                          toast.success(t('{name} переведён в {group}', { name: card.full_name, group: result.group }))
                          setOpen(false)
                          // ученик ушёл к другому куратору — его карточки у этого куратора больше нет
                          if (!result.still_mine) navigate('/students')
                        },
                        onError: (error) => toast.error(error.message),
                      },
                    )
                  }
                >
                  {t('Перевести')}
                </Button>
              </div>
            </>
          )}
        </Modal>
      )}
    </>
  )
}

export function CallDialog({ card, open: outside, onOpenChange }: { card: CuratorCard } & OwnedDialog) {
  const { open, setOpen, controlled } = useOpenState(outside, onOpenChange)
  const [text, setText] = useState('')
  const call = useParentCall()
  const primary = card.contacts[0]

  return (
    <>
      {!controlled && (
        <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
          {t('Родителям')}
        </Button>
      )}
      {open && (
        <Modal title={t('Позвонить родителям')} note={card.full_name} onClose={() => setOpen(false)}>
          <Rows>
            {primary ? (
              <Row
                icon="person"
                title={primary.phone || primary.email}
                note={`${primary.full_name}, ${primary.relation_title}`}
                right={<Chip size="sm">{t('ведёт Салтанат')}</Chip>}
                acts={
                  primary.phone ? (
                    <Button variant="secondary" size="sm" onClick={() => window.open(`tel:${primary.phone.replace(/\s/g, '')}`, '_self')}>
                      {t('Позвонить')}
                    </Button>
                  ) : undefined
                }
              />
            ) : (
              <Row icon="person" tone="warn" title={t('Контактов пока нет')} note={t('заведите контакт в карточке — блок «Контакты»')} />
            )}
          </Rows>
          <Field kind="textarea" name="text" label={t('О чём говорили — запишется в заметки')} value={text} onChange={setText} rows={3} placeholder={t('Коротко')} />
          <div className="acad__actions">
            <Button
              disabled={call.isPending}
              onClick={() =>
                call.mutate(
                  { student: card.id, text },
                  {
                    onSuccess: (result) => {
                      toast.success(
                        result.noted ? t('Итог звонка записан в заметки') : t('Звонок записан в журнал'),
                      )
                      setText('')
                      setOpen(false)
                    },
                    onError: (e) => toast.error(e.message),
                  },
                )
              }
            >
              {t('Сохранить итог звонка')}
            </Button>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t('Закрыть')}
            </Button>
          </div>
        </Modal>
      )}
    </>
  )
}

export function EscalateStudentDialog({ card, open: outside, onOpenChange }: { card: CuratorCard } & OwnedDialog) {
  const { open, setOpen, controlled } = useOpenState(outside, onOpenChange)
  const [domain, setDomain] = useState<'exam' | 'documents'>('exam')
  const [comment, setComment] = useState('')
  const send = useEscalateStudent()

  return (
    <>
      {!controlled && (
        <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
          {t('Передать')}
        </Button>
      )}
      {open && (
        <Modal title={t('Передать владельцу домена')} note={t('Владелец получит уведомление с вашим комментарием и ссылкой на карточку {name}', { name: card.full_name })} onClose={() => setOpen(false)}>
          <Field
            kind="select"
            name="domain"
            label={t('Кому')}
            value={domain}
            onChange={(next) => setDomain(next as 'exam' | 'documents')}
            options={[
              { value: 'exam', title: `${t('Кымбат')} · ${t('экзамены')}` },
              { value: 'documents', title: `${t('Асем')} · ${t('документы')}` },
            ]}
          />
          <Field kind="textarea" name="comment" label={t('Что нужно от владельца')} value={comment} onChange={setComment} rows={3} placeholder={t('Например: балл IELTS расходится с сертификатом, нужно решение')} />
          <div className="acad__actions">
            <Button
              disabled={send.isPending || !comment.trim()}
              onClick={() =>
                send.mutate(
                  { student: card.id, domain, comment },
                  {
                    onSuccess: () => {
                      toast.success(t('{owner} получит уведомление', { owner: t(OWNER_OF[domain]) }))
                      setComment('')
                      setOpen(false)
                    },
                    onError: (e) => toast.error(e.message),
                  },
                )
              }
            >
              {t('Передать')}
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

/** Передать строку очереди владельцу её домена. Кнопка подписана адресатом. */
export function EscalateRowDialog({ id, domain }: { id: number; domain: string }) {
  const [open, setOpen] = useState(false)
  const [comment, setComment] = useState('')
  const { escalate } = useEscalateSuggestion()
  const owner = OWNER_OF[domain]
  // имя владельца подставляется в целую фразу; без имени — своя фраза «владельцу»
  const passTo = owner ? t('Передать {owner}', { owner: t(owner) }) : t('Передать владельцу')

  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
        {passTo}
      </Button>
      {open && (
        <Modal title={passTo} note={t('Строка уйдёт из вашей очереди к владельцу домена. Он увидит ваш комментарий.')} onClose={() => setOpen(false)}>
          <Field kind="textarea" name="comment" label={t('Комментарий')} value={comment} onChange={setComment} rows={3} placeholder={t('Что смущает')} autoFocus />
          <div className="acad__actions">
            <Button
              disabled={escalate.isPending || !comment.trim()}
              onClick={() =>
                escalate.mutate(
                  { id, comment },
                  {
                    onSuccess: () => {
                      toast.success(owner ? t('Передано {owner}', { owner: t(owner) }) : t('Передано владельцу'))
                      setOpen(false)
                    },
                    onError: (e) => toast.error(e.message),
                  },
                )
              }
            >
              {t('Передать')}
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
