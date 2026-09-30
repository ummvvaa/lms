/**
 * Домашнее задание урока глазами ученика — в уроке и в расписании.
 *
 * Текст ДЗ живёт у урока (`lesson.homework`): учитель пишет его в уроке
 * с подсказкой «Ученики увидят в расписании», и здесь ученик его видит.
 * Если по уроку нужна сдача в LMS, задание находится в списке «Домашние
 * задания» (`/homework/my/` отдаёт урок каждого задания) — ссылка ведёт
 * прямо в него; новых запросов к серверу не нужно.
 */
import { useNavigate } from 'react-router-dom'
import type { AcadLesson } from '../../api/academics'
import { useMyHomework, type MyHomework } from '../../api/homework'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Chip, DataCard } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { dateWords } from '../academics/shared'
import './myWork.css'

/** Кнопка задания со сдачей: «Сдать в LMS», пока к сдаче, иначе — посмотреть работу. */
function HandIn({ item }: { item: MyHomework }) {
  const navigate = useNavigate()
  return (
    <Button variant="secondary" size="sm" onClick={() => navigate(`/homework/${item.id}`)}>
      {item.state === 'todo' ? t('Сдать в LMS') : t('Моя работа')}
    </Button>
  )
}

/** Строка «Домашнее задание» в карточке урока ученика. */
export function LessonHomeworkRow({ lesson, text }: { lesson: number; text: string }) {
  const mine = useMyHomework()
  const item = mine.data?.items.find((row) => row.lesson.id === lesson)
  if (!text && !item) return <Row title={t('Домашнее задание')} value={null} none={t('не задано')} />
  return (
    <Row
      title={t('Домашнее задание')}
      note={<span className="mywork__wrap">{text || t('Задание — в прикреплённых файлах')}</span>}
      acts={item ? <HandIn item={item} /> : undefined}
    />
  )
}

/** «ДЗ на неделю» в расписании ученика: уроки недели с заданием, сдача — ссылкой. */
export function WeekHomework({ lessons }: { lessons: AcadLesson[] }) {
  const navigate = useNavigate()
  const mine = useMyHomework()
  const byLesson = new Map((mine.data?.items ?? []).map((item) => [item.lesson.id, item]))
  const rows = lessons
    .filter((lesson) => lesson.is_live && (lesson.homework.trim() !== '' || byLesson.has(lesson.id)))
    .sort((a, b) => a.date.localeCompare(b.date) || a.slot - b.slot)
  const todo = (mine.data?.counts.todo ?? 0) > 0
  return (
    <DataCard
      title={t('Домашние задания недели')}
      count={rows.length || undefined}
      empty={rows.length === 0 && t('на этой неделе не задано')}
      emptyAction={
        todo ? (
          <Button variant="link" size="sm" onClick={() => navigate('/homework')}>
            {t('К сдаче в LMS')}
          </Button>
        ) : undefined
      }
    >
      <Rows>
        <ShowAll>
          {rows.map((lesson) => {
            const item = byLesson.get(lesson.id)
            return (
              <Row
                key={lesson.id}
                icon="homework"
                tone={item ? 'accent' : 'neutral'}
                title={`${lesson.subject.title} · ${lesson.weekday}, ${dateWords(lesson.date)}`}
                note={
                  <span className="mywork__wrap">{`${t('ДЗ:')} ${lesson.homework || t('задание — в прикреплённых файлах')}`}</span>
                }
                right={
                  item && item.state !== 'todo' ? (
                    <Chip
                      size="sm"
                      tone={item.state === 'checked' ? 'good' : item.state === 'missed' ? 'bad' : 'accent'}
                    >
                      {item.state === 'checked'
                        ? t('проверено')
                        : item.state === 'missed'
                          ? t('не сдано')
                          : t('сдано')}
                    </Chip>
                  ) : undefined
                }
                acts={item?.state === 'todo' ? <HandIn item={item} /> : undefined}
                to={item ? `/homework/${item.id}` : `/lessons/${lesson.id}`}
              />
            )
          })}
        </ShowAll>
      </Rows>
    </DataCard>
  )
}
