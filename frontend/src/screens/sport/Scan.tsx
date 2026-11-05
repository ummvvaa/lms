/**
 * Отметка по QR на телефоне ученика: `/s/<токен>` (макеты ScanPhone и StScan, 27.10.2026).
 *
 * У секции один постоянный код (05.11.2026) — на экране директора и на листе
 * у площадки. Камера открывает ссылку — страница отправляет токен. Сервер
 * сначала проверяет, идёт ли занятие и чьё оно, и только потом просит место
 * (`need_geo`); страница спрашивает геолокацию у браузера и шлёт широту,
 * долготу и точность. Не вошёл — здесь же форма входа, после входа токен
 * уходит снова. Ответы: «Ты отмечен», «Уже отмечен», «Ты отмечен как гость»,
 * «Отметка на проверке» (место неточно или чуть за радиусом), «Ты далеко»,
 * «Это не твоё занятие», «Сейчас нет занятия». Запретил геолокацию —
 * инструкция для iPhone и Android и «Попробовать снова»: без места отметки нет.
 * Прежний меняющийся код секции — «Этот код больше не работает».
 *
 * Страницу переиспользуют кружки (`kind`): у них код меняющийся — свежий
 * токен ждёт входа в этом браузере две минуты, старый — «Код устарел».
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router'
import { scan, type ScanAnswer, type ScanPosition } from '../../api/sport'
import { LOGO, SCHOOL_NAME } from '../../branding'
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

/** Чем страница отметки отличается у кружка: своя ручка, своя кнопка «назад», свои слова. */
export interface ScanKind {
  send: (token: string | null, position?: ScanPosition) => Promise<ScanAnswer>
  /** кнопка под ответом: адрес и подпись */
  home?: { path: string; label: string }
  /** «Код устарел»: чей экран сканировать снова */
  stale?: string
  /** «Ты отмечен»: пожелание после отметки */
  wish?: string
}

/** Что с местом ученика: спрашиваем у браузера, запрещено, не определилось. */
type Geo = 'idle' | 'asking' | 'denied' | 'failed'

/** Сколько ждём место от телефона, мс: GPS в помещении отвечает не сразу. */
const GEO_TIMEOUT = 15_000

/** Место от браузера: высокая точность, свежее. Отказ — код ошибки Geolocation API (1 — запрещено). */
function locate(): Promise<ScanPosition> {
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject(new Error('unsupported'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) =>
        resolve({ latitude: coords.latitude, longitude: coords.longitude, accuracy: coords.accuracy }),
      reject,
      { enableHighAccuracy: true, timeout: GEO_TIMEOUT, maximumAge: 0 },
    )
  })
}

export default function Scan({ kind }: { kind?: ScanKind } = {}) {
  const send = kind?.send ?? scan
  const { token = '' } = useParams()
  const { me, isLoading, login } = useAuth()
  const [answer, setAnswer] = useState<ScanAnswer | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [geo, setGeo] = useState<Geo>('idle')
  const sent = useRef(false)
  const asked = useRef(false)
  const fail = useCallback(
    (reason: unknown) => setError(message(reason, t('Не удалось отметиться'))),
    [],
  )

  useEffect(() => {
    if (isLoading || sent.current) return
    sent.current = true
    send(token).then(setAnswer).catch(fail)
  }, [isLoading, token, send, fail])

  /** Спросить место и отправить его с токеном печатного кода. */
  const mark = useCallback(() => {
    setGeo('asking')
    locate()
      .then((position) =>
        send(token, position)
          .then((next) => {
            // сервер снова просит место — значит, телефон прислал не координаты
            setGeo(next.state === 'need_geo' ? 'failed' : 'idle')
            setAnswer(next)
          })
          .catch((reason: unknown) => {
            setGeo('idle')
            fail(reason)
          }),
      )
      .catch((reason: unknown) =>
        setGeo((reason as GeolocationPositionError | null)?.code === 1 ? 'denied' : 'failed'),
      )
  }, [send, token, fail])

  // сервер проверил время и запись и просит место — спрашиваем браузер один раз, дальше по кнопке
  useEffect(() => {
    if (answer?.state !== 'need_geo' || asked.current) return
    asked.current = true
    mark()
  }, [answer, mark])

  return (
    <div className="login">
      <Backdrop />
      <div className="login__brand">
        <img className="login__logo" src={LOGO.header} alt="" />
        <span className="login__title">{SCHOOL_NAME}</span>
      </div>
      <div className="card card-pad card--beam login__card sport-scan">
        {answer?.state === 'login' && !me ? (
          <ScanLogin
            onDone={() =>
              // меняющийся код ждёт входа на сервере, печатный не устаревает — шлём его снова
              send(answer.geo ? token : null)
                .then(setAnswer)
                .catch(fail)
            }
            login={login}
            geo={Boolean(answer.geo)}
          />
        ) : error ? (
          <Result tone="bad" title={t('Не получилось отметиться')} text={error} kind={kind} />
        ) : geo === 'denied' ? (
          <GeoDenied onRetry={mark} />
        ) : geo === 'failed' ? (
          <Result
            kind={kind}
            tone="warn"
            title={t('Не удалось определить место')}
            text={t(
              'Включи геолокацию (GPS) на телефоне, выйди ближе к окну или на улицу и попробуй снова. Без геолокации отметки нет',
            )}
            foot={<Button onClick={mark}>{t('Попробовать снова')}</Button>}
          />
        ) : answer && answer.state !== 'need_geo' && geo !== 'asking' ? (
          <Answer answer={answer} kind={kind} onRetry={mark} />
        ) : (
          <p className="t-note">
            {geo === 'asking' || answer?.state === 'need_geo'
              ? t('Определяем, где ты… Разреши доступ к геолокации')
              : t('Отмечаем…')}
          </p>
        )}
      </div>
    </div>
  )
}

/** Ученик запретил геолокацию: как разрешить на iPhone и Android — и повтор. */
function GeoDenied({ onRetry }: { onRetry: () => void }) {
  return (
    <>
      <Chip tone="warn">{t('Разреши доступ к геолокации')}</Chip>
      <p className="sport-scan__text">
        {t('Отметка по этому коду ставится только рядом с местом занятия. Без геолокации отметки нет')}
      </p>
      <div className="sport-scan__how">
        <b>iPhone</b>
        <span className="t-note">
          {t(
            'Настройки → Конфиденциальность и безопасность → Службы геолокации: включи, ниже выбери Safari → «При использовании». В Safari нажми «аА» в строке адреса → Настройки веб-сайта → Геопозиция → Разрешить',
          )}
        </span>
      </div>
      <div className="sport-scan__how">
        <b>Android</b>
        <span className="t-note">
          {t(
            'Включи геолокацию в шторке телефона. В Chrome нажми значок слева от адреса → Разрешения → Местоположение → Разрешить',
          )}
        </span>
      </div>
      <Button onClick={onRetry}>{t('Попробовать снова')}</Button>
    </>
  )
}

function ScanLogin({
  onDone,
  login,
  geo = false,
}: {
  onDone: () => void
  login: (email: string, password: string) => Promise<unknown>
  /** печатный код: после входа страница попросит геолокацию */
  geo?: boolean
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <>
      <h1 className="t-card">{t('Войди, чтобы отметиться')}</h1>
      <p className="t-note">
        {geo
          ? t('После входа разреши доступ к геолокации — и отметка поставится сама')
          : t('После входа отметка поставится сама — код подождёт 2 минуты')}
      </p>
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
  kind,
}: {
  tone: 'good' | 'warn' | 'bad'
  title: string
  text?: string
  foot?: ReactNode
  kind?: ScanKind
}) {
  const { me } = useAuth()
  const navigate = useNavigate()
  // у 8–10 секция — в разделе «Спорт», у 11 — во вкладке «Спорт» портфолио
  const home =
    kind?.home?.path ??
    (studentMayOpen(me?.sections, '/sport') ? '/sport?sport=section' : '/my-data?tab=sport&sport=section')
  return (
    <>
      <Chip tone={tone}>{title}</Chip>
      {text && <p className="sport-scan__text">{text}</p>}
      {foot}
      {me && (
        <Button variant="outline" onClick={() => navigate(home)}>
          {kind?.home?.label ?? t('Мои секции')}
        </Button>
      )}
    </>
  )
}

function Answer({ answer, kind, onRetry }: { answer: ScanAnswer; kind?: ScanKind; onRetry: () => void }) {
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
          kind={kind}
          tone="good"
          title={answer.state === 'marked' ? t('Ты отмечен') : t('Уже отмечен')}
          text={
            answer.state === 'marked' ? (kind?.wish ?? t('{where}. Хорошей тренировки!', { where })) : where
          }
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
    case 'guest':
    case 'guest_already':
      return (
        <Result
          kind={kind}
          tone="good"
          title={answer.state === 'guest' ? t('Ты отмечен как гость') : t('Уже отмечен как гость')}
          text={t('{where}. Ты не записан в эту секцию — записать тебя может директор спорта', { where })}
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
          kind={kind}
          tone="warn"
          title={t('Это не твоё занятие')}
          text={t('Сейчас идёт {where} для параллелей {grades}. В этой секции ты записан на {mine}', {
            where,
            grades: session?.grades ?? '',
            mine: [answer.mine?.section, answer.mine?.slot].filter(Boolean).join(' · '),
          })}
        />
      )
    case 'not_started':
      return (
        <Result
          kind={kind}
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
          kind={kind}
          tone="warn"
          title={t('Занятие уже закончилось')}
          text={t('Отметиться можно с начала занятия до его конца')}
        />
      )
    case 'no_hour':
      return (
        <Result
          kind={kind}
          tone="warn"
          title={t('Сначала выбери время занятия')}
          text={t('Пока час не выбран, отметиться на занятии не получится')}
        />
      )
    case 'not_enrolled':
      return (
        <Result
          kind={kind}
          tone="warn"
          title={kind ? t('Ты не записан в этот кружок') : t('Ты не записан на это занятие')}
          text={where}
        />
      )
    case 'review':
      return (
        <Result
          kind={kind}
          tone="warn"
          title={t('Отметка на проверке')}
          text={
            answer.inaccurate
              ? t(
                  '{where}. Телефон определил место неточно, поэтому отметку подтвердит директор спорта. Подойди к нему, если он рядом',
                  { where },
                )
              : t(
                  '{where}. Ты в {distance} от места занятия — чуть дальше, чем нужно, поэтому отметку подтвердит директор спорта',
                  { where, distance: answer.distance ?? '' },
                )
          }
          foot={
            answer.inaccurate && (
              <Button variant="outline" onClick={onRetry}>
                {t('Попробовать снова')}
              </Button>
            )
          }
        />
      )
    case 'far':
      return (
        <Result
          kind={kind}
          tone="bad"
          title={t('Ты далеко от места занятия ({distance})', { distance: answer.distance ?? '' })}
          text={
            answer.inaccurate
              ? t(
                  'Телефон определил место неточно. Включи GPS, выйди ближе к окну или на улицу и попробуй снова',
                )
              : t('Отметиться можно только рядом с местом занятия: {where}', {
                  where: [session?.section, session?.address].filter(Boolean).join(', '),
                })
          }
          foot={<Button onClick={onRetry}>{t('Попробовать снова')}</Button>}
        />
      )
    case 'no_session':
      return (
        <Result
          kind={kind}
          tone="warn"
          title={t('Сейчас нет занятия этой секции')}
          text={t('{section}. Отметиться можно с начала занятия до его конца', {
            section: answer.place?.section ?? '',
          })}
        />
      )
    case 'replaced':
      return (
        <Result
          kind={kind}
          tone="bad"
          title={t('Этот QR больше не действует')}
          text={t('Отсканируй новый код на месте занятия или подойди к директору спорта')}
        />
      )
    case 'rejected':
      return (
        <Result
          kind={kind}
          tone="bad"
          title={t('Отметка отклонена')}
          text={t(
            '{where}. Директор спорта отклонил отметку на этом занятии. Подойди к нему — он может отметить тебя сам',
            { where },
          )}
        />
      )
    case 'login':
      return <Result kind={kind} tone="warn" title={t('Войди, чтобы отметиться')} />
    default:
      // у кружков код меняющийся и может устареть; у секций он постоянный — прежний код просто не работает
      return kind ? (
        <Result kind={kind} tone="bad" title={t('Код устарел')} text={kind.stale} />
      ) : (
        <Result tone="bad" title={t('Этот код больше не работает')} text={t('Отсканируй QR на площадке')} />
      )
  }
}
