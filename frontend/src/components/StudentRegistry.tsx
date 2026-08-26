/**
 * Реестровый список учеников — экран администратора.
 *
 * Доменных полей здесь нет: их ведут директора у себя. Администратор
 * отвечает за то, кто вообще есть в школе, поэтому заводит и открывает
 * карточки отсюда. Раньше «Таблица» у него упиралась в «у вашей роли
 * нет домена» — пункт меню вёл в тупик.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStudents } from '../api/hooks'
import AddStudent from './AddStudent'
import DataTable from './DataTable'
import Empty from './Empty'
import { counted, ErrorNote, Loading, ScreenHead } from './ui'
import { t } from '../i18n'
import { Input } from './ui/input'

export default function StudentRegistry() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const students = useStudents({ search, page_size: 500 })

  const rows = students.data?.results ?? []

  return (
    <div>
      <ScreenHead
        title={t('Ученики школы')}
        subtitle={t('Кто учится, в каком классе и группе. Доменные поля ведут директора у себя.')}
      />

      <div className="toolbar">
        <Input
          placeholder={t('Поиск по имени или почте')}
          aria-label={t('Поиск по имени')}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <span className="toolbar__spacer" />
        <span className="muted">{counted(students.data?.count ?? 0, ['ученик', 'ученика', 'учеников'])}</span>
        <AddStudent onCreated={(id) => navigate(`/students/${id}`)} />
      </div>

      {students.isLoading && <Loading kind="table" />}
      {students.error && <ErrorNote error={students.error} />}

      {!students.isLoading && rows.length === 0 && (
        <Empty
          icon="people"
          title={search ? 'По этому поиску никого нет' : 'Учеников пока нет'}
          what={
            search
              ? 'Очистите поиск, чтобы увидеть всех.'
              : 'Заведите первого ученика руками или загрузите список файлом.'
          }
          action={search ? 'Очистить поиск' : undefined}
          onAction={search ? () => setSearch('') : undefined}
        />
      )}

      {rows.length > 0 && (
        <div className="card card-pad">
          <DataTable
            columns={[
              {
                key: 'name',
                title: t('Ученик'),
                width: '34%',
                cell: (row) => (
                  <button className="cell cell-link" onClick={() => navigate(`/students/${row.id}`)}>
                    {row.full_name}
                  </button>
                ),
              },
              { key: 'grade', title: t('Класс'), width: '10%', align: 'right', cell: (row) => row.grade },
              {
                key: 'group',
                title: t('Группа'),
                width: '12%',
                cell: (row) => row.group_code ?? '—',
              },
              {
                key: 'email',
                title: t('Почта'),
                width: '30%',
                cell: (row) => <span className="muted">{row.email}</span>,
              },
              {
                key: 'year',
                title: t('Выпуск'),
                width: '14%',
                align: 'right',
                cell: (row) => row.graduation_year,
              },
            ]}
            rows={rows}
            rowKey={(row) => row.id}
          />
        </div>
      )}
    </div>
  )
}
