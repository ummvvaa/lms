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

 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useContactRows, useContacts, type CuratorCard as Card } from '../../api/hooks'
import ConfirmDialog from '../../components/ConfirmDialog'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Row, Rows } from '../../components/patterns'
import { RELATION_OPTIONS } from '../../components/StudentRows'
import { DataCard, EmptyNote } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'

export default function ContactsBlock({ card }: { card: Card }) {
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

  return (
    <DataCard
      title={t('Контакты')}
      right={
        <Button size="sm" onClick={() => setAdding(true)}>
          {t('Добавить контакт')}
        </Button>
      }
    >
      {/* Пустая строка вместо карточки-пустышки, но кнопки и форма
          остаются: контакт заводят отсюда же */}
      {rows.length === 0 && !adding && (
        <EmptyNote what="контактов пока не записано" who="ведёт директор школы и куратор" />
      )}
      <Rows>
        {rows.map((contact) =>
          editing === contact.id ? (
            <div key={contact.id} className="cnotes__form">
              <Field.Row>
                <Field kind="text" name="phone" label={`${t('Телефон')}: ${contact.full_name}`} value={phone} onChange={setPhone} placeholder={t('Телефон')} />
                <Field kind="text" name="email" label={t('Почта')} value={email} onChange={setEmail} placeholder={t('Почта')} />
              </Field.Row>
              <div className="acad__actions">
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
            </div>
          ) : (
            <Row
              key={contact.id}
              icon="person"
              title={contact.full_name}
              note={`${contact.relation_title} · ${contact.phone || contact.email || t('контакта нет')}`}
              acts={
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
        <Modal title={t('Добавить контакт')} note={t('Телефон или почта — хотя бы одно: по ним и звонят')} onClose={() => setAdding(false)}>
          <Field kind="text" name="full_name" label={t('ФИО родителя или опекуна')} value={fresh.full_name} onChange={(value) => setFresh({ ...fresh, full_name: value })} autoFocus />
          <Field
            kind="select"
            name="relation"
            label={t('Кем приходится ученику')}
            value={fresh.relation}
            onChange={(value) => setFresh({ ...fresh, relation: value })}
            options={RELATION_OPTIONS.map((option) => ({ value: option.value, title: t(option.title) }))}
          />
          <Field.Row>
            <Field kind="text" name="phone" label={t('Телефон')} value={fresh.phone} onChange={(value) => setFresh({ ...fresh, phone: value })} placeholder="+7 7__ ___ __ __" />
            <Field kind="text" name="email" label={t('Почта')} value={fresh.email} onChange={(value) => setFresh({ ...fresh, email: value })} />
          </Field.Row>
          <div className="acad__actions">
            <Button
              size="sm"
              disabled={
                create.isPending || !fresh.full_name.trim() || !(fresh.phone.trim() || fresh.email.trim())
              }
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

      <ConfirmDialog
        open={dropping !== null}
        title={t('Убрать контакт?')}
        what={dropping ? `${t('Контакт уйдёт из карточки:')} ${dropping.name}` : undefined}
        confirmLabel={t('Убрать')}
        busy={drop.isPending}
        onCancel={() => setDropping(null)}
        onConfirm={() =>
          dropping &&
          drop.mutate(dropping.id, {
            onSuccess: () => {
              setDropping(null)
              toast.success(t('Контакт убран'))
            },
            onError: (error) => toast.error(error.message),
          })
        }
      />
    </DataCard>
  )
}
