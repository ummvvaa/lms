/**
 * Отметка по QR на телефоне ученика: `/s/<токен>` (макеты ScanPhone и StScan, 27.10.2026).
 *
 * Камера открывает ссылку — страница сразу отправляет токен. Не вошёл:
 * сервер проверил, что код свежий, и держит отметку в этом браузере две
 * минуты; здесь же форма входа, после входа отметка ставится сама.
 * Ответы: «Ты отмечен», «Уже отмечен», «Код устарел», «Это не твоё занятие»,
 * «Занятие ещё не началось / уже закончилось».
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router'
import { scan, type ScanAnswer } from '../../api/sport'
import { useAuth } from '../../auth/AuthContext'
import Backdrop from '../../components/Backdrop'
import Field from '../../components/Field'
import { Chip } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { studentMayOpen } from '../../layout/nav'
import { formatDateLong, formatTime, formatWeekday } from '../../lib/format'
import '../login-layout.css'
import './sport.css'

function message(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export default function Scan() {
  const { token = '' } = useParams()
  const { me, isLoading, login } = useAuth()
  const [answer, setAnswer] = useState<ScanAnswer | null>(null)
  const [error, setError] = useState<string | null>(null)
  const sent = useRef(false)

  useEffect(() => {
    if (isLoading || sent.current) return
    sent.current = true
    scan(token)
      .then(setAnswer)
      .catch((reason: unknown) => setError(message(reason, t('Не удалось отметиться'))))
  }, [isLoading, token])

  return (
    <div className="login">
      <Backdrop />
      <div className="card card-pad card--beam login__card sport-scan">
        {answer?.state === 'login' && !me ? (
          <ScanLogin
            onDone={() =>
              scan(null)
                .then(setAnswer)
                .catch((reason: unknown) => setError(message(reason, t('Не удалось отметиться'))))
            }
            login={login}
          />
        ) : error ? (
          <Result tone="bad" title={t('Не получилось отметиться')} text={error} />
        ) : answer ? (
          <Answer answer={answer} />
        ) : (
          <p className="t-note">{t('Отмечаем…')}</p>
        )}
      </div>
    </div>
  )
}

function ScanLogin({
  onDone,
  login,
}: {
  onDone: () => void
  login: (email: string, password: string) => Promise<unknown>
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <>
      <h1 className="t-card">{t('Войди, чтобы отметиться')}</h1>
      <p className="t-note">{t('После входа отметка поставится сама — код подождёт 2 минуты')}</p>
      <form
        className="login__form"
        onSubmit={(event) => {
          event.preventDefault()
          setBusy(true)
          setError(null)
          login(email, password)
            .then(onDone)
            .catch((reason: unknown) => setError(message(reason, t('Не удалось войти'))))
            .finally(() => setBusy(false))
        }}
      >
        <Field
          name="email"
          label={t('Почта или логин')}
          value={email}
          onChange={setEmail}
          autoComplete="username"
          required
          autoFocus
        />
        <Field
          kind="password"
          name="password"
          label={t('Пароль')}
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
          required
        />
        <Button type="submit" disabled={busy}>
          {t('Войти и отметиться')}
        </Button>
      </form>
      {error && (
        <Chip tone="bad" className="login__hint">
          {error}
        </Chip>
      )}
    </>
  )
}

function Result({
  tone,
  title,
  text,
  foot,
}: {
  tone: 'good' | 'warn' | 'bad'
  title: string
  text?: string
  foot?: ReactNode
}) {
  const { me } = useAuth()
  const navigate = useNavigate()
  // у 8–10 секция — в разделе «Спорт», у 11 — во вкладке «Спорт» портфолио
  const home = studentMayOpen(me?.sections, '/sport')
    ? '/sport?sport=section'
    : '/my-data?tab=sport&sport=section'
  return (
    <>
      <Chip tone={tone}>{title}</Chip>
      {text && <p className="sport-scan__text">{text}</p>}
      {foot}
      {me && (
        <Button variant="outline" onClick={() => navigate(home)}>
          {t('Моя секция')}
        </Button>
      )}
    </>
  )
}

function Answer({ answer }: { answer: ScanAnswer }) {
  const session = answer.session
  const where = session
    ? t('{section}, {day} {time}', {
        section: session.section,
        day: session.day.toLocaleLowerCase(),
        time: `${session.starts}–${session.ends}`,
      })
    : ''
  switch (answer.state) {
    case 'marked':
    case 'already':
      return (
        <Result
          tone="good"
          title={answer.state === 'marked' ? t('Ты отмечен') : t('Уже отмечен')}
          text={answer.state === 'marked' ? t('{where}. Хорошей тренировки!', { where }) : where}
          foot={
            answer.marked_at && (
              <div className="dir__line">
                <span>{t('Отметка')}</span>
                <b>
                  {t('{day}, {date} · {time}', {
                    day: formatWeekday(answer.marked_at, 'short'),
                    date: formatDateLong(answer.marked_at),
                    time: formatTime(answer.marked_at),
                  })}
                </b>
              </div>
            )
          }
        />
      )
    case 'foreign':
      return (
        <Result
          tone="warn"
          title={t('Это не твоё занятие')}
          text={t('Сейчас идёт {where} для параллелей {grades}. Ты записан на {mine}', {
            where,
            grades: session?.grades ?? '',
            mine: [answer.mine?.section, answer.mine?.slot].filter(Boolean).join(' · '),
          })}
        />
      )
    case 'not_started':
      return (
        <Result
          tone="warn"
          title={t('Занятие ещё не началось')}
          text={t('Отметиться можно с начала занятия до его конца. Начало: {when}', {
            when: answer.starts_at
              ? `${formatDateLong(answer.starts_at)}, ${formatTime(answer.starts_at)}`
              : '',
          })}
        />
      )
    case 'ended':
      return (
        <Result
          tone="warn"
          title={t('Занятие уже закончилось')}
          text={t('Отметиться можно с начала занятия до его конца')}
        />
      )
    case 'no_hour':
      return (
        <Result
          tone="warn"
          title={t('Сначала выбери время занятия')}
          text={t('Пока час не выбран, отметиться на занятии не получится')}
        />
      )
    case 'not_enrolled':
      return <Result tone="warn" title={t('Ты не записан на это занятие')} text={where} />
    case 'login':
      return <Result tone="warn" title={t('Войди, чтобы отметиться')} />
    default:
      return (
        <Result
          tone="bad"
          title={t('Код устарел')}
          text={t('QR меняется каждые несколько секунд. Отсканируй код с экрана директора спорта ещё раз')}
        />
      )
  }
}
