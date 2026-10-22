/**
 * Реестровый список учеников — экран администратора.
 *
 * Доменных полей здесь нет: их ведут директора у себя. Администратор
 * отвечает за то, кто вообще есть в школе, поэтому заводит и открывает
 * карточки отсюда. Раньше «Таблица» у него упиралась в «у вашей роли
 * нет домена» — пункт меню вёл в тупик.
 */
import { useState } from 'react'
import { useTrack } from '../usage/context'
import { Link, useNavigate } from 'react-router'
import { useStudents } from '../api/hooks'
import DataTable from './DataTable'
import Empty from './Empty'
import Field from './Field'
import Icon from '../layout/icons'
import { Avatar, Segmented } from './patterns'
import { Chip, counted, DataCard, ErrorNote, Loading, ScreenHead } from './ui'
import { t } from '../i18n'
import { Button } from './ui/button'
import { PARALLELS } from '../lib/parallels'
import '../screens/student-registry.css'

export default function StudentRegistry() {
  const trackFilter = useTrack('filter.change')
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  // параллель — у группы; фильтр по ней — по уже загруженному списку, без нового запроса
  const [parallel, setParallel] = useState('all')
  const students = useStudents({ search, page_size: 500 })

  const all = students.data?.results ?? []
  const rows = parallel === 'all' ? all : all.filter((row) => String(row.parallel) === parallel)
  const groups = new Set(all.map((row) => row.group_code).filter(Boolean)).size
  const total = students.data?.count ?? 0

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Ученики школы')}
        subtitle={
          students.data
            ? [counted(total, 'ученик|ученика|учеников'), counted(groups, 'группа|группы|групп')].join(' · ')
            : undefined
        }
        actions={
          // заведение — на «Пользователях» с ролью «ученик»: одно место о человеке (решение владельца, 11.10.2026)
          <Button onClick={() => navigate('/users?new=student')}>
            <Icon name="plus" size={16} />
            {t('Завести ученика')}
          </Button>
        }
      />

      <div className="filters">
        <Field
          usageFilter
          className="filters__search"
          name="registry-search"
          label={t('Поиск по имени')}
          placeholder={t('Поиск по имени или почте')}
          value={search}
          onChange={setSearch}
        />
        <Segmented
          label={t('Все параллели')}
          value={parallel}
          onChange={setParallel}
          items={[
            {
              value: 'all',
              label: (
                <>
                  {t('Все')}
                  <span className="tabs__n num">{all.length}</span>
                </>
              ),
            },
            ...PARALLELS.map((value) => ({
              value: String(value),
              label: (
                <>
                  {t('{n} параллель', { n: value })}
                  <span className="tabs__n num">{all.filter((row) => row.parallel === value).length}</span>
                </>
              ),
            })),
          ]}
        />
      </div>

      {students.isLoading && <Loading kind="table" />}
      {students.error && <ErrorNote error={students.error} />}

      {!students.isLoading && rows.length === 0 && (
        <Empty
          icon="people"
          title={search || parallel !== 'all' ? t('По этому поиску никого нет') : t('Учеников пока нет')}
          what={
            search || parallel !== 'all'
              ? t('Очистите поиск, чтобы увидеть всех.')
              : t('Заведите первого ученика руками или загрузите список файлом.')
          }
          action={search || parallel !== 'all' ? t('Очистить поиск') : undefined}
          onAction={
            search || parallel !== 'all'
              ? () => {
                  trackFilter()
                  setSearch('')
                  setParallel('all')
                }
              : undefined
          }
        />
      )}

      {rows.length > 0 && (
        <DataCard title={t('Список')} count={rows.length}>
          <DataTable
            columns={[
              {
                key: 'name',
                title: t('Ученик'),
                width: '38%',
                cell: (row) => (
                  <Link className="personcell registry__who" to={`/students/${row.id}`}>
                    <Avatar name={row.full_name} />
                    <b>{row.full_name}</b>
                  </Link>
                ),
              },
              {
                key: 'group',
                title: t('Группа'),
                width: '14%',
                cell: (row) =>
                  row.group_code ? (
                    <Chip size="sm" className="num">
                      {row.group_code}
                    </Chip>
                  ) : (
                    <span className="t-note">{t('без группы')}</span>
                  ),
              },
              {
                key: 'email',
                title: t('Почта'),
                width: '32%',
                cell: (row) => <span className="muted registry__mail">{row.email}</span>,
              },
              {
                key: 'year',
                title: t('Выпуск'),
                width: '10%',
                align: 'right',
                cell: (row) => <span className="num">{row.graduation_year}</span>,
              },
              {
                key: 'open',
                title: '',
                width: '6%',
                align: 'right',
                actions: true,
                // на телефоне строка — карточка с именем-ссылкой: отдельная стрелка лишняя
                phone: 'hidden',
                cell: (row) => (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t('Открыть карточку')}
                    onClick={() => navigate(`/students/${row.id}`)}
                  >
                    <Icon name="chevronRight" size={16} />
                  </Button>
                ),
              },
            ]}
            rows={rows}
            rowKey={(row) => row.id}
          />
        </DataCard>
      )}
    </div>
  )
}
