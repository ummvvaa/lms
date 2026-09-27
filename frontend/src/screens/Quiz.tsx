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
import { Row, Rows, StatRow } from '../components/patterns'
import DataTable from '../components/DataTable'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { AnswerOption } from '../components/ui/answer-option'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { SelectField } from '../components/SelectField'
import './quiz.css'
import { t } from '../i18n'

type Mode = 'play' | 'matches' | 'teams' | 'topics'
type TeamRow = { team: string; score: number; matches: number; accuracy: number }

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
        <Chip tone="neutral">{session.exam_type}</Chip>
      </div>
      <p className="muted quiz__topic">
        {question.section} · {question.topic}
      </p>
      <p className="quiz__text">{question.text}</p>
      {/* Вариант ответа — свой элемент, а не кнопка реестра. Кнопка
          реестра красится правилом по двум атрибутам (`[data-slot][data-variant]`),
          и наш класс выбранного варианта по одному классу ему проигрывал:
          нажатие проходило, а на экране не менялось ничего — ученик решал,
          что вариант не выбирается вовсе (найдено владельцем, фаза 48) */}
      <div className="quiz__options" role="radiogroup" aria-label={t('Варианты ответа')}>
        {question.options.map((option) => {
          const picked = chosen[question.answer_id] === option.id
          return (
            <AnswerOption key={option.id} letter={option.letter} picked={picked} onPick={() => pick(option.id)}>
                {option.text}
            </AnswerOption>
          )
        })}
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
    >
      {match.code && (
        <p className="quiz__code">
          {t('Код вызова:')} <b className="num">{match.code}</b>
          <span className="muted"> · {t('передайте его однокласснику')}</span>
        </p>
      )}
      <StatRow>
        <Kpi value={mine?.score ?? 0} label={t('Мой счёт')} />
        <Kpi value={`${mine?.percent ?? 0}%`} label={t('Точность')} />
        <Kpi value={mine?.best_streak ?? 0} label={t('Лучшая серия')} />
      </StatRow>
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
  const [exam, setExam] = useState('')
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

  // Процент побед считается только по вызовам: в соло соперника нет,
  // и «победа над собой» — это не то число, ради которого играют
  const examList = data?.exams ?? []
  // первый видимый экзамен подставляется сам: пустой выбор в списке
  // из двух пунктов — лишний шаг
  const chosenExam = exam || examList[0]?.code || ''

  const duels = (data?.matches ?? []).filter((match) => match.kind === 'duel' && match.status === 'done')
  const wins = duels.filter((match) => {
    const mine = match.players.find((player) => player.is_me)
    const rival = match.players.find((player) => !player.is_me)
    return mine && rival && mine.score > rival.score
  }).length
  const winRate = duels.length === 0 ? null : Math.round((wins / duels.length) * 100)

  // Разрез по разделам — по своим же матчам: чужих здесь нет вовсе
  const byTopic = new Map<string, { total: number; sum: number }>()
  for (const match of data?.matches ?? []) {
    const mine = match.players.find((player) => player.is_me)
    if (!mine || !mine.finished) continue
    const key = [match.exam_type, match.section].filter(Boolean).join(' · ')
    const row = byTopic.get(key) ?? { total: 0, sum: 0 }
    byTopic.set(key, { total: row.total + 1, sum: row.sum + mine.percent })
  }
  const topics = [...byTopic.entries()]
    .map(([key, row]) => ({ key, matches: row.total, accuracy: Math.round(row.sum / row.total) }))
    .sort((a, b) => b.matches - a.matches)

  const begin = (kind: 'solo' | 'duel') =>
    start.mutate(
      { kind, exam_type: chosenExam },
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
        subtitle={t('Шесть вопросов на время: точность весит больше скорости. Можно одному, можно позвать одноклассника по коду. Личных рейтингов нет.')}
        actions={
          bank?.ready ? (
            <>
              <Button variant="outline" size="sm" disabled={start.isPending} onClick={() => begin('duel')}>
                {t('Позвать одноклассника')}
              </Button>
              <Button size="sm" disabled={start.isPending} onClick={() => begin('solo')}>
                {t('Начать')}
              </Button>
            </>
          ) : undefined
        }
      />

      <StatRow>
        <Kpi label={t('Заданий в банке')} value={bank?.questions || null} none={t('нет')} />
        <Kpi label={t('Сыграно')} value={stats?.matches || null} none={t('нет')} />
        <Kpi tone="good" label={t('Точность')} value={stats && stats.matches > 0 ? `${stats.accuracy}%` : null} none={t('нет')} />
        <Kpi label={t('Побед в вызовах')} value={winRate === null ? null : `${winRate}%`} none={t('вызовов ещё не было')} />
      </StatRow>

      <ScreenTabs
        value={mode}
        onChange={setMode}
        items={[
          { value: 'play', label: t('Играть') },
          { value: 'matches', label: `${t('Мои матчи')} · ${data?.matches.length ?? 0}` },
          { value: 'teams', label: t('Командный зачёт') },
          { value: 'topics', label: t('По темам') },
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
                {/* Список экзаменов приходит с сервера: школа ведёт два,
                    скрытый в справочнике здесь не появляется (фаза 48) */}
                <label className="quiz__field">
                  <span className="eyebrow">{t('Экзамен')}</span>
                  <SelectField
                    value={chosenExam}
                    onChange={(event) => setExam(event.target.value)}
                    aria-label={t('Экзамен')}
                  >
                    {examList.map((row) => (
                      <option key={row.code} value={row.code}>
                        {row.title}
                      </option>
                    ))}
                  </SelectField>
                </label>
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

              <p className="muted quiz__note">
                {t('Статистику выше видите только вы и директора — общей таблицы учеников нет.')}
              </p>
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
          title={t('Зачёт групп')}
          note={`${t('Сумма группы за последние')} ${data?.teams.days ?? 30} ${t('дней')}`}
        >
          <DataTable
            columns={[
              { key: 'team', title: t('Группа'), width: '40%', cell: (row: TeamRow) => <b>{row.team}</b>, sortBy: (row: TeamRow) => row.team },
              { key: 'score', title: t('Счёт'), width: '20%', align: 'right', cell: (row: TeamRow) => <span className="num">{row.score}</span>, sortBy: (row: TeamRow) => row.score },
              { key: 'matches', title: t('Матчей'), width: '20%', align: 'right', cell: (row: TeamRow) => <span className="num">{row.matches}</span>, sortBy: (row: TeamRow) => row.matches },
              { key: 'accuracy', title: t('Точность'), width: '20%', align: 'right', cell: (row: TeamRow) => <span className="num">{row.accuracy}%</span>, sortBy: (row: TeamRow) => row.accuracy },
            ]}
            rows={data?.teams.teams ?? []}
            rowKey={(row) => row.team}
          />
          {(data?.teams.teams ?? []).length === 0 && (
            <p className="muted quiz__note">{t('Группы ещё не играли — сыграйте первым.')}</p>
          )}
          <p className="muted quiz__note">
            {t('Здесь только суммы групп: строк отдельных учеников в этом зачёте нет.')}
          </p>
        </DataCard>
      )}

      {/* «По темам» считается по вашим же матчам: экзамен и раздел
          у каждого свои, и сводка показывает, где вы отвечаете точнее */}
      {mode === 'topics' && (
        <DataCard title={t('По темам')} note={t('Ваши матчи в разрезе экзамена и раздела')}>
          {topics.length === 0 && (
            <p className="muted quiz__note">{t('Сыграйте первый матч — разбор появится здесь.')}</p>
          )}
          <Rows>
            {topics.map((row) => (
              <Row
                key={row.key}
                icon="book"
                tone="info"
                title={row.key}
                note={`${counted(row.matches, ['матч', 'матча', 'матчей'])}`}
                right={<span className="num quiz__accuracy">{row.accuracy}%</span>}
              />
            ))}
          </Rows>
        </DataCard>
      )}
    </div>
  )
}
