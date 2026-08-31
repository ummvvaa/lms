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
import { useState } from 'react'
import { toast } from 'sonner'
import {
  useAttempts,
  useContacts,
  useMyProfile,
  useMyProposals,
  useMyUniversities,
  usePropose,
  useStudentRows,
  type MyProposal,
} from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { useDomainMeta } from '../api/hooks'
import { profileModelOf, type Domain, type DomainField, type DomainModel } from '../api/types'
import Empty from '../components/Empty'
import { DataCard, ErrorNote, Loading, Metric, MetricRow, ScreenHead, type Accent } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { NativeSelect, NativeSelectOption } from '../components/ui/native-select'
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

/** Цвет полосы над карточкой домена — тот же, которым домен отмечен везде. */
const DOMAIN_ACCENT: Record<string, Accent> = {
  behavior: 'brand',
  admission: 'indigo',
  exam: 'teal',
  talent: 'warn',
  sport: 'ok',
}

const DOMAIN_NOTE: Record<string, string> = {
  behavior: 'Ведёт директор школы',
  admission: 'Ведёт директор по поступлению',
  exam: 'Ведёт академический директор',
  talent: 'Ведёт директор талантов',
  sport: 'Ведёт директор спорта',
}

/** Значения, которые ученик отправил и которые ещё ждут решения директора. */
function pendingByField(proposals: MyProposal[]): Record<string, string> {
  const out: Record<string, string> = {}
  for (const proposal of proposals) {
    if (proposal.status !== 'pending') continue
    for (const change of proposal.changes) {
      // новые записи (олимпиады, соревнования) помечаются в своих списках
      if (change.new_object_key) continue
      out[`${change.model}.${change.field}`] = change.new_value
    }
  }
  return out
}

/**
 * Форма «внести данные» под карточкой домена.
 *
 * Отправляет только изменённые поля. Значение не пишется в профиль:
 * оно уходит предложением владельцу домена, и до решения показывается
 * с пометкой «ждёт проверки» — нейтральной, без «не подтверждено».
 */
function ProposeForm({
  model,
  fields,
  current,
  pending,
}: {
  model: DomainModel
  fields: DomainField[]
  current: Record<string, unknown>
  pending: Record<string, string>
}) {
  const propose = usePropose()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})

  const valueOf = (field: DomainField) =>
    draft[field.name] ?? pending[`${model.label}.${field.name}`] ?? String(current?.[field.name] ?? '')

  const submit = () => {
    const rows = fields
      .filter((f) => draft[f.name] !== undefined && draft[f.name] !== String(current?.[f.name] ?? ''))
      .map((f) => ({ model: model.label, field: f.name, value: draft[f.name] }))
    if (rows.length === 0) {
      setOpen(false)
      return
    }
    propose.mutate(rows, {
      onSuccess: (result) => {
        if (result.accepted > 0) toast.success(t('Отправлено на проверку'))
        result.rejected.forEach((row) => toast.error(row.reason))
        setDraft({})
        setOpen(false)
      },
    })
  }

  if (!open) {
    return (
      <div className="propose__toggle">
        <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
          {t('Внести данные')}
        </Button>
      </div>
    )
  }

  return (
    <div className="propose__form">
      <p className="muted propose__note">
        {t('Значение проверит директор — до этого оно помечено как «ждёт проверки».')}
      </p>
      {fields.map((field) => (
        <label key={field.name} className="propose__field">
          <span className="muted propose__label">{t(field.title)}</span>
          {field.choices ? (
            <NativeSelect
              size="sm"
              value={valueOf(field)}
              onChange={(e) => setDraft((prev) => ({ ...prev, [field.name]: e.target.value }))}
            >
              <NativeSelectOption value="">—</NativeSelectOption>
              {field.choices.map((choice) => (
                <NativeSelectOption key={choice.value} value={choice.value}>
                  {choice.title}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          ) : (
            <Input
              value={valueOf(field)}
              placeholder={field.range_hint}
              onChange={(e) => setDraft((prev) => ({ ...prev, [field.name]: e.target.value }))}
            />
          )}
        </label>
      ))}
      <div className="propose__actions">
        <Button size="sm" disabled={propose.isPending} onClick={submit}>
          {t('Отправить на проверку')}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
          {t('Отмена')}
        </Button>
      </div>
    </div>
  )
}

export default function MyData() {
  const { me } = useAuth()
  const meta = useDomainMeta()
  const profile = useMyProfile()
  const attempts = useAttempts()
  const universities = useMyUniversities()
  const rows = useStudentRows(me?.student_id ?? null)
  const contacts = useContacts({ student: me?.student_id ?? null })
  const proposals = useMyProposals()

  if (meta.isLoading || profile.isLoading) return <Loading kind="cards" />
  if (profile.error) return <ErrorNote error={profile.error} />
  if (!profile.data) return null

  const card = profile.data as unknown as Record<string, Record<string, unknown>>
  const domains: Domain[] = meta.data?.domains ?? []
  const attemptRows = attempts.data?.results ?? []
  const activities = rows.data?.activities ?? []
  const competitions = rows.data?.competitions ?? []
  const contactRows = contacts.data?.results ?? []
  const myProposals = proposals.data?.results ?? []
  const pending = pendingByField(myProposals)
  const declined = myProposals.filter((p) => p.status === 'rejected' && p.reject_reason)

  return (
    <div>
      <ScreenHead
        title={t('Мои данные')}
        subtitle={t('Всё, что школа записала про вас — и что вы внесли сами.')}
      />

      {declined.length > 0 && (
        <div className="card card-pad card--accent card--warn propose__declined">
          <span className="eyebrow">{t('Возвращено на доработку')}</span>
          <ul className="propose__declinedlist">
            {declined.slice(0, 5).map((proposal) => (
              <li key={proposal.id}>
                <b>{proposal.changes.map((c) => t(c.field_title)).join(', ')}</b>
                <span className="muted"> — {proposal.reject_reason}. </span>
                <span className="muted">{t('Поправьте и внесите заново в карточке ниже.')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid--two">
        {domains.map((domain) => {
          const model = profileModelOf(domain)
          if (!model) return null
          const values = card[domain.code]
          const proposable = model.fields.filter((f) => f.student_proposable)
          return (
            <DataCard
              key={domain.code}
              title={t(DOMAIN_TITLE[domain.code] ?? domain.title)}
              note={t(DOMAIN_NOTE[domain.code] ?? '')}
              accent={DOMAIN_ACCENT[domain.code]}
            >
              <MetricRow>
                {model.fields.map((field) => {
                  const waiting = pending[`${model.label}.${field.name}`]
                  const choice = field.choices?.find((c) => c.value === waiting)
                  return (
                    <div key={field.name} className="propose__cell">
                      <Metric
                        value={waiting !== undefined ? choice?.title || waiting : shown(values, field)}
                        label={field.short || field.title}
                      />
                      {waiting !== undefined && <Badge variant="mute">{t('ждёт проверки')}</Badge>}
                    </div>
                  )
                })}
              </MetricRow>
              {proposable.length > 0 && (
                <ProposeForm model={model} fields={proposable} current={values} pending={pending} />
              )}
            </DataCard>
          )
        })}

        <DataCard
          title={t('Сданные экзамены и пробные')}
          note={t('Каждая попытка с датой и баллом')}
          count={attemptRows.length}
          accent="teal"
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
          accent="indigo"
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
          accent="warn"
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
          accent="ok"
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
          accent="brand"
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
          icon="person"
          title={t('Данных пока нет')}
          what={t('Здесь появится всё, что о вас записала школа.')}
          action={t('Заполнить анкету')}
          to="/onboarding"
        />
      )}
    </div>
  )
}
