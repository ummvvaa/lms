/**
 * «Мои данные» — что школа записала про ученика.
 *
 * Ученик видит про себя всё: баллы текущие и целевые, посещаемость,
 * выполнение заданий, портфолио, спорт, попытки экзаменов, вузы,
 * активности, соревнования и контакты родителей.
 *
 * Не видит он ровно три оценочные метки — статус по дисциплине, статус
 * по поступлению и статус портфолио. Экран не решает это сам: карточки
 * собираются из `/api/meta/domains/`, а оттуда ярлыки роли `student`
 * не приходят вовсе (инвариант №7). Спрятать данные «на всякий случай»
 * тут поэтому нечем — и добавить ярлык обратно тоже.
 */
import { useAttempts, useContacts, useMyProfile, useMyUniversities, useStudentRows } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { useDomainMeta } from '../api/hooks'
import { profileModelOf, type Domain, type DomainField } from '../api/types'
import Empty from '../components/Empty'
import { DataCard, ErrorNote, Loading, Metric, MetricRow, ScreenHead } from '../components/ui'
import { t } from '../i18n'

/** Что видно в карточке: значение с подписью поля. */
function shown(profile: Record<string, unknown> | undefined, field: DomainField): string {
  if (field.type === 'reference') return String(profile?.[`${field.name}_name`] || '—')
  const value = profile?.[field.name]
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'да' : 'нет'
  const choice = field.choices?.find((c) => c.value === value)
  return choice ? choice.title : String(value)
}

/** Подписи карточек: заголовок отвечает на вопрос «что это за данные». */
const DOMAIN_TITLE: Record<string, string> = {
  behavior: 'Учёба и посещаемость',
  admission: 'Куда вы поступаете',
  exam: 'Ваши баллы',
  talent: 'Портфолио и таланты',
  sport: 'Спорт',
}

const DOMAIN_NOTE: Record<string, string> = {
  behavior: 'Ведёт директор школы',
  admission: 'Ведёт директор по поступлению',
  exam: 'Ведёт академический директор',
  talent: 'Ведёт директор талантов',
  sport: 'Ведёт директор спорта',
}

export default function MyData() {
  const { me } = useAuth()
  const meta = useDomainMeta()
  const profile = useMyProfile()
  const attempts = useAttempts()
  const universities = useMyUniversities()
  const rows = useStudentRows(me?.student_id ?? null)
  const contacts = useContacts({ student: me?.student_id ?? null })

  if (meta.isLoading || profile.isLoading) return <Loading />
  if (profile.error) return <ErrorNote error={profile.error} />
  if (!profile.data) return null

  const card = profile.data as unknown as Record<string, Record<string, unknown>>
  const domains: Domain[] = meta.data?.domains ?? []
  const attemptRows = attempts.data?.results ?? []
  const activities = rows.data?.activities ?? []
  const competitions = rows.data?.competitions ?? []
  const contactRows = contacts.data?.results ?? []

  return (
    <div>
      <ScreenHead title={t('Мои данные')} subtitle={t('Всё, что школа записала про вас.')} />

      <div className="grid grid--two">
        {domains.map((domain) => {
          const model = profileModelOf(domain)
          if (!model) return null
          const values = card[domain.code]
          return (
            <DataCard
              key={domain.code}
              title={t(DOMAIN_TITLE[domain.code] ?? domain.title)}
              note={t(DOMAIN_NOTE[domain.code] ?? '')}
            >
              <MetricRow>
                {model.fields.map((field) => (
                  <Metric key={field.name} value={shown(values, field)} label={field.short || field.title} />
                ))}
              </MetricRow>
            </DataCard>
          )
        })}

        <DataCard
          title={t('Сданные экзамены и пробные')}
          note={t('Каждая попытка с датой и баллом')}
          count={attemptRows.length}
        >
          {attemptRows.length === 0 && (
            <p className="muted rows__empty">{t('Попыток пока нет — они появятся после первой сдачи')}</p>
          )}
          <ul className="rows__list">
            {attemptRows.slice(0, 10).map((row) => (
              <li key={row.id} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">
                    {row.exam_type} {row.total_score ?? '—'}
                  </span>
                  <span className="muted rows__note">
                    {new Date(row.date).toLocaleDateString('ru')} ·{' '}
                    {row.attempt_format === 'mock' ? 'пробный' : 'официальный'}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </DataCard>

        <DataCard
          title={t('Вузы в вашем списке')}
          note={t('И насколько вы подходите по требованиям')}
          count={universities.data?.length ?? 0}
        >
          {(universities.data?.length ?? 0) === 0 && (
            <p className="muted rows__empty">{t('Список пуст — выберите программы в каталоге')}</p>
          )}
          <ul className="rows__list">
            {(universities.data ?? []).slice(0, 10).map((row) => (
              <li key={row.program} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">{row.university_name}</span>
                  <span className="muted rows__note">{row.program_name}</span>
                </div>
              </li>
            ))}
          </ul>
        </DataCard>

        <DataCard
          title={t('Активности портфолио')}
          note={t('Олимпиады, проекты, волонтёрство')}
          count={activities.length}
        >
          {activities.length === 0 && <p className="muted rows__empty">{t('Активностей пока нет')}</p>}
          <ul className="rows__list">
            {activities.slice(0, 10).map((row) => (
              <li key={row.id} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">{row.title}</span>
                  <span className="muted rows__note">
                    {row.is_confirmed ? t('подтверждена') : t('ждёт подтверждения')}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </DataCard>

        <DataCard
          title={t('Спортивные соревнования')}
          note={t('Выступления и результаты')}
          count={competitions.length}
        >
          {competitions.length === 0 && <p className="muted rows__empty">{t('Соревнований пока нет')}</p>}
          <ul className="rows__list">
            {competitions.slice(0, 10).map((row) => (
              <li key={row.id} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">{row.name}</span>
                  <span className="muted rows__note">{row.result || '—'}</span>
                </div>
              </li>
            ))}
          </ul>
        </DataCard>

        <DataCard
          title={t('Контакты родителей')}
          note={t('Кого школа набирает по вашим вопросам')}
          count={contactRows.length}
        >
          {contactRows.length === 0 && <p className="muted rows__empty">{t('Контактов пока не записано')}</p>}
          <ul className="rows__list">
            {contactRows.map((row) => (
              <li key={row.id} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">
                    {row.full_name}
                    {row.is_primary ? ` · ${t('основной')}` : ''}
                  </span>
                  <span className="muted rows__note">
                    {[row.relation_title, row.phone].filter(Boolean).join(' · ')}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </DataCard>
      </div>

      {domains.length === 0 && (
        <Empty
          title={t('Данных пока нет')}
          what={t('Здесь появится всё, что о вас записала школа.')}
          action={t('Заполнить анкету')}
          to="/onboarding"
        />
      )}
    </div>
  )
}
