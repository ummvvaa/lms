/**
 * «Проверка ДЗ» — задания со сдачей в LMS по своим урокам (30.09.2026).
 *
 * Три вкладки: есть непроверенные работы, срок ещё идёт, всё проверено.
 * Строка — задание: кому, срок и что после него, сколько сдали и сколько
 * ждут проверки; «Проверять» открывает работы по одной. Кымбат
 * и администратор видят задания всей школы, учитель — своих уроков
 * (решает сервер). Раскладка — по макету Homework: список заданий на две
 * трети, справа — как дать ДЗ со сдачей; на телефоне — столбиком.
 */
import { Link, useSearchParams } from 'react-router'
import { useReviewList, type ReviewItem, type ReviewTab } from '../../api/homework'
import { useAuth } from '../../auth/AuthContext'
import { ShowAll } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../../components/ui'
import { t, tk } from '../../i18n'
import Icon from '../../layout/icons'
import { dueWords, firstLine } from './homeworkParts'
import { dateWords } from './shared'
import './homework-review-layout.css'

const TABS: ReviewTab[] = ['unchecked', 'running', 'checked']

const EMPTY: Record<ReviewTab, string> = {
  unchecked: tk('непроверенных работ нет'),
  running: tk('заданий, у которых идёт срок, нет'),
  checked: tk('проверенных заданий пока нет'),
}

/** Название задания в списке: первая строка текста, иначе предмет. */
const titleOf = (item: ReviewItem) => firstLine(item.text, item.lesson.subject)

/** «с опозданием можно» или «закрыто после срока». */
const policyWords = (item: ReviewItem) =>
  item.late_policy === 'close' ? t('закрыто после срока') : t('с опозданием можно')

export default function HomeworkReview() {
  const { me } = useAuth()
  const [params, setParams] = useSearchParams()
  const list = useReviewList()
  if (list.isLoading) return <Loading kind="table" />
  if (list.error) return <ErrorNote error={list.error} />
  if (!list.data) return null

  const { items, counts } = list.data
  const asked = params.get('tab') as ReviewTab | null
  // без выбора — первая вкладка, где что-то есть
  const tab: ReviewTab =
    asked && TABS.includes(asked) ? asked : (TABS.find((code) => counts[code] > 0) ?? 'unchecked')
  const rows = items.filter((item) => item.tab === tab)
  const wholeSchool = me?.role === 'admin' || me?.role === 'director_exam'
  const setTab = (next: ReviewTab) => {
    const copy = new URLSearchParams(params)
    copy.set('tab', next)
    setParams(copy, { replace: true })
  }
  const lessonNote = (item: ReviewItem) =>
    [
      wholeSchool ? item.lesson.subject : '',
      t('урок {date}', { date: dateWords(item.lesson.date) }),
      wholeSchool && item.lesson.teacher ? item.lesson.teacher.short : '',
    ]
      .filter(Boolean)
      .join(' · ')

  // задание строкой-кнопкой, как в макете: иконка, название и откуда оно,
  // справа — сдали из скольких полосой и что ждёт проверки; ссылка открывает работы
  const itemRow = (item: ReviewItem) => (
    <Link key={item.id} className="hwr-item lift" to={`/homework-review/${item.id}`}>
      <span className="hwr-item__ico" aria-hidden="true">
        <Icon name="homework" size={20} />
      </span>
      <span className="hwr-item__text">
        <b className="hwr-item__title">{titleOf(item)}</b>
        <span className="t-note">{[item.lesson.cohort, lessonNote(item)].filter(Boolean).join(' · ')}</span>
      </span>
      <span className="hwr-item__side">
        <span className="hwr-item__line">
          <span className="t-note num">
            {t('сдали {done} из {total}', { done: item.submitted, total: item.total })}
          </span>
          {item.unchecked > 0 && (
            <Chip tone="accent" size="sm" className="num">
              {t('не проверено {n}', { n: item.unchecked })}
            </Chip>
          )}
        </span>
        <Bar percent={item.total ? (item.submitted / item.total) * 100 : 0} color="var(--good)" />
        <span className="t-note">
          {t('срок {due}', { due: dueWords(item.due_at) })} · {policyWords(item)}
        </span>
      </span>
      <span className="hwr-item__go" aria-hidden="true">
        <Icon name="chevronRight" size={16} />
      </span>
    </Link>
  )

  const tabLabel = (title: string, n: number) => (
    <>
      {title}
      <span className="tabs__n num">{n}</span>
    </>
  )

  return (
    <div className="lay-screen hwr-screen">
      <ScreenHead
        title={t('Проверка ДЗ')}
        subtitle={
          wholeSchool ? t('Задания со сдачей в LMS по всей школе') : t('Задания со сдачей по вашим урокам')
        }
      />
      <ScreenTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'unchecked', label: tabLabel(t('Есть непроверенные'), counts.unchecked) },
          { value: 'running', label: tabLabel(t('Срок ещё идёт'), counts.running) },
          { value: 'checked', label: tabLabel(t('Всё проверено'), counts.checked) },
        ]}
      />
      <div className="lay-3 hwr-cols">
        {items.length === 0 || rows.length === 0 ? (
          <section className="card card-pad lay-span2 hwr-empty">
            <span className="hwr-item__ico" aria-hidden="true">
              <Icon name="homework" size={20} />
            </span>
            <b>{t('Задания со сдачей')}</b>
            <span className="t-note">
              {items.length === 0 ? t('заданий со сдачей в LMS пока нет') : t(EMPTY[tab])}
            </span>
          </section>
        ) : (
          <DataCard className="lay-span2" title={t('Задания со сдачей')} count={rows.length}>
            <div className="hwr-list">
              <ShowAll>{rows.map(itemRow)}</ShowAll>
            </div>
          </DataCard>
        )}
        <DataCard title={t('Как дать ДЗ со сдачей')}>
          <ol className="hwr-steps">
            <li>
              <span className="hwr-steps__n num">1</span>
              <span>{t('Учитель открывает урок и записывает домашнее задание')}</span>
            </li>
            <li>
              <span className="hwr-steps__n num">2</span>
              <span>{t('Включает «Нужна сдача в LMS»')}</span>
            </li>
            <li>
              <span className="hwr-steps__n num">3</span>
              <span>
                {t('Ученики загружают работы в разделе «Домашние задания» — задание появляется здесь')}
              </span>
            </li>
          </ol>
        </DataCard>
      </div>
    </div>
  )
}
