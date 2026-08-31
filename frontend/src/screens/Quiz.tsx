/**
 * Квиз в нашем виде (фаза 46): соло на время, вызов по коду, зачёт классов.
 *
 * У образца здесь рейтинговые матчи, MMR и публичная таблица лидеров.
 * Мы так не делаем: у нас 250 подростков в состоянии поступления, и «топ-50
 * по XP» на экране — ежедневное напоминание остальным двумстам, что они
 * не в нём. Публичен только результат класса, а не строка ученика.
 *
 * Вызов передаётся кодом: списка одноклассников ученику не показывается
 * нигде, включая сырой ответ API (инвариант №7).
 */
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  useAnswerQuestion,
  usePracticeSession,
  useQuiz,
  useQuizActions,
  type QuizMatchRow,
  type PrepSession,
} from '../api/hooks'
import Empty from '../components/Empty'
import { DataCard, ErrorNote, Loading, Metric, MetricRow, ScreenHead, ScreenTabs } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { NativeSelect } from '../components/ui/native-select'
import './quiz.css'
import { t } from '../i18n'

type Mode = 'play' | 'matches' | 'teams'

const EXAMS = ['IELTS', 'SAT', 'TOEFL', 'ACT', 'ЕНТ', 'Duolingo', 'HSK']

/** Игра: вопрос за вопросом, время каждого ответа уходит на сервер. */
function Runner({
  session,
  player,
  onDone,
}: {
  session: PrepSession
  player: number
  onDone: (match: QuizMatchRow) => void
}) {
  const [index, setIndex] = useState(0)
  const [chosen, setChosen] = useState<Record<number, number>>({})
  const answer = useAnswerQuestion()
  const { finish } = useQuizActions()
  const startedAt = useRef(Date.now())
  const shownAt = useRef(Date.now())

  const question = session.questions[index]
  const isLast = index >= session.questions.length - 1
  if (!question) return <Loading />

  const pick = (optionId: number) => {
    // секунды на этот вопрос: из них и складывается прибавка за скорость
    const seconds = Math.max(0, Math.round((Date.now() - shownAt.current) / 1000))
    setChosen((prev) => ({ ...prev, [question.answer_id]: optionId }))
    answer.mutate({ session: session.id, answer_id: question.answer_id, option: optionId, seconds })
  }

  const next = () => {
    shownAt.current = Date.now()
    setIndex(index + 1)
  }

  return (
    <div className="card card-pad quiz__runner">
      <div className="row-between">
        <span className="eyebrow">
          {t('Вопрос')} {index + 1} {t('из')} {session.questions.length}
        </span>
        <Badge variant="mute">{session.exam_type}</Badge>
      </div>
      <p className="muted quiz__topic">
        {question.section} · {question.topic}
      </p>
      <p className="quiz__text">{question.text}</p>
      <div className="quiz__options">
        {question.options.map((option) => (
          <Button
            key={option.id}
            variant="outline"
            className={`quiz__option${chosen[question.answer_id] === option.id ? ' quiz__option--picked' : ''}`}
            onClick={() => pick(option.id)}
          >
            <b>{option.letter}.</b> {option.text}
          </Button>
        ))}
      </div>
      <div className="toolbar">
        <span className="toolbar__spacer" />
        {!isLast && (
          <Button size="sm" onClick={next}>
            {t('Дальше')}
          </Button>
        )}
        {isLast && (
          <Button
            size="sm"
            disabled={finish.isPending}
            onClick={() =>
              finish.mutate(
                { player, seconds: Math.round((Date.now() - startedAt.current) / 1000) },
                { onSuccess: onDone, onError: (error) => toast.error(error.message) },
              )
            }
          >
            {t('Закончить')}
          </Button>
        )}
      </div>
    </div>
  )
}

function MatchCard({ match }: { match: QuizMatchRow }) {
  const mine = match.players.find((player) => player.is_me)
  const rival = match.players.find((player) => !player.is_me)
  return (
    <DataCard
      title={match.kind_title}
      note={`${match.exam_type}${match.section ? ` · ${match.section}` : ''}`}
      accent={match.kind === 'duel' ? 'indigo' : 'teal'}
    >
      {match.code && (
        <p className="quiz__code">
          {t('Код вызова:')} <b className="num">{match.code}</b>
          <span className="muted"> · {t('передайте его однокласснику')}</span>
        </p>
      )}
      <MetricRow>
        <Metric value={mine?.score ?? 0} label={t('Мой счёт')} />
        <Metric value={`${mine?.percent ?? 0}%`} label={t('Точность')} />
        <Metric value={mine?.best_streak ?? 0} label={t('Лучшая серия')} />
      </MetricRow>
      {rival && (
        <p className="quiz__rival">
          {rival.name}: <b className="num">{rival.score}</b>{' '}
          <span className="muted">{rival.finished ? `· ${rival.percent}%` : `· ${t('ещё играет')}`}</span>
        </p>
      )}
    </DataCard>
  )
}

export default function Quiz() {
  const [mode, setMode] = useState<Mode>('play')
  const [exam, setExam] = useState('IELTS')
  const [code, setCode] = useState('')
  const [player, setPlayer] = useState<number | null>(null)
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [result, setResult] = useState<QuizMatchRow | null>(null)

  const state = useQuiz()
  const { start, join } = useQuizActions()
  const session = usePracticeSession(sessionId)

  if (state.isLoading) return <Loading kind="cards" />
  if (state.error) return <ErrorNote error={state.error} />

  const data = state.data
  const bank = data?.bank
  const stats = data?.stats

  const begin = (kind: 'solo' | 'duel') =>
    start.mutate(
      { kind, exam_type: exam },
      {
        onSuccess: (made) => {
          setResult(null)
          setPlayer(made.player)
          setSessionId(made.session)
        },
        onError: (error) => toast.error(error.message),
      },
    )

  return (
    <div>
      <ScreenHead
        title={t('Квиз')}
        subtitle={t(
          'Соло на время, вызов однокласснику по коду и зачёт классов. Личных рейтингов у нас нет.',
        )}
      />

      <ScreenTabs
        value={mode}
        onChange={setMode}
        items={[
          { value: 'play', label: t('Играть') },
          { value: 'matches', label: `${t('Мои матчи')} · ${data?.matches.length ?? 0}` },
          { value: 'teams', label: t('Зачёт классов') },
        ]}
      />

      {mode === 'play' && (
        <>
          {!bank?.ready && (
            <Empty
              icon="target"
              title={t('Заданий пока нет')}
              what={bank?.detail ?? ''}
              hint={t(
                'Банк заданий загружает администратор файлом, а ведёт академический директор на «Пробных».',
              )}
            />
          )}

          {bank?.ready && sessionId === null && (
            <>
              <div className="card card-pad quiz__start">
                <label className="quiz__field">
                  <span className="eyebrow">{t('Экзамен')}</span>
                  <NativeSelect
                    value={exam}
                    onChange={(event) => setExam(event.target.value)}
                    aria-label={t('Экзамен')}
                  >
                    {EXAMS.map((row) => (
                      <option key={row} value={row}>
                        {row}
                      </option>
                    ))}
                  </NativeSelect>
                </label>
                <div className="toolbar">
                  <Button disabled={start.isPending} onClick={() => begin('solo')}>
                    {t('Соло на время')}
                  </Button>
                  <Button variant="outline" disabled={start.isPending} onClick={() => begin('duel')}>
                    {t('Позвать одноклассника')}
                  </Button>
                </div>
                <p className="muted quiz__note">
                  {t('Вызов даёт код — передайте его сами. Списка одноклассников здесь нет и не будет.')}
                </p>
              </div>

              <div className="card card-pad quiz__start">
                <span className="eyebrow">{t('Пришёл вызов?')}</span>
                <div className="toolbar">
                  <Input
                    placeholder={t('Код вызова')}
                    value={code}
                    onChange={(event) => setCode(event.target.value.toUpperCase())}
                  />
                  <Button
                    variant="outline"
                    disabled={join.isPending || code.length < 4}
                    onClick={() =>
                      join.mutate(code, {
                        onSuccess: (made) => {
                          setResult(null)
                          setPlayer(made.player)
                          setSessionId(made.session)
                        },
                        onError: (error) => toast.error(error.message),
                      })
                    }
                  >
                    {t('Принять вызов')}
                  </Button>
                </div>
              </div>

              {stats && stats.matches > 0 && (
                <DataCard
                  title={t('Ваша статистика')}
                  note={t('Видите её только вы и директора — общей таблицы нет')}
                  accent="brand"
                >
                  <MetricRow>
                    <Metric value={stats.matches} label={t('Сыграно матчей')} />
                    <Metric value={`${stats.accuracy}%`} label={t('Точность')} />
                    <Metric value={`${stats.average_seconds} с`} label={t('Среднее время')} />
                    <Metric value={stats.best_streak} label={t('Лучшая серия')} />
                  </MetricRow>
                </DataCard>
              )}
            </>
          )}

          {sessionId !== null && !result && session.data && player !== null && (
            <Runner
              session={session.data}
              player={player}
              onDone={(match) => {
                setResult(match)
                setSessionId(null)
                setPlayer(null)
              }}
            />
          )}

          {result && (
            <>
              <MatchCard match={result} />
              <div className="toolbar">
                <Button onClick={() => setResult(null)}>{t('Сыграть ещё')}</Button>
              </div>
            </>
          )}
        </>
      )}

      {mode === 'matches' && (
        <div className="grid grid--two">
          {(data?.matches ?? []).map((match) => (
            <MatchCard key={match.id} match={match} />
          ))}
          {(data?.matches ?? []).length === 0 && (
            <Empty
              icon="medal"
              title={t('Матчей пока нет')}
              what={t('Сыграйте соло или позовите одноклассника — матчи появятся здесь.')}
              hint={t('Результат соло видите только вы; результат вызова — вы и ваш соперник, больше никто.')}
              action={t('Играть')}
              onAction={() => setMode('play')}
            />
          )}
        </div>
      )}

      {mode === 'teams' && (
        <DataCard
          title={t('Зачёт классов')}
          note={`${t('Сумма класса за последние')} ${data?.teams.days ?? 30} ${t('дней')}`}
          accent="teal"
        >
          <table className="tbl">
            <thead>
              <tr>
                <th>{t('Класс')}</th>
                <th>{t('Счёт')}</th>
                <th>{t('Матчей')}</th>
                <th>{t('Точность')}</th>
              </tr>
            </thead>
            <tbody>
              {(data?.teams.teams ?? []).map((row) => (
                <tr key={row.team}>
                  <td>
                    <b>{row.team}</b>
                  </td>
                  <td className="num">{row.score}</td>
                  <td className="num">{row.matches}</td>
                  <td className="num">{row.accuracy}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(data?.teams.teams ?? []).length === 0 && (
            <p className="muted quiz__note">{t('Классы ещё не играли — сыграйте первым.')}</p>
          )}
          <p className="muted quiz__note">
            {t('Здесь только суммы классов: строк отдельных учеников в этом зачёте нет.')}
          </p>
        </DataCard>
      )}
    </div>
  )
}
