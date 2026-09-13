/**
 * Контакты родителей в карточке (фаза 66, дополнено в 70).
 *
 * До 66-й куратор их только читал: телефон, по которому он звонит,
 * правила заводила директор школы. На практике устаревший номер узнаёт
 * тот, кто по нему звонит, — поэтому телефон и почту куратор правит сам,
 * по своим группам. Домен остаётся за директором школы: она видит всю
 * школу и ведёт список целиком.
 *
 * С фазы 70 он и заводит контакт: право было с 66-й, а кнопки не было —
 * в карточке нового ученика стояло «Контактов пока нет», и позвонить
 * было некому, пока Салтанат не заведёт запись руками.
 *
 * Рядом — «Написать родителям», если почта есть. Письмо система не
 * отправляет, а открывает в почте куратора.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useContactRows, useContacts, type CuratorCard as Card } from '../../api/hooks'
import type { LetterTarget } from '../../components/LetterDialog'
import Modal from '../../components/Modal'
import { Row, Rows } from '../../components/patterns'
import { RELATION_OPTIONS } from '../../components/StudentRows'
import { SelectField } from '../../components/SelectField'
import { DataCard } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { t } from '../../i18n'

export default function ContactsBlock({
  card,
  onWrite,
}: {
  card: Card
  onWrite: (target: LetterTarget) => void
}) {
  const contacts = useContacts({ student: card.id })
  const { create, update, drop } = useContactRows()
  const [editing, setEditing] = useState<number | null>(null)
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [adding, setAdding] = useState(false)
  const [fresh, setFresh] = useState({ full_name: '', relation: 'mother', phone: '', email: '' })
  // убираем по подтверждению, и в нём написано имя: контакт — это человек,
  // по которому звонят, а не строка таблицы (фаза 70)
  const [dropping, setDropping] = useState<{ id: number; name: string } | null>(null)

  const rows = contacts.data?.results ?? []
  const withEmail = rows.some((row) => row.email)

  return (
    <DataCard
      title={t('Контакты')}
      note={t('Ведёт директор школы — Салтанат, куратор — по своим группам')}
      right={
        <>
          {withEmail && (
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                onWrite({
                  students: [card.id],
                  kind: 'free',
                  title: t('Написать родителям'),
                })
              }
            >
              {t('Написать родителям')}
            </Button>
          )}
          <Button size="sm" onClick={() => setAdding(true)}>
            {t('Добавить контакт')}
          </Button>
        </>
      }
    >
      {rows.length === 0 && <p className="muted">{t('Контактов пока нет')}</p>}
      <Rows>
        {rows.map((contact) =>
          editing === contact.id ? (
            <div key={contact.id} className="ctask__field">
              <Input
                value={phone}
                placeholder={t('Телефон')}
                aria-label={`${t('Телефон')}: ${contact.full_name}`}
                onChange={(event) => setPhone(event.target.value)}
              />
              <Input
                value={email}
                placeholder={t('Почта')}
                aria-label={`${t('Почта')}: ${contact.full_name}`}
                onChange={(event) => setEmail(event.target.value)}
              />
              <Button
                size="sm"
                disabled={update.isPending}
                onClick={() =>
                  update.mutate(
                    { id: contact.id, phone, email },
                    {
                      onSuccess: () => {
                        setEditing(null)
                        toast.success(t('Контакт обновлён'))
                      },
                      onError: (error) => toast.error(error.message),
                    },
                  )
                }
              >
                {t('Сохранить')}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                {t('Отмена')}
              </Button>
            </div>
          ) : (
            <Row
              key={contact.id}
              icon="person"
              title={contact.full_name}
              note={`${contact.relation_title} · ${contact.phone || contact.email || t('контакта нет')}`}
              right={
                <>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setEditing(contact.id)
                      setPhone(contact.phone)
                      setEmail(contact.email)
                    }}
                  >
                    {t('Изменить')}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setDropping({ id: contact.id, name: contact.full_name })}
                  >
                    {t('Убрать')}
                  </Button>
                </>
              }
            />
          ),
        )}
      </Rows>

      {adding && (
        <Modal title={t('Добавить контакт')} onClose={() => setAdding(false)}>
          <div className="ctask__field">
            <Input
              value={fresh.full_name}
              placeholder={t('ФИО родителя или опекуна')}
              aria-label={t('ФИО родителя или опекуна')}
              onChange={(event) => setFresh({ ...fresh, full_name: event.target.value })}
            />
            <SelectField
              value={fresh.relation}
              aria-label={t('Кем приходится ученику')}
              onChange={(event) => setFresh({ ...fresh, relation: event.target.value })}
            >
              {RELATION_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {t(option.title)}
                </option>
              ))}
            </SelectField>
            <Input
              value={fresh.phone}
              placeholder={t('Телефон')}
              aria-label={t('Телефон')}
              onChange={(event) => setFresh({ ...fresh, phone: event.target.value })}
            />
            <Input
              value={fresh.email}
              placeholder={t('Почта')}
              aria-label={t('Почта')}
              onChange={(event) => setFresh({ ...fresh, email: event.target.value })}
            />
          </div>
          <div className="ctask__actions">
            <span className="muted">{t('Телефон или почта — хотя бы одно: по ним и звонят')}</span>
            <span className="cfilters__spacer" />
            <Button
              size="sm"
              disabled={create.isPending || !fresh.full_name.trim() || !(fresh.phone.trim() || fresh.email.trim())}
              onClick={() =>
                create.mutate(
                  {
                    student: card.id,
                    full_name: fresh.full_name.trim(),
                    relation: fresh.relation,
                    phone: fresh.phone.trim(),
                    email: fresh.email.trim(),
                    preferred_channel: '',
                    note: '',
                    is_primary: rows.length === 0,
                  },
                  {
                    onSuccess: () => {
                      setAdding(false)
                      setFresh({ full_name: '', relation: 'mother', phone: '', email: '' })
                      toast.success(t('Контакт добавлен'))
                    },
                    onError: (error) => toast.error(error.message),
                  },
                )
              }
            >
              {t('Добавить')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setAdding(false)}>
              {t('Отмена')}
            </Button>
          </div>
        </Modal>
      )}

      {dropping && (
        <Modal title={t('Убрать контакт?')} onClose={() => setDropping(null)}>
          <p>
            {t('Контакт уйдёт из карточки:')} <b>{dropping.name}</b>
          </p>
          <div className="ctask__actions">
            <span className="cfilters__spacer" />
            <Button
              size="sm"
              disabled={drop.isPending}
              onClick={() =>
                drop.mutate(dropping.id, {
                  onSuccess: () => {
                    setDropping(null)
                    toast.success(t('Контакт убран'))
                  },
                  onError: (error) => toast.error(error.message),
                })
              }
            >
              {t('Убрать')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setDropping(null)}>
              {t('Отмена')}
            </Button>
          </div>
        </Modal>
      )}
    </DataCard>
  )
}
