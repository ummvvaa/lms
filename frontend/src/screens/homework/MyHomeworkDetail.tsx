/**
 * Задание ученика: сдать, заменить до срока, посмотреть сданное и итог
 * проверки (образец `docs/ui/dz-sdacha.html`, экраны «Сдача» и «Сдано»).
 *
 * Работа собирается из файлов, текста и ссылки. Файл уходит с устройства
 * прямо в хранилище (`uploadHomeworkFile`); несколько фото тетради перед
 * этим склеиваются в один PDF на устройстве. «Сдать работу» только
 * фиксирует собранное: сервер отвечает, можно ли сейчас что-то менять
 * (`may_change`), а если нельзя — словами почему (`change_note`).
 */
import { useRef, useState, type DragEvent, type ReactNode } from 'react'
import { Navigate, useParams } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  uploadHomeworkFile,
  useDropHomeworkFile,
  useMyHomeworkDetail,
  useSubmitHomework,
  type MyHomeworkDetail,
} from '../../api/homework'
import { useAuth } from '../../auth/AuthContext'
import Field from '../../components/Field'
import Progress from '../../components/Progress'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import Icon, { type IconName } from '../../layout/icons'
import { t, tn } from '../../i18n'
import { usePhone } from '../../phone'
import { dateWords } from '../academics/shared'
import {
  audioSupported,
  clockWords,
  dueShort,
  dueWords,
  FileRow,
  limitsWords,
  minutesPast,
  photosToPdf,
  PhotoError,
  type PhotoPdf,
  refuseFile,
  sizeWords,
  spanWords,
  useRecorder,
  whenWords,
} from './myWork'
import '../academics/academics.css'
import './myWork.css'

/** Файл в пути: склейка фото, загрузка, отказ. */
interface Pending {
  key: string
  name: string
  size: number
  share: number
  stage: 'pdf' | 'upload' | 'failed'
  error?: string
}

let pendingKey = 0

function Banner({
  tone,
  icon,
  children,
}: {
  tone: 'good' | 'warn' | 'bad'
  icon: IconName
  children: ReactNode
}) {
  return (
    <div className={`mywork__banner mywork__banner--${tone}`} role="status">
      <Icon name={icon} size={16} />
      <span>{children}</span>
    </div>
  )
}

/** «Моя работа»: способы приложить, файлы с ходом загрузки, текст, ссылка, комментарий и «Сдать». */
function WorkForm({
  data,
  onDone,
  onCancel,
}: {
  data: MyHomeworkDetail
  onDone: () => void
  onCancel?: () => void
}) {
  const client = useQueryClient()
  const phone = usePhone()
  const submit = useSubmitHomework()
  const drop = useDropHomeworkFile()
  const submission = data.submission
  const [text, setText] = useState(submission?.text ?? '')
  const [link, setLink] = useState(submission?.link ?? '')
  const [comment, setComment] = useState(submission?.comment ?? '')
  const [showText, setShowText] = useState(Boolean(submission?.text))
  const [showLink, setShowLink] = useState(Boolean(submission?.link))
  const [pending, setPending] = useState<Pending[]>([])
  const [over, setOver] = useState(false)
  const camera = useRef<HTMLInputElement>(null)
  const picker = useRef<HTMLInputElement>(null)
  const video = useRef<HTMLInputElement>(null)
  const recorder = useRecorder((file) => void addFiles([file]))
  const files = submission?.files ?? []
  const busy = pending.some((row) => row.stage !== 'failed')
  const limits = data.limits
  const late = data.past_due

  const patch = (key: string, next: Partial<Pending>) =>
    setPending((rows) => rows.map((row) => (row.key === key ? { ...row, ...next } : row)))
  const refresh = () => client.invalidateQueries({ queryKey: ['homework', 'my'] })

  /** Сколько ещё файлов можно приложить — пределом школы. */
  const room = () => limits.max_files - files.length - pending.filter((row) => row.stage !== 'failed').length

  async function upload(key: string, blob: Blob, name: string, photos?: number) {
    let started: number | null = null
    patch(key, { stage: 'upload', share: 0, size: blob.size })
    try {
      await uploadHomeworkFile({ assignment: data.id }, blob, {
        name,
        photos,
        onStart: (file) => {
          started = file
        },
        onProgress: (share) => patch(key, { share }),
      })
      setPending((rows) => rows.filter((row) => row.key !== key))
      await refresh()
    } catch (error) {
      // сорвавшаяся загрузка оставляет на сервере строку «загружается» — она держала бы сдачу
      if (started !== null) drop.mutate(started)
      patch(key, {
        stage: 'failed',
        error: error instanceof Error ? error.message : t('Файл не загрузился — попробуйте ещё раз'),
      })
    }
  }

  async function addFiles(list: File[]) {
    if (list.length === 0) return
    if (list.length > room()) {
      toast.error(`${tn(Math.max(0, room()), 'Можно приложить ещё {n} файл|Можно приложить ещё {n} файла|Можно приложить ещё {n} файлов')} · ${limitsWords(limits)}`)
      return
    }
    const refused = list.map((file) => refuseFile(file, limits)).filter(Boolean)
    if (refused.length) {
      toast.error(refused.join('. '))
      return
    }
    const rows = list.map((file) => ({
      key: `p${++pendingKey}`,
      name: file.name,
      size: file.size,
      share: 0,
      stage: 'upload' as const,
    }))
    setPending((current) => [...current, ...rows])
    for (const [index, file] of list.entries()) await upload(rows[index].key, file, file.name)
  }

  async function addPhotos(list: File[]) {
    if (list.length === 0) return
    if (room() < 1) {
      toast.error(`${t('Можно приложить ещё')} 0 · ${limitsWords(limits)}`)
      return
    }
    const name = `${data.lesson.subject.replace(/[\s/\\]+/g, '_')}_${t('фото')}.pdf`
    const key = `p${++pendingKey}`
    setPending((current) => [...current, { key, name, size: 0, share: 0, stage: 'pdf' }])
    let made: PhotoPdf
    try {
      made = await photosToPdf(list)
    } catch (error) {
      patch(key, {
        stage: 'failed',
        error: error instanceof PhotoError ? error.message : t('Фото не склеились — приложите их файлами'),
      })
      return
    }
    if (made.unreadable.length) toast.info(t('Часть фото браузер не читает (например, HEIC) — они приложены отдельными файлами'))
    if (made.pdf) {
      const refused = refuseFile(Object.assign(made.pdf, { name }), limits)
      if (refused) {
        patch(key, { stage: 'failed', error: `${refused}. ${t('Снимите меньше страниц за раз')}` })
        return
      }
      await upload(key, made.pdf, name, made.pages)
    } else setPending((rows) => rows.filter((row) => row.key !== key))
    if (made.unreadable.length) await addFiles(made.unreadable)
  }

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setOver(false)
    void addFiles(Array.from(event.dataTransfer.files))
  }

  const hasWork = files.length > 0 || text.trim() !== '' || link.trim() !== ''
  const send = () =>
    submit.mutate(
      { id: data.id, text, link, comment },
      {
        onSuccess: () => {
          toast.success(late ? t('Работа сдана с опозданием') : t('Работа сдана'))
          onDone()
        },
        onError: (error) => toast.error(error.message),
      },
    )

  const ways: { icon: IconName; label: string; onClick: () => void; hidden?: boolean; on?: boolean }[] = [
    { icon: 'camera', label: t('Сфотографировать'), onClick: () => camera.current?.click() },
    { icon: 'doc', label: t('Файл'), onClick: () => picker.current?.click() },
    {
      icon: 'mic',
      label: t('Записать аудио'),
      onClick: () => void recorder.start(),
      hidden: !audioSupported(),
    },
    { icon: 'video', label: t('Видео'), onClick: () => video.current?.click() },
    { icon: 'link', label: t('Ссылка'), onClick: () => setShowLink(!showLink), on: showLink },
    { icon: 'pencil', label: t('Текст ответа'), onClick: () => setShowText(!showText), on: showText },
  ]

  return (
    <DataCard title={t('Моя работа')}>
      <div className="mywork__ways">
        {ways
          .filter((way) => !way.hidden)
          .map((way) => (
            <Button
              key={way.label}
              variant="outline"
              className="mywork__way"
              aria-pressed={way.on}
              disabled={recorder.recording}
              onClick={way.onClick}
            >
              <Icon name={way.icon} size={20} />
              {way.label}
            </Button>
          ))}
      </div>
      <Input
        ref={camera}
        type="file"
        accept={ACCEPT_PHOTO}
        capture="environment"
        multiple
        className="acad__hidden"
        aria-label={t('Сфотографировать')}
        onChange={(event) => {
          const list = Array.from(event.target.files ?? [])
          event.target.value = ''
          void addPhotos(list)
        }}
      />
      <Input
        ref={picker}
        type="file"
        multiple
        className="acad__hidden"
        aria-label={t('Файл')}
        onChange={(event) => {
          const list = Array.from(event.target.files ?? [])
          event.target.value = ''
          void addFiles(list)
        }}
      />
      <Input
        ref={video}
        type="file"
        accept={ACCEPT_VIDEO}
        capture="environment"
        className="acad__hidden"
        aria-label={t('Видео')}
        onChange={(event) => {
          const list = Array.from(event.target.files ?? [])
          event.target.value = ''
          void addFiles(list)
        }}
      />
      {recorder.recording && (
        <div className="mywork__rec" role="status">
          <span className="mywork__recdot" aria-hidden="true" />
          <span className="num">{clockWords(recorder.seconds)}</span>
          <span className="t-note">{t('идёт запись')}</span>
          <span className="mywork__spacer" />
          <Button size="sm" onClick={() => recorder.stop(true)}>
            {t('Остановить')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => recorder.stop(false)}>
            {t('Отменить')}
          </Button>
        </div>
      )}
      {!phone && (
        <div
          className={`mywork__drop${over ? ' mywork__drop--over' : ''}`}
          onDragOver={(event) => {
            event.preventDefault()
            setOver(true)
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
        >
          <b>{t('Перетащите файлы сюда')}</b>
          <span className="t-note">{`${t('любые форматы: PDF, Word, Excel, PowerPoint, фото, аудио, видео, архивы')} · ${limitsWords(limits)}`}</span>
        </div>
      )}
      {phone && <p className="t-note mywork__hint">{limitsWords(limits)}</p>}
      {(files.length > 0 || pending.length > 0) && (
        <Rows>
          {files.map((file) => (
            <FileRow
              key={file.id}
              file={file}
              busy={drop.isPending}
              onDrop={() => drop.mutate(file.id, { onError: (error) => toast.error(error.message) })}
            />
          ))}
          {pending.map((row) => (
            <Row
              key={row.key}
              lead={
                <Chip size="sm">
                  {row.stage === 'pdf'
                    ? 'PDF'
                    : row.name.split('.').pop()?.toUpperCase().slice(0, 5) || t('файл')}
                </Chip>
              }
              title={<span className="mywork__name">{row.name}</span>}
              note={
                row.stage === 'failed' ? (
                  <span className="mywork__error">{row.error}</span>
                ) : row.stage === 'pdf' ? (
                  t('склеиваю фото в один PDF…')
                ) : (
                  <span className="mywork__progress">
                    <Progress percent={Math.round(row.share * 100)} />
                    <span className="num">{`${Math.round(row.share * 100)} % · ${sizeWords(row.size)}`}</span>
                  </span>
                )
              }
              acts={
                row.stage === 'failed' ? (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t('Убрать файл {name}', { name: row.name })}
                    onClick={() => setPending((rows) => rows.filter((item) => item.key !== row.key))}
                  >
                    <Icon name="close" size={15} />
                  </Button>
                ) : undefined
              }
            />
          ))}
        </Rows>
      )}
      {showLink && (
        <Field
          kind="text"
          name="link"
          label={t('Ссылка')}
          value={link}
          onChange={setLink}
          placeholder="https://"
          hint={t('Google Slides, Docs, Drive — откройте доступ по ссылке')}
        />
      )}
      {showText && (
        <Field
          kind="textarea"
          name="text"
          label={t('Текст ответа')}
          value={text}
          onChange={setText}
          rows={5}
        />
      )}
      <Field
        kind="textarea"
        name="comment"
        label={t('Комментарий учителю (необязательно)')}
        value={comment}
        onChange={setComment}
        rows={3}
        placeholder={t('Например: в № 217 не понял условие, решил по-своему')}
      />
      <div className="acad__actions mywork__actions">
        <Button onClick={send} disabled={submit.isPending || busy || recorder.recording || !hasWork}>
          {late ? t('Сдать с опозданием') : t('Сдать работу')}
        </Button>
        {onCancel && (
          <Button variant="outline" onClick={onCancel}>
            {t('Отмена')}
          </Button>
        )}
        <span className="t-note">
          {busy
            ? t('Дождитесь конца загрузки')
            : !hasWork
              ? t('Приложите файл, напишите ответ или дайте ссылку')
              : late
                ? t('Сдача будет помечена «с опозданием»')
                : t('До срока работу можно заменить.')}
        </span>
      </div>
    </DataCard>
  )
}

/** «Что сдано»: файлы, ответ, ссылка, комментарий учителю — и «Заменить работу», пока можно. */
function HandedCard({ data, onReplace }: { data: MyHomeworkDetail; onReplace: () => void }) {
  const submission = data.submission
  if (!submission) return null
  const replaceable = data.may_change && data.state === 'review'
  const empty = submission.files.length === 0 && !submission.text && !submission.link && !submission.comment
  return (
    <DataCard title={t('Что сдано')} empty={empty && t('в работе ничего нет')}>
      <Rows>
        {submission.files.map((file) => (
          <FileRow key={file.id} file={file} />
        ))}
        {submission.link && (
          <Row
            icon="link"
            tone="info"
            title={t('Ссылка')}
            note={<span className="mywork__name">{submission.link}</span>}
            acts={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => window.open(submission.link, '_blank', 'noopener')}
              >
                {t('Открыть')}
              </Button>
            }
          />
        )}
        {submission.text && (
          <Row
            icon="pencil"
            tone="neutral"
            title={t('Текст ответа')}
            note={<span className="mywork__wrap">{submission.text}</span>}
          />
        )}
        {submission.comment && (
          <Row icon="bulb" tone="neutral" title={t('Комментарий учителю')} note={`«${submission.comment}»`} />
        )}
      </Rows>
      {(replaceable || (data.state === 'review' && data.change_note)) && (
        <div className="acad__actions mywork__actions">
          {replaceable && (
            <Button variant="outline" onClick={onReplace}>
              {t('Заменить работу')}
            </Button>
          )}
          <span className="t-note">
            {replaceable
              ? data.due_at
                ? t('Можно до {time}. После срока — только просмотр.', { time: dueShort(data.due_at) })
                : t('Работу можно заменить, пока учитель её не проверил.')
              : data.change_note}
          </span>
        </div>
      )}
    </DataCard>
  )
}

/** Итог проверки: оценка или «без оценки» и слово учителя. */
function ResultCard({ data }: { data: MyHomeworkDetail }) {
  const submission = data.submission
  if (!submission?.checked_at) return null
  return (
    <DataCard
      title={t('Проверено')}
      right={<span className="t-note">{whenWords(submission.checked_at)}</span>}
    >
      <div className="mywork__result">
        <span className={`mywork__score num${submission.grade === null ? ' mywork__score--none' : ''}`}>
          {submission.grade ?? t('без оценки')}
        </span>
        <div className="mywork__task">
          <b>{submission.teacher_comment || t('Принято.')}</b>
          {!submission.teacher_comment && (
            <span className="t-note">
              {submission.grade === null
                ? t('Учитель проверил без оценки.')
                : t('Учитель проверил без комментария.')}
            </span>
          )}
        </div>
      </div>
    </DataCard>
  )
}

/** Задание учителя: текст, файлы, урок и состав. */
function TaskCard({ data }: { data: MyHomeworkDetail }) {
  const cohort = data.lesson.cohort
  return (
    <DataCard title={t('Задание')}>
      <div className="mywork__text">{data.text || t('Задание — в прикреплённых файлах')}</div>
      {data.files.length > 0 && (
        <Rows>
          {data.files.map((file) => (
            <FileRow key={file.id} file={file} />
          ))}
        </Rows>
      )}
      <p className="t-note mywork__hint">{`${t('Урок {date}', { date: dateWords(data.lesson.date) })} · ${cohort}`}</p>
    </DataCard>
  )
}

export default function MyHomeworkDetailScreen() {
  const { id } = useParams()
  const { me } = useAuth()
  const student = me?.role === 'student'
  const assignment = Number(id)
  const { data, isLoading, error } = useMyHomeworkDetail(
    student && Number.isFinite(assignment) ? assignment : null,
  )
  const [replacing, setReplacing] = useState(false)
  if (me && !student) return <Navigate to="/dashboard" replace />
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const now = new Date()
  const teacher = data.lesson.teacher?.short ?? ''
  const policy =
    data.late_policy === 'accept'
      ? t('после срока — с пометкой «с опозданием»')
      : t('после срока сдача закрыта')
  const due = data.due_at
    ? data.past_due
      ? `${t('срок был:')} ${whenWords(data.due_at)}`
      : `${t('срок:')} ${dueWords(data.due_at, now)}`
    : t('без срока')
  const subtitle = [teacher, due, data.state === 'todo' && !data.past_due ? policy : '']
    .filter(Boolean)
    .join(' · ')
  const submission = data.submission
  const editing = (data.state === 'todo' && data.may_change) || (replacing && data.may_change)

  let banner: { tone: 'good' | 'warn' | 'bad'; icon: IconName; text: string } | null = null
  if (editing && data.past_due) {
    banner = {
      tone: 'warn',
      icon: 'clock',
      text: t('Срок прошёл {span} назад. Учитель принимает работы после срока — сдача будет помечена «с опозданием».', { span: spanWords(minutesPast(data.due_at, now)) }),
    }
  } else if (data.state === 'missed') {
    banner = { tone: 'bad', icon: 'lock', text: t('Срок прошёл. Учитель не принимает работы после срока.') }
  } else if (data.state === 'review' && submission?.submitted_at && !editing) {
    const when = whenWords(submission.submitted_at)
    banner = {
      tone: 'good',
      icon: 'check',
      text: submission.late_minutes
        ? t('Сдано с опозданием на {span} {when}. Учитель проверит работу.', { span: spanWords(submission.late_minutes), when })
        : t('Сдано {when}. Учитель проверит работу.', { when }),
    }
  }

  return (
    <div>
      <ScreenHead
        title={data.lesson.subject}
        crumb={{ label: t('Домашние задания'), to: '/homework' }}
        subtitle={subtitle}
      />
      {banner && (
        <Banner tone={banner.tone} icon={banner.icon}>
          {banner.text}
        </Banner>
      )}
      <div className="acad__cols">
        {data.state !== 'missed' && (
          <div className="acad__stack">
            {editing ? (
              <WorkForm
                data={data}
                onDone={() => setReplacing(false)}
                onCancel={replacing ? () => setReplacing(false) : undefined}
              />
            ) : (
              <>
                <ResultCard data={data} />
                {submission?.submitted_at ? (
                  <HandedCard data={data} onReplace={() => setReplacing(true)} />
                ) : (
                  <DataCard title={t('Моя работа')} empty={data.change_note || t('работа не сдана')} />
                )}
              </>
            )}
          </div>
        )}
        <div className="acad__stack">
          <TaskCard data={data} />
        </div>
      </div>
    </div>
  )
}

// Типы для выбора файла — в самом конце файла намеренно: сочетание «слеш-звёздочка»
// в середине сбивало бы разбор комментариев у стража переводов (test_i18n)
const ACCEPT_PHOTO = 'image/*'
const ACCEPT_VIDEO = 'video/*'
