/**
 * Кабинет Асем — поступление (фаза 49).
 *
 * Первым идёт то, что горит: дедлайны этой недели крупной карточкой.
 * Ниже четыре числа, слева очередь целей, стран и вузов и баланс списков,
 * справа — справочник, который она ведёт сама, и формулы статусов,
 * которые школа так и не задала.
 */
import { useNavigate } from 'react-router-dom'
import {
  useCabinet,
  usePendingAdditions,
  usePendingOnboarding,
  useReviewAddition,
  useStudentQueue,
} from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import OnboardingQueue from '../../components/OnboardingQueue'
import PendingQueue from '../../components/PendingQueue'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { counted, t, tk, tn } from '../../i18n'
import { CabinetBoard, CabinetStats } from './cabinet'

interface AdmissionCabinet {
  title: string
  owner: string
  stats: Parameters<typeof CabinetStats>[0]['stats']
  urgent: {
    eyebrow: string
    applying: number
    not_ready: number
    first: { university: string; deadline: string; days: number } | null
    /** дедлайны ближайших `window_days` дней с подающими: без них героя нет */
    window_days: number
    rounds: number
    applicants: number
    nearest: { university: string; deadline: string; days: number } | null
  }
  balance: { title: string; count: number; tone: string; chip: string }[]
  directory: {
    unverified_requirements: number
    universities: number
    scholarships: number
    stale_rounds: number
  }
}

/**
 * Что ученики добавили себе в список сами — до подтверждения.
 *
 * Третья очередь на этом экране и по смыслу отдельная: здесь решается
 * не значение поля, а сама строка «подаюсь сюда». Пока она не
 * подтверждена, это пометка ученика, а не решение школы.
 */
function PendingAdditions() {
  const pending = usePendingAdditions()
  const review = useReviewAddition()
  const rows = pending.data ?? []
  if (rows.length === 0) return null

  return (
    <DataCard
      title={t('Ученики добавили себе')}
      count={rows.length}
    >
      <ShowAll>
        {rows.map((row) => (
          <div key={row.id} className="cabinet__row">
            <span className="cabinet__rowtext">
              <b>{row.student_name}</b>
              <span className="muted">
                {row.university_name} · {row.program_name} ({row.tier})
              </span>
            </span>
            <Button
              size="sm"
              disabled={review.isPending}
              onClick={() => review.mutate({ id: row.id, decision: 'confirm' })}
            >
              {t('Подтвердить')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={review.isPending}
              onClick={() => review.mutate({ id: row.id, decision: 'decline' })}
            >
              {t('Снять')}
            </Button>
          </div>
        ))}
      </ShowAll>
    </DataCard>
  )
}

export default function AdmissionDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useCabinet()
  const schoolIsEmpty = useSchoolIsEmpty()
  // те же запросы, что у самих очередей: раскладке нужно знать, пусты ли они
  const students = useStudentQueue()
  const answers = usePendingOnboarding()
  const added = usePendingAdditions()

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Поступление')}
        hint={t('Здесь появятся сроки и списки вузов')}
        what={t('Дедлайны берутся из раундов справочника, списки собирают ученики.')}
        detail={t('Начните со справочника вузов и программ.')}
        guide
      />
    )

  const cabinet = data as unknown as AdmissionCabinet
  const urgent = cabinet.urgent
  const queue = students.data?.results.length ?? 0
  const onboarding = answers.data?.length ?? 0
  const additions = added.data?.length ?? 0
  const listed = cabinet.balance.reduce((sum, row) => sum + row.count, 0)

  return (
    <div>
      <ScreenHead
        title={t(cabinet.title)}
        subtitle={t(cabinet.owner)}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate('/directory')}>
              {t('Справочник вузов')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => navigate('/scholarship-directory')}>
              {t('Стипендии')}
            </Button>
            <Button size="sm" onClick={() => navigate('/deadlines')}>
              {t('Дедлайны')}
            </Button>
          </>
        }
      />

      <GettingStarted />

      {/* То, что горит, стоит первым и на цвете: у остального есть завтра,
          а у дедлайна этой недели — нет. Дедлайнов в ближайшие 30 дней нет —
          нет и героя: пустой оранжевый блок «дедлайнов нет» занимал пол-экрана
          и ничего не сообщал; первым встаёт ряд чисел (фаза 80) */}
      {urgent.rounds > 0 && (
        <DataCard
          title={urgent.applying > 0 ? t(urgent.eyebrow) : t('Дедлайны в ближайшие 30 дней')}
          right={
            <Button size="sm" onClick={() => navigate('/deadlines')}>
              {t('Открыть список')}
            </Button>
          }
        >
          <Rows>
            <Row
              icon="clock"
              tone="accent"
              title={
                urgent.applying > 0
                  ? tn(urgent.applying, '{n} ученик подаёт на этой неделе|{n} ученика подают на этой неделе|{n} учеников подают на этой неделе')
                  : t('Ближайший дедлайн — {university}, через {days} дн.', { university: urgent.nearest?.university ?? '', days: urgent.nearest?.days ?? 0 })
              }
              note={
                urgent.applying > 0
                  ? `${t('Заявка не готова: {n}.', { n: urgent.not_ready })}${
                      urgent.first ? ` ${t('Первый дедлайн — {university}, через {days} дн.', { university: urgent.first.university, days: urgent.first.days })}` : ''
                    }`
                  : t('Раундов с подающими: {rounds} · подают: {applicants}', { rounds: urgent.rounds, applicants: urgent.applicants })
              }
            />
          </Rows>
        </DataCard>
      )}

      <CabinetStats stats={cabinet.stats} />

      <CabinetBoard
        cards={[
          additions > 0 && {
            key: 'additions',
            column: 'main',
            rows: additions * 2,
            node: <PendingAdditions />,
          },
          {
            key: 'queue',
            column: 'main',
            // строка очереди вдвое выше строки списка: в ней значения и кнопки
            rows: queue * 2,
            folded: queue === 0,
            node: <PendingQueue note={tk('Цели, специальности, страны и вузы в списках.')} fold />,
          },
          {
            key: 'directory',
            column: 'aside',
            rows: 4,
            node: (
              <DataCard title={t('Справочник')}>
                <Rows>
                  <Row
                    title={t('Требования не подтверждены')}
                    note={counted(cabinet.directory.unverified_requirements, 'программа|программы|программ')}
                    right={<Chip tone="warn">{t('Сверить')}</Chip>}
                    onOpen={() => navigate('/directory')}
                    openLabel={t('Открыть справочник')}
                  />
                  <Row
                    title={t('Вузов в каталоге')}
                    note={String(cabinet.directory.universities)}
                    onOpen={() => navigate('/directory')}
                    openLabel={t('Открыть справочник')}
                  />
                  <Row
                    title={t('Стипендий')}
                    note={String(cabinet.directory.scholarships)}
                    onOpen={() => navigate('/scholarship-directory')}
                    openLabel={t('Открыть стипендии')}
                  />
                  <Row
                    title={t('Дедлайн не проверялся месяц')}
                    note={counted(cabinet.directory.stale_rounds, 'раунд|раунда|раундов')}
                    right={<Chip tone="warn">{t('Сверить')}</Chip>}
                    onOpen={() => navigate('/deadlines')}
                    openLabel={t('Открыть дедлайны')}
                  />
                </Rows>
              </DataCard>
            ),
          },
          // анкета первого входа — ниже очереди и отдельно: она уже в профиле
          // и решения не ждёт (D16)
          onboarding > 0 && {
            key: 'onboarding',
            column: 'main',
            rows: onboarding * 2,
            node: <OnboardingQueue />,
          },
          {
            key: 'balance',
            column: 'main',
            rows: cabinet.balance.length,
            folded: listed === 0,
            narrow: true,
            node: (
              <DataCard
                title={t('Баланс списков')}
                empty={listed === 0 && t('списков вузов пока нет')}
              >
                <Rows>
                  {cabinet.balance.map((row) => (
                    <Row
                      key={row.title}
                      title={t(row.title)}
                      note={tn(row.count, '{n} чел.|{n} чел.|{n} чел.')}
                      right={<Chip tone={row.tone as Tone}>{t(row.chip)}</Chip>}
                    />
                  ))}
                </Rows>
              </DataCard>
            ),
          },
          {
            key: 'statuses',
            column: 'aside',
            rows: 2,
            node: (
              // Формулы статусов школа не задала — решение владельца O1.
              // Пока их нет, статус ставится руками, и об этом сказано прямо
              <DataCard title={t('Статусы A / B / C')}>
                <p className="muted rows__empty">
                  {t('Формулы школа не задала. Статусы ставятся вручную — при 250 учениках это не удержать.')}
                </p>
                <Button variant="outline" size="sm" onClick={() => navigate('/task-templates')}>
                  {t('Задать формулы')}
                </Button>
              </DataCard>
            ),
          },
        ]}
      />
    </div>
  )
}
