/**
 * Кабинет Асем — поступление (фаза 49).
 *
 * Первым идёт то, что горит: дедлайны этой недели крупной карточкой.
 * Ниже четыре числа, слева очередь целей, стран и вузов и баланс списков,
 * справа — справочник, который она ведёт сама, и формулы статусов,
 * которые школа так и не задала.
 */
import { useNavigate } from 'react-router-dom'
import { useCabinet, usePendingAdditions, useReviewAddition } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import OnboardingQueue from '../../components/OnboardingQueue'
import PendingQueue from '../../components/PendingQueue'
import { Hero, Row, Rows } from '../../components/patterns'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Badge, type BadgeVariant } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { CabinetColumns, CabinetStats } from './cabinet'

interface AdmissionCabinet {
  title: string
  owner: string
  stats: Parameters<typeof CabinetStats>[0]['stats']
  urgent: {
    eyebrow: string
    applying: number
    not_ready: number
    first: { university: string; deadline: string; days: number } | null
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
      note={t('Пока вы не подтвердите, запись остаётся пометкой ученика, а не решением школы.')}
      accent="brand"
      count={rows.length}
    >
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
    </DataCard>
  )
}

export default function AdmissionDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useCabinet()
  const schoolIsEmpty = useSchoolIsEmpty()

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
          а у дедлайна этой недели — нет */}
      <Hero
        tone="brand"
        eyebrow={t(urgent.eyebrow)}
        title={
          urgent.applying > 0
            ? `${urgent.applying} ${t('учеников подают на этой неделе')}`
            : t('На этой неделе дедлайнов нет')
        }
        note={
          urgent.applying > 0
            ? `${t('Заявка не готова у стольких')}: ${urgent.not_ready}.${
                urgent.first
                  ? ` ${t('Первый дедлайн')} — ${urgent.first.university}, ${t('через')} ${urgent.first.days} ${t('дн.')}`
                  : ''
              }`
            : t('Ближайшие сроки видны в разделе «Дедлайны».')
        }
        figure="arcs"
        action={<Button onClick={() => navigate('/deadlines')}>{t('Открыть список')}</Button>}
      />

      <CabinetStats stats={cabinet.stats} />

      <CabinetColumns
        main={
          <>
            <OnboardingQueue />
            <PendingAdditions />
            <PendingQueue note="Цели, специальности, страны и вузы в списках." />

            <DataCard title={t('Баланс списков')} note={t('Кому пересобрать список')} accent="brand">
              <Rows>
                {cabinet.balance.map((row) => (
                  <Row
                    key={row.title}
                    title={t(row.title)}
                    note={`${row.count} ${t('чел.')}`}
                    right={<Badge variant={row.tone as BadgeVariant}>{t(row.chip)}</Badge>}
                  />
                ))}
              </Rows>
            </DataCard>
          </>
        }
        aside={
          <>
            <DataCard title={t('Справочник')} note={t('Что вы ведёте сами')} accent="indigo">
              <Rows>
                <Row
                  title={t('Требования не подтверждены')}
                  note={`${cabinet.directory.unverified_requirements} ${t('программ')}`}
                  right={<Badge variant="warn">{t('Сверить')}</Badge>}
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
                  note={`${cabinet.directory.stale_rounds} ${t('раундов')}`}
                  right={<Badge variant="warn">{t('Сверить')}</Badge>}
                  onOpen={() => navigate('/deadlines')}
                  openLabel={t('Открыть дедлайны')}
                />
              </Rows>
            </DataCard>

            {/* Формулы статусов школа не задала — решение владельца O1.
                Пока их нет, статус ставится руками, и об этом сказано прямо */}
            <DataCard title={t('Статусы A / B / C')} accent="warn">
              <p className="muted rows__empty">
                {t('Формулы школа не задала. Статусы ставятся вручную — при 250 учениках это не удержать.')}
              </p>
              <Button variant="outline" size="sm" onClick={() => navigate('/task-templates')}>
                {t('Задать формулы')}
              </Button>
            </DataCard>
          </>
        }
      />
    </div>
  )
}
