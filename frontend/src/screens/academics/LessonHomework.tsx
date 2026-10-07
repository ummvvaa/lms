/**
 * «Тема и домашнее задание» на экране урока у учителя.
 *
 * Текст ДЗ — как раньше, в уроке (`Lesson.homework`). Сверху — сдача в LMS
 * (решение владельца, 30.09.2026): файлы учителя к заданию, «Нужна сдача
 * в LMS», срок и что делать после срока. Одна кнопка «Сохранить» пишет
 * и тему с текстом, и задание со сдачей. Правит сдачу тот, кому сервер
 * разрешил (`may_edit`); остальные видят её на чтение.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useLessonMeta, type AcadLesson } from '../../api/academics'
import { uploadHomeworkFile, useDropHomeworkFile, useLessonHomework, useSaveLessonHomework, type LatePolicy, type LessonHomework } from '../../api/homework'
import Field from '../../components/Field'
import { Row, Rows, Segmented } from '../../components/patterns'
import { DataCard } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Switch } from '../../components/ui/switch'
import { t, tn } from '../../i18n'
import { dayInSchoolZone, timeInSchoolZone, todayAlmaty } from '../../lib/dates'
import { dueWords, FileLine, downloadHomeworkFile, sizeWords } from './homeworkParts'

type Due = 'next' | 'evening' | 'custom'

/** Какой из вариантов срока сейчас сохранён. */
function dueOf(data: LessonHomework): Due {
  if (!data.due_at) return data.options.next_lesson ? 'next' : 'evening'
  const at = new Date(data.due_at).getTime()
  if (data.options.next_lesson && new Date(data.options.next_lesson).getTime() === at) return 'next'
  if (new Date(data.options.evening).getTime() === at) return 'evening'
  return 'custom'
}

/** «Сегодня, 20:00» или «В день урока, 20:00» — вариант вечера. */
function eveningWords(iso: string): string {
  const at = new Date(iso)
  const day = dayInSchoolZone(at)
  return `${day === todayAlmaty() ? t('Сегодня') : t('В день урока')}, ${timeInSchoolZone(at)}`
}

/** «Все ученики 9 MANCHESTER — 24 чел.» или «Только ученики EEP-9-2 — 12 чел.» */
function recipientsWords(data: LessonHomework): string {
  const { cohort, count } = data.recipients
  return data.recipients.kind === 'group' ? t('Все ученики {cohort} — {count} чел.', { cohort, count }) : t('Только ученики {cohort} — {count} чел.', { cohort, count })
}

/** Файлы учителя к заданию: прикрепить, убрать, скачать. */
function TeacherFiles({ lesson, data }: { lesson: number; data: LessonHomework }) {
  const client = useQueryClient()
  const drop = useDropHomeworkFile()
  const picker = useRef<HTMLInputElement>(null)
  const [progress, setProgress] = useState<{ name: string; share: number } | null>(null)
  const limit = (file: File) => (file.type.startsWith('video/') ? data.limits.video_mb : data.limits.file_mb) * 1024 * 1024

  const upload = async (files: File[]) => {
    let room = data.limits.max_files - data.files.length
    for (const file of files) {
      if (room <= 0) {
        toast.error(tn(data.limits.max_files, 'Не больше {n} файла к заданию|Не больше {n} файлов к заданию|Не больше {n} файлов к заданию'))
        break
      }
      if (file.size > limit(file)) {
        toast.error(`${t('Файл больше допустимого')} (${sizeWords(limit(file))}): ${file.name}`)
        continue
      }
      try {
        setProgress({ name: file.name, share: 0 })
        await uploadHomeworkFile({ lesson }, file, { onProgress: (share) => setProgress({ name: file.name, share }) })
        room -= 1
      } catch (error) {
        toast.error(error instanceof Error ? error.message : t('Файл не загрузился — попробуйте ещё раз'))
      }
    }
    setProgress(null)
    await client.invalidateQueries({ queryKey: ['homework', 'lesson', lesson] })
  }

  return (
    <div className="hwset__files">
      {data.files.map((file) => (
        <FileLine key={file.id} file={file}>
          <Button variant="link" size="sm" onClick={() => void downloadHomeworkFile(file.id)}>
            {t('Скачать')}
          </Button>
          {data.may_edit && (
            <Button variant="ghost" size="sm" disabled={drop.isPending} onClick={() => drop.mutate(file.id, { onError: (e) => toast.error(e.message) })}>
              {t('Убрать')}
            </Button>
          )}
        </FileLine>
      ))}
      {progress && <span className="t-note">{`${t('Загружается {name}', { name: progress.name })} · ${Math.round(progress.share * 100)} %`}</span>}
      {data.may_edit && (
        <div>
          <Input
            ref={picker}
            type="file"
            multiple
            className="acad__hidden"
            onChange={(event) => {
              const files = Array.from(event.target.files ?? [])
              event.target.value = ''
              if (files.length) void upload(files)
            }}
          />
          <Button variant="outline" size="sm" disabled={progress !== null} onClick={() => picker.current?.click()}>
            {`+ ${t('Прикрепить файл')}`}
          </Button>
        </div>
      )}
    </div>
  )
}

export default function LessonHomeworkCards({
  lesson,
  mayWrite,
  lms,
  children,
}: {
  lesson: AcadLesson
  /** правит тему и текст ДЗ: учитель урока, Кымбат, администратор */
  mayWrite: boolean
  /** спрашивать ли сдачу в LMS: у куратора её нет */
  lms: boolean
  /** раскладка экрана: куда встают «Тема и ДЗ» и «Кто получит» */
  children?: (topic: ReactNode, recipients: ReactNode) => ReactNode
}) {
  const saveMeta = useLessonMeta()
  const saveHomework = useSaveLessonHomework()
  const homework = useLessonHomework(lms ? lesson.id : null)
  const data = homework.data
  const [topic, setTopic] = useState(lesson.topic)
  const [text, setText] = useState(lesson.homework)
  const [requires, setRequires] = useState(false)
  const [due, setDue] = useState<Due>('next')
  const [day, setDay] = useState('')
  const [time, setTime] = useState('20:00')
  const [policy, setPolicy] = useState<LatePolicy>('accept')
  const [error, setError] = useState('')

  // сохранённое на сервере перезаписывает поля только когда оно само поменялось:
  // загрузка файла перечитывает урок, а недописанный текст должен остаться
  useEffect(() => setTopic(lesson.topic), [lesson.topic])
  useEffect(() => setText(lesson.homework), [lesson.homework])
  const saved = data ? `${data.lesson}|${data.requires_submission}|${data.due_at}|${data.late_policy}` : ''
  useEffect(() => {
    if (!data) return
    setRequires(data.requires_submission)
    setDue(dueOf(data))
    const at = data.due_at ? new Date(data.due_at) : new Date(data.options.evening)
    setDay(dayInSchoolZone(at))
    setTime(timeInSchoolZone(at))
    setPolicy(data.late_policy)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saved])

  const editable = Boolean(data?.may_edit)
  const fail = (e: Error) => toast.error(e.message)
  const dueAt = (): string | null => {
    if (!data || !requires) return null
    if (due === 'next') return data.options.next_lesson
    if (due === 'evening') return data.options.evening
    // своя дата — время школы: сервер читает её по Алматы
    return `${day}T${time}`
  }
  const save = () => {
    setError('')
    if (editable && requires && !text.trim()) {
      setError(t('Напишите, что задано: ученики увидят это в разделе «Домашние задания»'))
      return
    }
    if (editable && requires && due === 'custom' && (!day || !time)) {
      setError(t('Укажите дату и время срока'))
      return
    }
    saveMeta.mutate(
      { lesson: lesson.id, topic, homework: text },
      {
        onSuccess: () => {
          if (data && editable && (data.assignment !== null || requires)) {
            saveHomework.mutate({ lesson: lesson.id, requires_submission: requires, due_at: dueAt(), late_policy: policy }, { onError: fail })
          } else toast.success(t('Тема и задание сохранены'))
        },
        onError: fail,
      },
    )
  }

  const policies: { value: LatePolicy; label: string }[] = [
    { value: 'accept', label: t('Принимать с пометкой «с опозданием»') },
    { value: 'close', label: t('Закрыть сдачу') },
  ]
  const dueItems: { value: Due; label: string }[] = data
    ? [
        ...(data.options.next_lesson ? [{ value: 'next' as Due, label: `${t('До следующего урока')} · ${dueWords(data.options.next_lesson)}` }] : []),
        { value: 'evening', label: eveningWords(data.options.evening) },
        { value: 'custom', label: t('Своя дата…') },
      ]
    : []

  const topicCard = (
    <DataCard title={t('Тема и домашнее задание')}>
      <Field kind="text" name="topic" label={t('Тема')} value={topic} onChange={setTopic} placeholder={t('О чём урок')} disabled={!mayWrite} />
      <Field
        kind="textarea"
        name="homework"
        label={t('Домашнее задание')}
        value={text}
        onChange={setText}
        rows={3}
        placeholder={t('Ученики увидят в расписании и в уроке')}
        disabled={!mayWrite}
      />
      {data && (data.files.length > 0 || editable) && <TeacherFiles lesson={lesson.id} data={data} />}
      {data && editable && (
        <div className="hwset">
          <label className="hwset__toggle">
            <Switch checked={requires} onCheckedChange={setRequires} aria-label={t('Нужна сдача в LMS')} />
            <span>
              <b>{t('Нужна сдача в LMS')}</b>
              <span className="t-note">{t('Ученики загрузят работу в разделе «Домашние задания». Если выключено — ДЗ просто видно в уроке, как сейчас.')}</span>
            </span>
          </label>
          {requires && (
            <>
              <div className="hwset__opts">
                <span className="t-caps">{t('Срок сдачи')}</span>
                <Segmented usageFilter={false} value={due} onChange={setDue} label={t('Срок сдачи')} items={dueItems} />
                {due === 'custom' && (
                  <Field.Row>
                    <Field kind="date" name="due-day" label={t('День')} value={day} onChange={setDay} min={lesson.date} />
                    <Field kind="time" name="due-time" label={t('Время')} value={time} onChange={setTime} />
                  </Field.Row>
                )}
              </div>
              <div className="hwset__opts">
                <span className="t-caps">{t('После срока')}</span>
                <Segmented usageFilter={false} value={policy} onChange={setPolicy} label={t('После срока')} items={policies} />
              </div>
            </>
          )}
        </div>
      )}
      {data && !editable && data.requires_submission && (
        <Rows>
          <Row title={t('Сдача в LMS')} value={dueWords(data.due_at)} none={t('без срока')} note={data.late_policy === 'close' ? t('после срока сдача закрыта') : t('после срока — с пометкой «с опозданием»')} />
        </Rows>
      )}
      {error && (
        <span className="field__error t-note" role="alert">
          {error}
        </span>
      )}
      {mayWrite && (
        <div className="acad__actions">
          <Button variant="secondary" size="sm" onClick={save} disabled={saveMeta.isPending || saveHomework.isPending}>
            {t('Сохранить')}
          </Button>
        </div>
      )}
    </DataCard>
  )
  const recipientsCard = data && (requires || data.requires_submission) && (
    <DataCard title={t('Кто получит')}>
      <p className="acad__note">{recipientsWords(data)}</p>
      <p className="t-note">
        {data.recipients.kind === 'group'
          ? t('Если урок на подгруппу, задание получат только ученики этой подгруппы.')
          : data.recipients.kind === 'stream'
            ? t('Урок потока: задание получат ученики потока из всех его групп.')
            : t('Урок подгруппы: задание получат только её ученики.')}
      </p>
      <span className="t-caps">{t('Оценка')}</span>
      <p className="acad__note">
        {t('Ставить оценку или нет — решаете при проверке каждой работы. Оценки за ДЗ идут в журнал отдельной колонкой «ДЗ» рядом с уроком и по умолчанию не входят в четвертную (это меняет администратор в «Настройках школы»).')}
      </p>
      {data.assignment !== null && data.requires_submission && (
        <Rows>
          <Row icon="homework" tone="accent" title={t('Проверка ДЗ')} note={t('работы учеников по этому уроку')} to={`/homework-review/${data.assignment}`} />
        </Rows>
      )}
    </DataCard>
  )
  if (children) return <>{children(topicCard, recipientsCard || null)}</>
  return (
    <>
      {topicCard}
      {recipientsCard}
    </>
  )
}
