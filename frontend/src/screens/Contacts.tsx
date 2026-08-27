/**
 * Контакты родителей и опекунов — список школы целиком, с поиском.
 *
 * Ведёт раздел директор школы: это её домен. На карточке ученика те же
 * контакты видны своим блоком, здесь — все сразу, чтобы найти нужный
 * телефон, не открывая карточку.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useContactRows, useContacts, useStudents } from '../api/hooks'
import DeleteButton from '../components/DeleteButton'
import Empty from '../components/Empty'
import ManualEntryNote from '../components/ManualEntryNote'
import RowForm from '../components/RowForm'
import { CONTACT_FIELDS, contactBody } from '../components/StudentRows'
import { counted, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'
import { NativeSelect } from '../components/ui/native-select'
import { Input } from '../components/ui/input'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import RowMenu, { RowMenuItem, RowMenuSeparator } from '../components/RowMenu'

export default function Contacts() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [student, setStudent] = useState('')
  const [problem, setProblem] = useState<string | null>(null)

  const contacts = useContacts({ search })
  const students = useStudents({ page_size: 500 })
  const rows = useContactRows()

  const list = contacts.data?.results ?? []

  return (
    <div>
      <ScreenHead
        title={t('Контакты родителей')}
        subtitle={t('Кому звонить по каждому ученику.')}
        actions={
          <Button onClick={() => setAdding(!adding)}>{adding ? t('Отмена') : t('Добавить контакт')}</Button>
        }
      />

      <ManualEntryNote />

      <div className="toolbar">
        <Input
          placeholder={t('Поиск по имени, телефону или ученику')}
          aria-label={t('Поиск по контактам')}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <span className="toolbar__spacer" />
        <span className="muted">
          {counted(contacts.data?.count ?? 0, ['контакт', 'контакта', 'контактов'])}
        </span>
      </div>

      {adding && (
        <DataCard title={t('Новый контакт')} note={t('Сначала выберите, чей это родитель')}>
          <label className="rows__picker">
            <span className="rowform__label">{t('Ученик')}</span>
            <NativeSelect value={student} onChange={(event) => setStudent(event.target.value)}>
              <option value="">{t('— ученик не выбран —')}</option>
              {(students.data?.results ?? []).map((row) => (
                <option key={row.id} value={row.id}>
                  {row.full_name}
                </option>
              ))}
            </NativeSelect>
          </label>
          {problem && (
            <Badge variant="risk" className="badge--line">
              {problem}
            </Badge>
          )}
          <RowForm
            fields={CONTACT_FIELDS}
            busy={rows.create.isPending}
            submitLabel={t('Добавить')}
            onCancel={() => setAdding(false)}
            onSubmit={(values) => {
              if (!student) {
                setProblem('Выберите ученика — контакт принадлежит конкретному человеку')
                return
              }
              setProblem(null)
              rows.create.mutate(
                { student: Number(student), ...contactBody(values) },
                {
                  onSuccess: () => setAdding(false),
                  onError: (error) =>
                    setProblem(error instanceof Error ? error.message : 'Не удалось завести контакт'),
                },
              )
            }}
          />
        </DataCard>
      )}

      {contacts.isLoading && <Loading kind="table" />}
      {contacts.error && <ErrorNote error={contacts.error} />}

      {!contacts.isLoading && list.length === 0 && !adding && (
        <Empty
          icon="person"
          title={search ? t('По этому поиску никого нет') : t('Контактов пока нет')}
          what={
            search
              ? t('Очистите поиск, чтобы увидеть все контакты.')
              : t('Заведите первый контакт руками; список файлом загружает администратор.')
          }
          action={search ? t('Очистить поиск') : t('Добавить контакт')}
          onAction={search ? () => setSearch('') : () => setAdding(true)}
        />
      )}

      {list.length > 0 && (
        <DataCard title={t('Все контакты школы')} note={t('Основной помечен отдельно')} count={list.length}>
          <ul className="rows__list">
            {list.map((row) => (
              <li key={row.id} className="rows__item">
                <div className="rows__body">
                  <div>
                    <span className="rows__label">
                      {row.full_name}
                      {row.is_primary ? ` · ${t('основной')}` : ''}
                    </span>
                    <span className="muted rows__note">
                      {' '}
                      ·{' '}
                      {[row.relation_title, row.phone, row.email, row.channel_title]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </div>
                  <div className="rows__actions">
                    <Button variant="outline" size="sm" onClick={() => navigate(`/students/${row.student}`)}>
                      {row.student_name}
                    </Button>
                    <RowMenu>
                      <RowMenuItem onClick={() => setEditing(editing === row.id ? null : row.id)}>
                        {t('Изменить')}
                      </RowMenuItem>
                      <RowMenuSeparator />
                      <RowMenuItem risk keepOpen>
                        <DeleteButton
                          inMenu
                          model="students.ParentContact"
                          id={row.id}
                          path="/contacts/"
                          invalidate={[['contacts']]}
                        />
                      </RowMenuItem>
                    </RowMenu>
                  </div>
                </div>
                {editing === row.id && (
                  <RowForm
                    fields={CONTACT_FIELDS}
                    row={{
                      full_name: row.full_name,
                      relation: row.relation,
                      phone: row.phone,
                      email: row.email,
                      preferred_channel: row.preferred_channel,
                      note: row.note,
                      is_primary: row.is_primary,
                    }}
                    busy={rows.update.isPending}
                    submitLabel={t('Сохранить')}
                    onCancel={() => setEditing(null)}
                    onSubmit={(values) =>
                      rows.update.mutate(
                        { id: row.id, ...contactBody(values) },
                        { onSuccess: () => setEditing(null) },
                      )
                    }
                  />
                )}
              </li>
            ))}
          </ul>
        </DataCard>
      )}
    </div>
  )
}
