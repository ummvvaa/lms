/**
 * Проверка работ одного задания (30.09.2026).
 *
 * Слева ученики тремя группами — не проверено, проверено, не сдали; справа
 * выбранная работа: файлы с просмотром на месте (PDF постранично, фото,
 * аудио и видео с перемоткой), текст, ссылка и комментарий ученика, «Скачать
 * всё» одним архивом. Оценка по желанию — «Без оценки» или 1–10 — и
 * комментарий ученику; «Проверено → следующая» сразу открывает следующую
 * непроверенную. Вернуть на доработку нельзя (решение владельца); проверенную
 * можно проверить заново — оценка в журнале обновится.
 *
 * Выбранный ученик живёт в адресе (`?student=`): из журнала клетка «ДЗ»
 * открывает сразу его работу. На телефоне — либо список, либо работа.
 */
import { Fragment, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { downloadFile } from '../../api/client'
import { useCheckSubmission, useReviewDetail, type HomeworkSubmission, type ReviewDetail, type ReviewStudent } from '../../api/homework'
import Field from '../../components/Field'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { usePhone } from '../../phone'
import { dueWords, FileLine, FileView, downloadHomeworkFile, firstLine, lateSpan } from './homeworkParts'
import { dateWords } from './shared'

type State = ReviewStudent['state']

const GROUPS: { state: State; label: string }[] = [
  { state: 'unchecked', label: tk('Не проверено') },
  { state: 'checked', label: tk('Проверено') },
  { state: 'missed', label: tk('Не сдали') },
]

const GRADES = Array.from({ length: 10 }, (_, i) => i + 1)

/** Подпись ученика в списке: когда сдал, на сколько опоздал, какая оценка. */
function markOf(row: ReviewStudent, detail: ReviewDetail): string {
  const sub = row.submission
  if (row.state === 'checked' && sub) return sub.grade !== null ? t('оценка {mark}', { mark: sub.grade }) : t('без оценки')
  if (row.state === 'unchecked' && sub) {
    return sub.late_minutes ? t('с опозданием на {span}', { span: lateSpan(sub.late_minutes) }) : t('сдано {when}', { when: dueWords(sub.submitted_at) })
  }
  return row.absent ? t('не сдано · был «н» {date}', { date: dateWords(detail.lesson.date) }) : t('не сдано')
}

function dotOf(row: ReviewStudent): string {
  if (row.state === 'checked') return 'done'
  if (row.state === 'unchecked') return row.submission?.late_minutes ? 'late' : 'new'
  return 'none'
}

/** Чип над работой: вовремя, с опозданием, проверено, не сдано. */
function stateChip(row: ReviewStudent): { tone: Tone; text: string } {
  const sub = row.submission
  if (!sub) return { tone: 'neutral', text: t('не сдано') }
  if (row.state === 'checked') return { tone: 'good', text: sub.grade !== null ? t('проверено · оценка {mark}', { mark: sub.grade }) : t('проверено без оценки') }
  if (sub.late_minutes) return { tone: 'warn', text: `${t('с опозданием на {span}', { span: lateSpan(sub.late_minutes) })} · ${dueWords(sub.submitted_at)}` }
  return { tone: 'accent', text: `${t('сдано вовремя')} · ${dueWords(sub.submitted_at)}` }
}

/** Почему работы нет: срок ещё идёт, сдача закрыта или ещё может прийти. */
function missedWords(detail: ReviewDetail, row: ReviewStudent): string {
  const past = detail.due_at !== null && Date.now() > new Date(detail.due_at).getTime()
  const why = !past
    ? t('Срок ещё идёт.')
    : detail.late_policy === 'close'
      ? t('Срок прошёл, сдача закрыта.')
      : t('Срок прошёл: работа ещё может прийти с пометкой «с опозданием».')
  return [t('Ученик не сдал работу.'), why, row.absent ? t('В день урока был «н».') : ''].filter(Boolean).join(' ')
}

/** Оценка и комментарий: «Проверено» и «Проверено → следующая». */
function GradeBox({ sub, onDone }: { sub: HomeworkSubmission; onDone: (next: boolean) => void }) {
  const check = useCheckSubmission()
  const checked = sub.checked_at !== null
  const [mark, setMark] = useState<number | null>(checked ? sub.grade : null)
  const [comment, setComment] = useState(sub.teacher_comment)
  const submit = (next: boolean) =>
    check.mutate(
      { id: sub.id, mark, comment },
      {
        onSuccess: () => {
          toast.success(t('Проверено'))
          onDone(next)
        },
        onError: (e) => toast.error(e.message),
      },
    )
  return (
    <div className="hwrev__grade">
      <span className="t-caps">{`${t('Оценка')} · ${t('необязательно')}`}</span>
      <div className="hwrev__scale" role="group" aria-label={t('Оценка')}>
        <Button variant={mark === null ? 'default' : 'outline'} size="sm" aria-pressed={mark === null} onClick={() => setMark(null)}>
          {t('Без оценки')}
        </Button>
        {GRADES.map((n) => (
          <Button key={n} variant={mark === n ? 'default' : 'outline'} size="sm" aria-pressed={mark === n} onClick={() => setMark(n)}>
            {n}
          </Button>
        ))}
      </div>
      <Field
        kind="textarea"
        name="teacher-comment"
        label={t('Комментарий ученику')}
        value={comment}
        onChange={setComment}
        rows={3}
        placeholder={t('Что хорошо, что поправить. Ученик увидит его вместе с оценкой.')}
      />
      <div className="acad__actions">
        <Button size="sm" disabled={check.isPending} onClick={() => submit(true)}>
          {t('Проверено → следующая')}
        </Button>
        <Button variant="outline" size="sm" disabled={check.isPending} onClick={() => submit(false)}>
          {t('Проверено')}
        </Button>
      </div>
      <span className="t-note">
        {checked
          ? `${t('Оценку можно изменить — она сразу обновится в журнале.')} ${t('Оценка попадёт в журнал в колонку «ДЗ» этого урока. Вернуть работу на доработку нельзя — только проверить.')}`
          : t('Оценка попадёт в журнал в колонку «ДЗ» этого урока. Вернуть работу на доработку нельзя — только проверить.')}
      </span>
    </div>
  )
}

/** Выбранная работа: шапка с чипом и «Скачать всё», файлы, ответ, оценка. */
function Work({ detail, row, onDone, back }: { detail: ReviewDetail; row: ReviewStudent; onDone: (next: boolean) => void; back?: () => void }) {
  const sub = row.submission
  const chip = stateChip(row)
  const [zipping, setZipping] = useState(false)
  const zip = async () => {
    if (!sub) return
    setZipping(true)
    try {
      await downloadFile(`/homework/submissions/${sub.id}/zip/`, `${row.student.full_name}.zip`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('Архив не скачался — попробуйте ещё раз'))
    } finally {
      setZipping(false)
    }
  }
  const safeLink = sub?.link && /^https?:\/\//i.test(sub.link) ? sub.link : ''
  return (
    <DataCard
      title={row.student.full_name}
      note={detail.lesson.cohort_kind === 'stream' ? row.student.group : undefined}
      right={
        <>
          <Chip tone={chip.tone}>{chip.text}</Chip>
          {sub && (sub.files.length > 0 || sub.text || sub.link) && (
            <Button variant="outline" size="sm" disabled={zipping} onClick={() => void zip()}>
              {t('Скачать всё')}
            </Button>
          )}
          {back && (
            <Button variant="outline" size="sm" onClick={back}>
              {t('Все ученики')}
            </Button>
          )}
        </>
      }
    >
      {!sub ? (
        <p className="acad__note">{missedWords(detail, row)}</p>
      ) : (
        <div className="hwrev__body">
          {sub.files.map((file) => (
            <FileView key={file.id} file={file} />
          ))}
          {sub.text && (
            <div>
              <span className="t-caps">{t('Текст ответа')}</span>
              <p className="hwrev__answer">{sub.text}</p>
            </div>
          )}
          {sub.link && (
            <div>
              <span className="t-caps">{t('Ссылка')}</span>
              <p className="hwrev__answer">
                {safeLink ? (
                  <a className="hwrev__link" href={safeLink} target="_blank" rel="noopener noreferrer">
                    {safeLink}
                  </a>
                ) : (
                  sub.link
                )}
              </p>
            </div>
          )}
          {sub.comment && <span className="t-note">{t('Комментарий ученика: «{comment}»', { comment: sub.comment })}</span>}
          {sub.files.length === 0 && !sub.text && !sub.link && <span className="t-note">{t('В работе нет файлов и текста')}</span>}
          {detail.may_check ? (
            <GradeBox key={`${sub.id}-${sub.checked_at ?? ''}`} sub={sub} onDone={onDone} />
          ) : (
            sub.checked_at && (
              <Rows>
                <Row title={t('Оценка')} value={sub.grade} none={t('без оценки')} note={sub.teacher_comment ? `«${sub.teacher_comment}»` : undefined} />
              </Rows>
            )
          )}
        </div>
      )}
    </DataCard>
  )
}

export default function HomeworkCheck() {
  const { id } = useParams()
  const navigate = useNavigate()
  const phone = usePhone()
  const [params, setParams] = useSearchParams()
  const assignment = Number(id)
  const detail = useReviewDetail(Number.isFinite(assignment) ? assignment : null)
  if (detail.isLoading) return <Loading kind="cards" />
  if (detail.error) return <ErrorNote error={detail.error} />
  if (!detail.data) return null

  const data = detail.data
  const students = data.students
  const byState = (state: State) => students.filter((row) => row.state === state)
  const unchecked = byState('unchecked')
  const chosen = Number(params.get('student')) || null
  // без выбора на ноутбуке открыта первая непроверенная; на телефоне — список
  const current = students.find((row) => row.student.id === chosen) ?? (phone ? null : (unchecked[0] ?? students[0] ?? null))
  const pick = (student: number | null) => {
    const copy = new URLSearchParams(params)
    if (student === null) copy.delete('student')
    else copy.set('student', String(student))
    setParams(copy, { replace: true })
  }
  const onDone = (next: boolean) => {
    if (!next || !current) return
    // следующая непроверенная после текущей, по кругу
    const at = unchecked.findIndex((row) => row.student.id === current.student.id)
    const order = at >= 0 ? [...unchecked.slice(at + 1), ...unchecked.slice(0, at)] : unchecked
    const following = order.find((row) => row.student.id !== current.student.id)
    if (following) pick(following.student.id)
    else toast.success(t('Все сданные работы проверены'))
  }
  const title = firstLine(data.text, data.lesson.subject)

  const list = (
    <DataCard title={t('Ученики')} count={students.length} className="hwrev__list" empty={students.length === 0 && t('в составе нет учеников')}>
      {GROUPS.map(({ state, label }) => {
        const rows = byState(state)
        if (rows.length === 0) return null
        return (
          <Fragment key={state}>
            <div className="hwrev__grp t-caps">{`${t(label)} · ${rows.length}`}</div>
            <Rows>
              {rows.map((row) => (
                <div key={row.student.id} className={`hwrev__pick${current?.student.id === row.student.id ? ' hwrev__pick--on' : ''}`}>
                  <Row
                    lead={<span className={`hwrev__dot hwrev__dot--${dotOf(row)}`} aria-hidden="true" />}
                    title={row.student.full_name}
                    note={`${data.lesson.cohort_kind === 'stream' ? `${row.student.group} · ` : ''}${markOf(row, data)}`}
                    onOpen={() => pick(row.student.id)}
                  />
                </div>
              ))}
            </Rows>
          </Fragment>
        )
      })}
    </DataCard>
  )

  const task = (
    <DataCard title={t('Задание')}>
      <p className="hwrev__answer">{data.text || t('текст задания не записан')}</p>
      {data.files.map((file) => (
        <FileLine key={file.id} file={file}>
          <Button variant="link" size="sm" onClick={() => void downloadHomeworkFile(file.id)}>
            {t('Скачать')}
          </Button>
        </FileLine>
      ))}
      <span className="t-note">{`${t('Урок {date}', { date: dateWords(data.lesson.date) })} · ${data.lesson.cohort}${data.lesson.teacher ? ` · ${data.lesson.teacher.short}` : ''}`}</span>
    </DataCard>
  )

  return (
    <div>
      <ScreenHead
        title={`${title} · ${data.lesson.cohort}`}
        crumb={{ label: t('Проверка ДЗ'), to: '/homework-review' }}
        subtitle={`${data.lesson.subject} · ${t('срок {when}', { when: dueWords(data.due_at) })} · ${t('сдали {done} из {total}', { done: data.submitted, total: data.total })} · ${t('не проверено: {n}', { n: data.unchecked })}`}
        actions={
          <Button variant="outline" size="sm" onClick={() => navigate(`/lessons/${data.lesson.id}`)}>
            {t('Открыть урок')}
          </Button>
        }
      />
      {phone ? (
        current ? (
          <Work key={current.student.id} detail={data} row={current} onDone={onDone} back={() => pick(null)} />
        ) : (
          <div className="acad__stack">
            {list}
            {task}
          </div>
        )
      ) : (
        <div className="hwrev">
          <div className="acad__stack">
            {list}
            {task}
          </div>
          {current ? <Work key={current.student.id} detail={data} row={current} onDone={onDone} /> : <DataCard title={t('Работа')} empty={t('выберите ученика слева')} />}
        </div>
      )}
    </div>
  )
}
