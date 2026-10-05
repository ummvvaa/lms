/**
 * «Проверка ДЗ» — задания со сдачей в LMS по своим урокам (30.09.2026).
 *
 * Три вкладки: есть непроверенные работы, срок ещё идёт, всё проверено.
 * Строка — задание: кому, срок и что после него, сколько сдали и сколько
 * ждут проверки; «Проверять» открывает работы по одной. Кымбат
 * и администратор видят задания всей школы, учитель — своих уроков
 * (решает сервер). На телефоне таблица — списком.
 */
import { useNavigate, useSearchParams } from 'react-router'
import { useReviewList, type ReviewItem, type ReviewTab } from '../../api/homework'
import { useAuth } from '../../auth/AuthContext'
import DataTable, { type Column } from '../../components/DataTable'
import { Row, Rows } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { usePhone } from '../../phone'
import { dueWords, firstLine } from './homeworkParts'
import { dateWords } from './shared'

const TABS: ReviewTab[] = ['unchecked', 'running', 'checked']

const EMPTY: Record<ReviewTab, string> = {
  unchecked: tk('непроверенных работ нет'),
  running: tk('заданий, у которых идёт срок, нет'),
  checked: tk('проверенных заданий пока нет'),
}

/** Название задания в списке: первая строка текста, иначе предмет. */
const titleOf = (item: ReviewItem) => firstLine(item.text, item.lesson.subject)

/** «с опозданием можно» или «закрыто после срока». */
const policyWords = (item: ReviewItem) => (item.late_policy === 'close' ? t('закрыто после срока') : t('с опозданием можно'))

export default function HomeworkReview() {
  const navigate = useNavigate()
  const phone = usePhone()
  const { me } = useAuth()
  const [params, setParams] = useSearchParams()
  const list = useReviewList()
  if (list.isLoading) return <Loading kind="table" />
  if (list.error) return <ErrorNote error={list.error} />
  if (!list.data) return null

  const { items, counts } = list.data
  const asked = params.get('tab') as ReviewTab | null
  // без выбора — первая вкладка, где что-то есть
  const tab: ReviewTab = asked && TABS.includes(asked) ? asked : (TABS.find((code) => counts[code] > 0) ?? 'unchecked')
  const rows = items.filter((item) => item.tab === tab)
  const wholeSchool = me?.role === 'admin' || me?.role === 'director_exam'
  const open = (item: ReviewItem) => navigate(`/homework-review/${item.id}`)
  const setTab = (next: ReviewTab) => {
    const copy = new URLSearchParams(params)
    copy.set('tab', next)
    setParams(copy, { replace: true })
  }
  const lessonNote = (item: ReviewItem) =>
    [wholeSchool ? item.lesson.subject : '', t('урок {date}', { date: dateWords(item.lesson.date) }), wholeSchool && item.lesson.teacher ? item.lesson.teacher.short : ''].filter(Boolean).join(' · ')

  const columns: Column<ReviewItem>[] = [
    {
      key: 'task',
      title: t('Задание'),
      width: '32%',
      cell: (item) => (
        <>
          <b>{titleOf(item)}</b>
          <span className="t-note"> · {lessonNote(item)}</span>
        </>
      ),
      sortBy: (item) => item.lesson.date,
    },
    { key: 'who', title: t('Кому'), width: '14%', cell: (item) => item.lesson.cohort, sortBy: (item) => item.lesson.cohort },
    {
      key: 'due',
      title: t('Срок'),
      width: '18%',
      cell: (item) => (
        <>
          <span className="num">{dueWords(item.due_at)}</span>
          <span className="t-note"> · {policyWords(item)}</span>
        </>
      ),
      sortBy: (item) => item.due_at ?? '',
    },
    {
      key: 'done',
      title: t('Сдали'),
      width: '16%',
      cell: (item) => (
        <span className="hwlist__done">
          <Bar percent={item.total ? (item.submitted / item.total) * 100 : 0} color="var(--good)" />
          <span className="num">{t('{done} из {total}', { done: item.submitted, total: item.total })}</span>
        </span>
      ),
      sortBy: (item) => (item.total ? item.submitted / item.total : 0),
    },
    {
      key: 'wait',
      title: t('Не проверено'),
      width: '10%',
      align: 'right',
      cell: (item) =>
        item.unchecked ? (
          <Chip tone="accent" size="sm" className="num">
            {String(item.unchecked)}
          </Chip>
        ) : (
          <span className="t-note">{t('нет')}</span>
        ),
      sortBy: (item) => item.unchecked,
    },
    {
      key: 'open',
      title: '',
      width: '10%',
      align: 'right',
      cell: (item) => (
        <Button variant={item.unchecked ? 'secondary' : 'outline'} size="sm" onClick={() => open(item)}>
          {item.unchecked ? t('Проверять') : t('Открыть')}
        </Button>
      ),
    },
  ]

  return (
    <div>
      <ScreenHead title={t('Проверка ДЗ')} subtitle={wholeSchool ? t('Задания со сдачей в LMS по всей школе') : t('Задания со сдачей по вашим урокам')} />
      <ScreenTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'unchecked', label: t('Есть непроверенные {n}', { n: counts.unchecked }) },
          { value: 'running', label: t('Срок ещё идёт {n}', { n: counts.running }) },
          { value: 'checked', label: t('Всё проверено {n}', { n: counts.checked }) },
        ]}
      />
      {items.length === 0 ? (
        <div className="acad__cols acad__cols--even">
          <DataCard title={t('Задания со сдачей')} empty={t('заданий со сдачей в LMS пока нет')} />
          <DataCard title={t('Как задать ДЗ со сдачей')}>
            <p className="acad__note">
              {t('Откройте урок, запишите домашнее задание и включите «Нужна сдача в LMS». Ученики загрузят работы в разделе «Домашние задания», а здесь появится задание с их работами.')}
            </p>
          </DataCard>
        </div>
      ) : rows.length === 0 ? (
        <DataCard title={t('Задания со сдачей')} empty={t(EMPTY[tab])} />
      ) : phone ? (
        <DataCard title={t('Задания со сдачей')} count={rows.length}>
          <Rows>
            {rows.map((item) => (
              <Row
                key={item.id}
                icon="homework"
                tone={item.unchecked ? 'accent' : 'neutral'}
                title={titleOf(item)}
                note={`${item.lesson.cohort} · ${t('срок {due}', { due: dueWords(item.due_at) })} · ${t('сдали {done} из {total}', { done: item.submitted, total: item.total })}`}
                value={item.unchecked || null}
                none={item.submitted ? t('проверено') : t('ещё не сдавали')}
                to={`/homework-review/${item.id}`}
              />
            ))}
          </Rows>
        </DataCard>
      ) : (
        <div className="card">
          <DataTable columns={columns} rows={rows} rowKey={(item) => item.id} onRowClick={open} limit={30} />
        </div>
      )}
    </div>
  )
}
