/**
 * «Сегодня» учителя: уроки по звонкам, что не отмечено, оценки за неделю,
 * журналы, ближайшие СОР и СОЧ, изменения в расписании.
 *
 * Образец — `route(['teacher'], '/dashboard')` референса. Главный сценарий
 * на телефоне: открыть текущий урок и отметить отсутствующих — кнопка
 * «Отметить N урок» стоит первой.
 */
import { useNavigate } from 'react-router'
import { useTeacherToday } from '../../api/academics'
import { Row, Rows, ShowAll, StatRow } from '../../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tn } from '../../i18n'
import { absentWords, dateShort, dateWords, OpenLesson } from './shared'

export default function TeacherToday() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useTeacherToday()
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  if (!data.has_courses)
    return (
      <div>
        <ScreenHead title={t('Сегодня')} subtitle={data.today_words} />
        <div className="acad__cols">
          <div className="acad__stack">
            <DataCard title={t('Уроков пока нет')} empty={t('Кымбат или администратор ещё не поставили вас в расписание')} />
            <DataCard title={t('Журналы')} empty={t('появятся сами, когда у вас будут уроки')} />
          </div>
          <div className="acad__stack">
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

  return (
    <div>
      <ScreenHead
        title={t('Сегодня')}
        subtitle={`${data.today_words} · ${
          data.now_slot ? t('идёт {slot} урок до {time}', { slot: data.now_slot, time: data.now_ends?.slice(0, 5) ?? '' }) : t('уроки закончились')
        }`}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate('/schedule')}>
              {t('Расписание')}
            </Button>
            {now ? (
              <Button size="sm" onClick={() => navigate(`/lessons/${now.id}`)}>
                {now.marked ? t('Открыть {slot} урок', { slot: now.slot }) : t('Отметить {slot} урок', { slot: now.slot })}
              </Button>
            ) : (
              <Button size="sm" onClick={() => navigate('/journals')}>
                {t('Журналы')}
              </Button>
            )}
          </>
        }
      />
      <StatRow>
        <Kpi label={t('Уроков сегодня')} value={live.length || null} none={t('нет')} note={first && last ? `${first.bell.split('–')[0]}–${last.bell.split('–')[1]}` : ''} />
        <Kpi
          label={t('Не отмечено')}
          value={data.unmarked.length || null}
          none={t('всё отмечено')}
          tone={data.unmarked.length ? 'warn' : undefined}
          note={data.unmarked.length ? data.unmarked.map((lesson) => t('{date} {slot} ур.', { date: dateShort(lesson.date), slot: lesson.slot })).join(', ') : t('за неделю')}
          action={data.unmarked.length ? { label: t('Отметить'), to: `/lessons/${data.unmarked[0].id}` } : undefined}
        />
        <Kpi label={t('Оценок за неделю')} value={data.week_grades || null} none={t('не ставили')} note={counted(data.journals.length, 'журнал|журнала|журналов')} />
        <Kpi
          label={t('Ближайшие СОР и СОЧ')}
          value={data.assessments.length || null}
          none={t('нет')}
          note={data.assessments.length ? t('первый {date}', { date: dateShort(data.assessments[0].date) }) : t('в ближайший месяц')}
        />
      </StatRow>

      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard
            title={t('Уроки сегодня')}
            count={data.lessons.length || undefined}
            empty={data.lessons.length === 0 && t('сегодня у вас уроков нет')}
            right={
              <Button variant="link" size="sm" onClick={() => navigate('/schedule')}>
                {t('Вся неделя')}
              </Button>
            }
          >
            <div className="acad__timeline">
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
                  <div key={lesson.id} className={`acad__tl${lesson.state === 'now' && lesson.is_live ? ' acad__tl--now' : ''}${lesson.state === 'past' ? ' acad__tl--past' : ''}`}>
                    <div className="acad__tltime">
                      <b className="num">{lesson.bell.split('–')[0]}</b>
                      <span>{t('{slot} урок', { slot: lesson.slot })}</span>
                    </div>
                    <div>
                      <div className="acad__tltitle">
                        {lesson.title}
                        {lesson.kind !== 'fo' && (
                          <>
                            {' '}
                            <Chip tone={lesson.kind === 'soch' ? 'accent' : 'info'} size="sm">
                              {lesson.kind_label}
                            </Chip>
                          </>
                        )}
                      </div>
                      <div className="acad__tlnote">
                        {[
                          lesson.room,
                          counted(lesson.cohort.students, 'ученик|ученика|учеников'),
                          lesson.absent.length ? absentWords(lesson.absent) : '',
                          lesson.is_substitution && lesson.teacher ? t('замена за {teacher}', { teacher: lesson.teacher.short }) : '',
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </div>
                    </div>
                    <div className="acad__tlacts">
                      {chip}
                      {lesson.is_live && (
                        <OpenLesson lesson={lesson} label={lesson.state !== 'future' && !lesson.marked ? t('Отметить') : t('Открыть')} primary={lesson.state !== 'future' && !lesson.marked} />
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </DataCard>

          {unmarkedEarlier.length > 0 && (
            <DataCard title={t('Не отмечено раньше')} count={unmarkedEarlier.length}>
              <Rows>
                {unmarkedEarlier.map((lesson) => (
                  <Row
                    key={lesson.id}
                    icon="alert"
                    tone="warn"
                    title={lesson.title}
                    note={`${lesson.weekday}, ${dateWords(lesson.date)}, ${t('{slot} урок', { slot: lesson.slot })} · ${t('куратор видит этот урок как неотмеченный')}`}
                    acts={<OpenLesson lesson={lesson} label={t('Отметить')} primary />}
                  />
                ))}
              </Rows>
            </DataCard>
          )}

          <DataCard
            title={t('Мои журналы')}
            count={data.journals.length}
            right={
              <Button variant="link" size="sm" onClick={() => navigate('/journals')}>
                {t('Все')}
              </Button>
            }
          >
            <Rows>
              <ShowAll>
                {data.journals.map((course) => (
                  <Row
                    key={course.id}
                    icon="book"
                    tone="accent"
                    title={course.title}
                    note={`${counted(course.students, 'ученик|ученика|учеников')} · ${course.cohort.kind_title} · ${t('проведено {held} из {planned}', { held: course.held, planned: course.planned })}`}
                    right={course.unmarked ? <Chip tone="warn">{tn(course.unmarked, 'не отмечен {n} урок|не отмечено {n} урока|не отмечено {n} уроков')}</Chip> : undefined}
                    to={`/journals/${course.id}`}
                  />
                ))}
              </ShowAll>
            </Rows>
          </DataCard>
        </div>

        <div className="acad__stack">
          <DataCard
            title={t('Ближайшие СОР и СОЧ')}
            count={data.assessments.length || undefined}
            empty={data.assessments.length === 0 && t('в ближайший месяц нет')}
            emptyAction={
              data.assessments.length === 0 ? (
                <Button variant="secondary" size="sm" onClick={() => navigate('/journals')}>
                  {t('Запланировать')}
                </Button>
              ) : undefined
            }
          >
            <Rows>
              {data.assessments.map((lesson) => (
                <Row
                  key={lesson.id}
                  lead={<b className="num">{Number(lesson.date.slice(8))}</b>}
                  title={`${lesson.kind_label} · ${lesson.subject.short_title}`}
                  note={`${lesson.cohort.name} · ${lesson.weekday}, ${dateWords(lesson.date)}, ${t('{slot} урок', { slot: lesson.slot })} · ${t('из {max}', { max: lesson.max_score ?? '' })}`}
                  to={`/lessons/${lesson.id}`}
                />
              ))}
            </Rows>
          </DataCard>

          <DataCard title={t('Изменения в расписании')} count={data.changes.length || undefined} empty={data.changes.length === 0 && t('на две недели всё по плану')}>
            <Rows>
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
            </Rows>
          </DataCard>

        </div>
      </div>
    </div>
  )
}
