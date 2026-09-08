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
import { useEscalateStudent, useEscalateSuggestion, useParentCall, type CuratorCard } from '../../api/hooks'
import Modal from '../../components/Modal'
import { SelectField } from '../../components/SelectField'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Textarea } from '../../components/ui/textarea'
import { t } from '../../i18n'

/** Владелец домена по коду — подпись кнопок и адресат. Из реестра, не выдумка экрана. */
export const OWNER_OF: Record<string, string> = { exam: 'Кымбат', documents: 'Асем' }

export function CallDialog({ card }: { card: CuratorCard }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const call = useParentCall()
  const primary = card.contacts[0]

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        {t('Родителям')}
      </Button>
      {open && (
        <Modal title={t('Позвонить родителям')} onClose={() => setOpen(false)}>
          <div className="ctask">
            <dl className="ckv">
              <dt>{t('Ученик')}</dt>
              <dd>{card.full_name}</dd>
              <dt>{t('Телефон')}</dt>
              <dd>
                {primary ? (
                  <>
                    {primary.phone ? (
                      <a href={`tel:${primary.phone.replace(/\s/g, '')}`}>{primary.phone}</a>
                    ) : (
                      primary.email
                    )}
                    <span className="muted">
                      {' '}
                      · {primary.full_name}, {primary.relation_title}
                    </span>
                  </>
                ) : (
                  <span className="muted">{t('Контактов пока нет')}</span>
                )}
              </dd>
              <dt>{t('Контакт ведёт')}</dt>
              <dd>
                <Badge variant="mute">{t('Салтанат')}</Badge>
              </dd>
            </dl>
            <label className="ctask__field">
              <span className="eyebrow">{t('О чём говорили — запишется в заметки')}</span>
              <Textarea
                rows={3}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={t('Коротко')}
              />
            </label>
            <div className="ctask__actions">
              <Button variant="outline" onClick={() => setOpen(false)}>
                {t('Закрыть')}
              </Button>
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
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}

export function EscalateStudentDialog({ card }: { card: CuratorCard }) {
  const [open, setOpen] = useState(false)
  const [domain, setDomain] = useState<'exam' | 'documents'>('exam')
  const [comment, setComment] = useState('')
  const send = useEscalateStudent()

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        {t('Передать')}
      </Button>
      {open && (
        <Modal title={t('Передать владельцу домена')} onClose={() => setOpen(false)}>
          <div className="ctask">
            <p className="muted">
              {t('Владелец получит уведомление с вашим комментарием и ссылкой на карточку')} {card.full_name}.
            </p>
            <label className="ctask__field">
              <span className="eyebrow">{t('Кому')}</span>
              <SelectField value={domain} onChange={(e) => setDomain(e.target.value as 'exam' | 'documents')}>
                <option value="exam">
                  {t('Кымбат')} · {t('экзамены')}
                </option>
                <option value="documents">
                  {t('Асем')} · {t('документы')}
                </option>
              </SelectField>
            </label>
            <label className="ctask__field">
              <span className="eyebrow">{t('Что нужно от владельца')}</span>
              <Textarea
                rows={3}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder={t('Например: балл IELTS расходится с сертификатом, нужно решение')}
              />
            </label>
            <div className="ctask__actions">
              <Button variant="outline" onClick={() => setOpen(false)}>
                {t('Отмена')}
              </Button>
              <Button
                disabled={send.isPending || !comment.trim()}
                onClick={() =>
                  send.mutate(
                    { student: card.id, domain, comment },
                    {
                      onSuccess: () => {
                        toast.success(`${OWNER_OF[domain]} ${t('получит уведомление')}`)
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
            </div>
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
  const owner = OWNER_OF[domain] ?? t('владельцу')

  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
        {t('Передать')} {owner}
      </Button>
      {open && (
        <Modal title={`${t('Передать')} ${owner}`} onClose={() => setOpen(false)}>
          <div className="ctask">
            <p className="muted">
              {t('Строка уйдёт из вашей очереди к владельцу домена. Он увидит ваш комментарий.')}
            </p>
            <label className="ctask__field">
              <span className="eyebrow">{t('Комментарий')}</span>
              <Textarea
                rows={3}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder={t('Что смущает')}
              />
            </label>
            <div className="ctask__actions">
              <Button variant="outline" onClick={() => setOpen(false)}>
                {t('Отмена')}
              </Button>
              <Button
                disabled={escalate.isPending || !comment.trim()}
                onClick={() =>
                  escalate.mutate(
                    { id, comment },
                    {
                      onSuccess: () => {
                        toast.success(`${t('Передано')} ${owner}`)
                        setOpen(false)
                      },
                      onError: (e) => toast.error(e.message),
                    },
                  )
                }
              >
                {t('Передать')}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}
