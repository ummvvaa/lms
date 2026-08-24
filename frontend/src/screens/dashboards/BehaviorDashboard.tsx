/** Салтанат: заполненность профилей, светофор, риски по посещаемости. */
import { useDashboard } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import SectionLink from '../../components/SectionLink'
import { Donut, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import type { BehaviorData } from '../sections/data'

export default function BehaviorDashboard() {
  const { data, isLoading, error } = useDashboard<BehaviorData>('behavior')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Профиль и дисциплина')}
        hint={t('Здесь появится светофор по школе')}
        what={t(
          'Дашборд собирается из профилей учеников: заполненность, посещаемость, домашние работы. Начните с загрузки своего файла — того же, который вы ведёте сейчас.',
        )}
        guide
      />
    )

  const traffic = data.traffic
  const ok = traffic.can_execute ?? 0
  const warn = traffic.needs_supervision ?? 0
  const risk = traffic.critical ?? 0

  return (
    <div>
      <ScreenHead
        title={t('Профиль и дисциплина')}
        subtitle={`Цель дня: ${data.total} из ${data.total} учеников с базовым профилем.`}
      />

      <GettingStarted />

      <div className="grid grid--kpi">
        <Kpi
          value={`${data.filled} / ${data.total}`}
          label={t('Профили заполнены')}
          note={`${data.total - data.filled} осталось собрать`}
          color="var(--brand)"
        />
        <Kpi value={ok} label={t('Работают самостоятельно')} color="var(--ok)" />
        <Kpi value={warn} label={t('Нужен контроль')} color="var(--warn)" />
        <Kpi value={risk} label={t('Ежедневный контроль')} color="var(--risk)" />
      </div>

      <div className="split">
        <div className="card card-pad">
          <span className="eyebrow">{t('Светофор по школе')}</span>
          <div className="row-between" style={{ marginTop: 16 }}>
            <Donut
              segments={[
                { value: ok, color: 'var(--ok)' },
                { value: warn, color: 'var(--warn)' },
                { value: risk, color: 'var(--risk)' },
              ]}
            />
            <div className="legend">
              {[
                ['Работают самостоятельно', 'var(--ok)', ok],
                ['Нужен контроль', 'var(--warn)', warn],
                ['Ежедневный контроль', 'var(--risk)', risk],
              ].map(([label, color, value]) => (
                <div key={String(label)} className="legend__row">
                  <span className="legend__dot" style={{ background: String(color) }} />
                  <span className="muted">{label}</span>
                  <b className="num legend__value">{value}</b>
                </div>
              ))}
            </div>
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginTop: 18 }}>
            {t('Эти ярлыки видны только сотрудникам. У ученика на экране — задачи и процент готовности.')}
          </p>
        </div>

        <div className="grid">
          <SectionLink
            title={t('Риски')}
            value={risk + warn}
            note={t('кому нужен контроль прямо сейчас')}
            to="/risks"
          />
          <SectionLink
            title={t('Группы')}
            value={data.groups.length}
            note={t('заполненность профилей по группам')}
            to="/groups"
          />
        </div>
      </div>
    </div>
  )
}
