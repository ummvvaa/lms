/**
 * «Сегодня» учителя: уроки по звонкам, что не отмечено, оценки за неделю,
 * журналы, ближайшие СОР и СОЧ, изменения в расписании.
 *
 * Образец — `route(['teacher'], '/dashboard')` референса. Главный сценарий
 * на телефоне: открыть текущий урок и отметить отсутствующих — кнопка
 * «Отметить N урок» стоит первой.
 */
import { Fragment } from 'react'
import { Link, useNavigate } from 'react-router'
import { useTeacherToday } from '../../api/academics'
import Icon from '../../layout/icons'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Bar, Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { MyStaffTasksCard } from '../directors/parts'
import { t, tn } from '../../i18n'
import { Columns } from '../dashboards/home-today'
import { absentWords, dateShort, dateWords, OpenLesson } from './shared'

export default function TeacherToday() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useTeacherToday()
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  if (!data.has_courses)
    return (
      <div className="lay-screen">
        <ScreenHead title={t('Сегодня')} subtitle={data.today_words} />
        <div className="lay-main">
          <div className="lay-stack">
            <DataCard title={t('Уроков пока нет')} empty={t('Кымбат или администратор ещё не поставили вас в расписание')} />
            <DataCard title={t('Журналы')} empty={t('появятся сами, когда у вас будут уроки')} />
          </div>
          <div className="lay-stack">
            <DataCard title={t('Профиль')}>
              <Rows>
                <Row avatar={data.teacher.full_name} title={data.teacher.full_name} note={data.teacher.subject_titles} to="/profile" />
              </Rows>
            </DataCard>
          </div>
        </div>
      </div>
    )

  const live = data.lessons.filter((lesson) => lesson.is_live)
  const now = data.now_lesson
  const first = data.lessons[0]
  const last = data.lessons[data.lessons.length - 1]
  const unmarkedEarlier = data.unmarked.filter((lesson) => lesson.date !== data.today)


  const lessonsCard = (
    <DataCard
      className="card--beam"
      title={t('Уроки сегодня')}
      count={data.lessons.length || undefined}
      empty={data.lessons.length === 0 && t('сегодня у вас уроков нет')}
      right={
        <Button variant="link" size="sm" onClick={() => navigate('/schedule')}>
          {t('Вся неделя')}
        </Button>
      }
    >
      <div className="tday__lessons">
        {data.lessons.map((lesson) => {
          const chip = !lesson.is_live ? (
            <Chip tone="warn">{lesson.status_title}</Chip>
          ) : lesson.state === 'now' ? (
            <Chip tone={lesson.marked ? 'good' : 'accent'}>{lesson.marked ? t('идёт · отмечено') : t('идёт сейчас')}</Chip>
          ) : lesson.state === 'past' ? (
            lesson.marked ? (
              <Chip tone={lesson.absent.length ? 'bad' : 'good'}>{lesson.absent.length ? t('нет {count}', { count: lesson.absent.length }) : t('все были')}</Chip>
            ) : (
              <Chip tone="warn">{t('не отмечен')}</Chip>
            )
          ) : (
            <Chip>{t('впереди')}</Chip>
          )
          return (
            <div key={lesson.id} className={`tday__lesson${lesson.state === 'now' && lesson.is_live ? ' tday__lesson--now' : ''}${lesson.state === 'past' ? ' tday__lesson--past' : ''}`}>
              <span className="tday__slot">
                <b className="num">{lesson.slot}</b>
                {lesson.bell && <span className="num">{lesson.bell.split('–')[0]}</span>}
              </span>
              <span className="tday__what">
                <span className="tday__title">
                  {lesson.title}
                  {lesson.kind !== 'fo' && (
                    <Chip tone={lesson.kind === 'soch' ? 'accent' : 'info'} size="sm">
                      {lesson.kind_label}
                    </Chip>
                  )}
                </span>
                <span className="tday__note">
                  {[
                    lesson.room,
                    counted(lesson.cohort.students, 'ученик|ученика|учеников'),
                    lesson.absent.length ? absentWords(lesson.absent) : '',
                    lesson.is_substitution && lesson.teacher ? t('замена за {teacher}', { teacher: lesson.teacher.short }) : '',
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </span>
              <span className="tday__end">
                {chip}
                {lesson.is_live && (
                  <OpenLesson lesson={lesson} label={lesson.state !== 'future' && !lesson.marked ? t('Отметить') : t('Открыть')} primary={lesson.state !== 'future' && !lesson.marked} />
                )}
              </span>
            </div>
          )
        })}
      </div>
    </DataCard>
  )

  const unmarkedCard = (
    <DataCard title={t('Не отмечено раньше')} count={unmarkedEarlier.length}>
      <Rows>
        <ShowAll>
          {unmarkedEarlier.map((lesson) => (
            <Row
              key={lesson.id}
              title={lesson.title}
              note={`${lesson.weekday}, ${dateWords(lesson.date)}, ${t('{slot} урок', { slot: lesson.slot })}`}
              acts={<OpenLesson lesson={lesson} label={t('Отметить')} primary />}
            />
          ))}
        </ShowAll>
      </Rows>
    </DataCard>
  )

  const journalsCard = (
    <DataCard
      title={t('Мои журналы')}
      count={data.journals.length}
      right={
        <Button variant="link" size="sm" onClick={() => navigate('/journals')}>
          {t('Все')}
        </Button>
      }
    >
      <div className="tday__journals">
        <ShowAll to="/journals">
          {data.journals.map((course) => (
            <Link key={course.id} className="tday__journal" to={`/journals/${course.id}`}>
              <span className="tday__what">
                <span className="tday__title">{course.title}</span>
                <span className="tday__note">{`${counted(course.students, 'ученик|ученика|учеников')} · ${course.cohort.kind_title}`}</span>
              </span>
              <span className="tday__held">
                <span className="tday__note num">{t('проведено {held} из {planned}', { held: course.held, planned: course.planned })}</span>
                <Bar percent={course.planned ? (course.held / course.planned) * 100 : 0} />
              </span>
              <span className="tday__state">
                {course.unmarked ? <Chip tone="warn">{tn(course.unmarked, 'не отмечен {n} урок|не отмечено {n} урока|не отмечено {n} уроков')}</Chip> : <Chip tone="good">{t('всё отмечено')}</Chip>}
              </span>
              <Icon name="chevronRight" size={16} />
            </Link>
          ))}
        </ShowAll>
      </div>
    </DataCard>
  )

  const assessmentsCard = (
    <DataCard
      title={t('Ближайшие СОР и СОЧ')}
      empty={data.assessments.length === 0 && t('в ближайший месяц нет')}
      emptyAction={
        data.assessments.length === 0 ? (
          <Button variant="secondary" size="sm" onClick={() => navigate('/journals')}>
            {t('Запланировать')}
          </Button>
        ) : undefined
      }
      right={
        data.assessments.length > 0 ? (
          <Button variant="link" size="sm" onClick={() => navigate('/journals')}>
            {t('Запланировать')}
          </Button>
        ) : undefined
      }
    >
      <Rows>
        <ShowAll>
          {data.assessments.map((lesson) => (
            <Row
              key={lesson.id}
              lead={<span className={`tday__kind${lesson.kind === 'soch' ? ' tday__kind--soch' : ''}`}>{lesson.kind_label}</span>}
              title={`${lesson.subject.short_title} · ${lesson.cohort.name}`}
              note={`${lesson.weekday}, ${dateWords(lesson.date)} · ${t('{slot} урок', { slot: lesson.slot })}`}
              right={lesson.max_score ? <Chip>{t('из {max}', { max: lesson.max_score })}</Chip> : undefined}
              to={`/lessons/${lesson.id}`}
            />
          ))}
        </ShowAll>
      </Rows>
    </DataCard>
  )

  const changesCard = (
    <DataCard title={t('Изменения в расписании')} count={data.changes.length || undefined} empty={data.changes.length === 0 && t('на две недели всё по плану')}>
      <Rows>
        <ShowAll>
          {data.changes.map((lesson) => (
            <Row
              key={lesson.id}
              icon="refresh"
              tone="warn"
              title={lesson.title}
              note={`${lesson.weekday}, ${dateWords(lesson.date)} · ${lesson.substitute ? `${t('замена:')} ${lesson.substitute.short}` : lesson.status_title}${lesson.reason ? ` · ${lesson.reason}` : ''}`}
              to={`/lessons/${lesson.id}`}
            />
          ))}
        </ShowAll>
      </Rows>
    </DataCard>
  )

  const cards = [
    { key: 'lessons', side: 'main', live: data.lessons.length > 0, node: lessonsCard },
    { key: 'assessments', side: 'aside', live: data.assessments.length > 0, node: assessmentsCard },
    // неотмеченные — под СОР и СОЧ справа: колонки кончаются вровень
    { key: 'unmarked', side: 'aside', live: unmarkedEarlier.length > 0, node: unmarkedEarlier.length > 0 ? unmarkedCard : null },
    // изменений нет — карточки нет, пустая плашка ничего не сообщает
    { key: 'changes', side: 'aside', live: data.changes.length > 0, node: data.changes.length > 0 ? changesCard : null },
  ]
  const main = cards.filter((card) => card.live && card.side === 'main').map((card) => ({ key: card.key, folded: false, node: card.node }))
  const aside = cards.filter((card) => card.live && card.side === 'aside').map((card) => ({ key: card.key, folded: false, node: card.node }))
  const folded = cards.filter((card) => !card.live && card.node)

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Сегодня')}
        subtitle={`${data.today_words} · ${
          data.now_slot ? t('идёт {slot} урок до {time}', { slot: data.now_slot, time: data.now_ends?.slice(0, 5) ?? '' }) : t('уроки закончились')
        }`}
        actions={
          <>
            <Button variant="outline" onClick={() => navigate('/schedule')}>
              {t('Расписание')}
            </Button>
            {now ? (
              <>
                <Button variant="outline" onClick={() => navigate('/journals')}>
                  {t('Журналы')}
                </Button>
                <Button onClick={() => navigate(`/lessons/${now.id}`)}>
                  {now.marked ? t('Открыть {slot} урок', { slot: now.slot }) : t('Отметить {slot} урок', { slot: now.slot })}
                </Button>
              </>
            ) : (
              <Button onClick={() => navigate('/journals')}>{t('Журналы')}</Button>
            )}
          </>
        }
      />
      {/* задачи от академического директора (24.10.2026): исполнитель отмечает «Выполнено» */}
      <MyStaffTasksCard />
      <div className="lay-4">
        {/* урок без звонков своей группы приходит с пустым `bell`: подпись «с — по»
            только когда время есть у обоих крайних уроков (D88) */}
        <Kpi
          label={t('Уроков сегодня')}
          value={live.length || null}
          none={t('нет')}
          note={first && last ? (first.bell && last.bell ? `${first.bell.split('–')[0]}–${last.bell.split('–')[1]}` : t('время не назначено')) : ''}
        />
        <Kpi
          label={t('Не отмечено')}
          value={data.unmarked.length || null}
          none={t('всё отмечено')}
          tone={data.unmarked.length ? 'warn' : undefined}
          // чип — одной строкой: первый урок и «и ещё N», список целиком — в карточках ниже
          note={
            data.unmarked.length
              ? [t('{date} {slot} ур.', { date: dateShort(data.unmarked[0].date), slot: data.unmarked[0].slot }), data.unmarked.length > 1 ? t('и ещё {n}', { n: data.unmarked.length - 1 }) : '']
                  .filter(Boolean)
                  .join(' ')
              : t('за неделю')
          }
          action={data.unmarked.length ? { label: t('Отметить'), to: `/lessons/${data.unmarked[0].id}` } : undefined}
        />
        <Kpi label={t('Оценок за неделю')} value={data.week_grades || null} none={t('не ставили')} note={counted(data.journals.length, 'журнал|журнала|журналов')} />
        <Kpi
          label={t('Ближайшие СОР и СОЧ')}
          value={data.assessments.length || null}
          none={t('нет')}
          note={data.assessments.length ? t('первый {date}', { date: dateShort(data.assessments[0].date) }) : t('в ближайший месяц')}
        />
      </div>
      {/* две колонки, когда есть что ставить в обе; одна сторона пустая — карточки
          столбиком во всю ширину, без пустой полосы рядом; пустые — строкой ниже */}
      {main.length > 0 && aside.length > 0 ? (
        <div className="tday__cols">
          <Columns main={main} aside={aside} />
        </div>
      ) : (
        [...main, ...aside].map((card) => <Fragment key={card.key}>{card.node}</Fragment>)
      )}
      {/* журналы — во всю ширину под колонками: строка журнала широкая (полоса
          «проведено» и чип), а колонки над ней кончаются вровень */}
      {journalsCard}
      {folded.map((card) => (
        <Fragment key={card.key}>{card.node}</Fragment>
      ))}
    </div>
  )
}
