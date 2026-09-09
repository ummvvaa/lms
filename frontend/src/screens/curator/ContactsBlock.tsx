/**
 * Контакты родителей в карточке (фаза 66).
 *
 * До 66-й куратор их только читал: телефон, по которому он звонит,
 * правила заводила директор школы. На практике устаревший номер узнаёт
 * тот, кто по нему звонит, — поэтому телефон и почту куратор правит сам,
 * по своим группам. Домен остаётся за директором школы: она видит всю
 * школу и ведёт список целиком.
 *
 * Рядом — «Написать родителям», если почта есть. Письмо система не
 * отправляет, а открывает в почте куратора.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useContactRows, useContacts, type CuratorCard as Card } from '../../api/hooks'
import type { LetterTarget } from '../../components/LetterDialog'
import { Row, Rows } from '../../components/patterns'
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
  const { update } = useContactRows()
  const [editing, setEditing] = useState<number | null>(null)
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')

  const rows = contacts.data?.results ?? []
  const withEmail = rows.some((row) => row.email)

  return (
    <DataCard
      title={t('Контакты')}
      note={t('Ведёт директор школы — Салтанат')}
      right={
        withEmail ? (
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
        ) : undefined
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
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setEditing(contact.id)
                    setPhone(contact.phone)
                    setEmail(contact.email)
                  }}
                >
                  {t('Поправить')}
                </Button>
              }
            />
          ),
        )}
      </Rows>
    </DataCard>
  )
}
