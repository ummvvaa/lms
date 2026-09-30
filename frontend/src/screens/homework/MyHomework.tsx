/**
 * «Домашние задания» ученика: задания со сдачей в LMS по вкладкам —
 * к сдаче, на проверке, проверено, не сдано (образец `docs/ui/dz-sdacha.html`).
 *
 * Карточка — предмет, кто задал, сколько осталось, текст задания и файлы
 * учителя, правило после срока и «Сдать». Сколько одноклассников сдали,
 * ученик не видит нигде. ДЗ без сдачи живут в уроке и в расписании.
 */
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useMyHomework, type MyHomework, type StudentState } from '../../api/homework'
import { useAuth } from '../../auth/AuthContext'
import { Row, Rows, Segmented } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { dateWords } from '../academics/shared'
import { dayInSchoolZone } from '../../lib/dates'
import { FilePill, handedWords, leftChip, limitsWords, policyChip, whenWords, whoWords } from './myWork'
import './myWork.css'

/** Вкладки: подпись и пустое состояние — ключи перевода, переводятся при показе. */
const TABS: { value: StudentState; label: string; empty: string }[] = [
  { value: 'todo', label: tk('К сдаче'), empty: tk('сдавать сейчас нечего') },
  { value: 'review', label: tk('На проверке'), empty: tk('работ на проверке нет') },
  { value: 'checked', label: tk('Проверено'), empty: tk('проверенных работ пока нет') },
  { value: 'missed', label: tk('Не сдано'), empty: tk('несданных работ нет') },
]

function isTab(value: string | null): value is StudentState {
  return TABS.some((tab) => tab.value === value)
}

function HomeworkCard({ item }: { item: MyHomework }) {
  const navigate = useNavigate()
  const open = () => navigate(`/homework/${item.id}`)
  const submission = item.submission
  const policy = policyChip(item)
  const files = item.state === 'todo' || item.state === 'missed' ? item.files : (submission?.files ?? [])

  let deadline: { chip: string; tone: Tone; small: string }
  if (item.state === 'review' && submission) {
    const handed = handedWords(submission)
    deadline = { chip: handed.chip, tone: handed.tone, small: handed.when }
  } else if (item.state === 'checked') {
    deadline = { chip: t('проверено'), tone: 'good', small: '' }
  } else if (item.state === 'missed' || item.past_due) {
    deadline = {
      chip: t('срок прошёл'),
      tone: 'bad',
      small: item.due_at ? t('был до {when}', { when: whenWords(item.due_at) }) : '',
    }
  } else {
    const left = leftChip(item)
    deadline = {
      chip: left.label,
      tone: left.tone,
      small: item.due_at ? t('до {when}', { when: whenWords(item.due_at) }) : '',
    }
  }
  const checkedOn = submission?.checked_at
    ? t('проверено {date}', { date: dateWords(dayInSchoolZone(new Date(submission.checked_at))) })
    : ''
  const draft =
    item.state === 'todo' &&
    submission &&
    !submission.submitted_at &&
    (submission.files.length > 0 || submission.text || submission.link)

  return (
    <section className="card card-pad mywork__card">
      <div className="mywork__head">
        <span className="mywork__subject t-card">{item.lesson.subject}</span>
        <span className="mywork__who t-note">
          {item.state === 'checked' && checkedOn
            ? [item.lesson.teacher?.short ?? '', checkedOn].filter(Boolean).join(' · ')
            : whoWords(item)}
        </span>
      </div>
      <div className="mywork__deadline">
        <Chip tone={deadline.tone}>{deadline.chip}</Chip>
        {deadline.small && <span className="t-note">{deadline.small}</span>}
      </div>
      {item.state === 'checked' && submission ? (
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
      ) : (
        <div className="mywork__task">{item.text || t('Задание — в прикреплённых файлах')}</div>
      )}
      <div className="mywork__foot">
        {files.map((file) => (
          <FilePill key={file.id} file={file} />
        ))}
        <span className="mywork__spacer" />
        {draft && <Chip tone="warn">{t('начато, не сдано')}</Chip>}
        {item.state === 'todo' && !item.past_due && <Chip tone={policy.tone}>{policy.label}</Chip>}
        {item.state === 'missed' && <Chip>{t('учитель закрыл сдачу после срока')}</Chip>}
        {item.state === 'todo' ? (
          <Button onClick={open}>{item.past_due ? t('Сдать с опозданием') : t('Сдать')}</Button>
        ) : (
          <Button variant="outline" onClick={open}>
            {t('Открыть')}
          </Button>
        )}
      </div>
    </section>
  )
}

export default function MyHomeworkScreen() {
  const { me } = useAuth()
  const student = me?.role === 'student'
  const { data, isLoading, error } = useMyHomework(student)
  const [params, setParams] = useSearchParams()
  if (me && !student) return <Navigate to="/dashboard" replace />
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const asked = params.get('tab')
  // без выбора — первая непустая вкладка: открыть «К сдаче» с нулём, когда ждёт проверенное, — лишний шаг
  const tab: StudentState = isTab(asked)
    ? asked
    : (TABS.find((item) => data.counts[item.value] > 0)?.value ?? 'todo')
  const setTab = (next: StudentState) => setParams(next === 'todo' ? {} : { tab: next }, { replace: true })
  const items = data.items.filter((item) => item.state === tab)
  const current = TABS.find((item) => item.value === tab) ?? TABS[0]

  return (
    <div>
      <ScreenHead
        title={t('Домашние задания')}
        subtitle={t('Задания, которые нужно сдать в LMS. Остальные ДЗ — в карточке урока и в расписании.')}
      />
      <Segmented
        value={tab}
        onChange={setTab}
        label={t('Состояние заданий')}
        items={TABS.map((item) => ({
          value: item.value,
          label: (
            <>
              {t(item.label)}
              <span className="mywork__count num">{data.counts[item.value]}</span>
            </>
          ),
        }))}
      />
      <div className="acad__cols">
        <div className="acad__stack">
          {items.length === 0 ? (
            <DataCard title={t(current.label)} empty={t(current.empty)} />
          ) : (
            items.map((item) => <HomeworkCard key={item.id} item={item} />)
          )}
        </div>
        <div className="acad__stack">
          <DataCard title={t('Как сдать')}>
            <Rows>
              <Row
                icon="docs"
                tone="accent"
                title={t('Сфотографируйте тетрадь')}
                note={t('Несколько фото склеятся в один PDF — учитель листает его страницами')}
              />
              <Row
                icon="upload"
                tone="info"
                title={t('Или приложите файл')}
                note={`${t('Документ, аудио, видео или ссылка')} · ${limitsWords(data.limits)}`}
              />
              <Row
                icon="clock"
                tone="warn"
                title={t('До срока работу можно заменить')}
                note={t('После срока — только просмотр, если учитель не принимает работы позже')}
              />
            </Rows>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
