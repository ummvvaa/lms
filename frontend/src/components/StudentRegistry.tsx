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
import Empty from './Empty'
import { counted, ErrorNote, Loading, ScreenHead } from './ui'
import { t } from '../i18n'

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
        <input
          className="input"
          placeholder={t('Поиск по имени или почте')}
          aria-label={t('Поиск по имени')}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <span className="toolbar__spacer" />
        <span className="muted">{counted(students.data?.count ?? 0, ['ученик', 'ученика', 'учеников'])}</span>
        <AddStudent onCreated={(id) => navigate(`/students/${id}`)} />
      </div>

      {students.isLoading && <Loading />}
      {students.error && <ErrorNote error={students.error} />}

      {!students.isLoading && rows.length === 0 && (
        <Empty
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
        <div className="card card-pad users__wrap">
          <table className="history users__table">
            <thead>
              <tr>
                <th>{t('Ученик')}</th>
                <th>{t('Класс')}</th>
                <th>{t('Группа')}</th>
                <th>{t('Почта')}</th>
                <th>{t('Выпуск')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <button className="cell cell-link" onClick={() => navigate(`/students/${row.id}`)}>
                      {row.full_name}
                    </button>
                  </td>
                  <td className="num">{row.grade}</td>
                  <td className="num">{row.group_code ?? '—'}</td>
                  <td className="muted">{row.email}</td>
                  <td className="num">{row.graduation_year}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
