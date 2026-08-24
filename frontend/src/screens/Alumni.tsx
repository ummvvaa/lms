/**
 * Каталог выпускников и менторство.
 *
 * Запрос ученика уходит не выпускнику, а в школу: сотрудник решает,
 * передавать ли его дальше. Ученику это видно прямо в интерфейсе,
 * чтобы он не ждал ответа, которого не будет.
 */
import { useState } from 'react'
import {
  useAlumni,
  useArchivedEssays,
  useMentorships,
  useRequestMentorship,
  useReviewMentorship,
  type Alumnus,
} from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import Empty from '../components/Empty'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'

const OUTCOME_TITLE: Record<string, string> = {
  admitted: 'поступил',
  enrolled: 'учится',
  rejected: 'отказ',
  waitlist: 'лист ожидания',
  withdrawn: 'отозвал',
}

const STATUS_TITLE: Record<string, string> = {
  requested: 'ждёт решения школы',
  approved: 'одобрено школой',
  declined: 'отклонено школой',
  sent: 'передано выпускнику',
  accepted: 'выпускник согласился',
  refused: 'выпускник отказался',
  completed: 'завершено',
}

function AskForm({ alumnus, onDone }: { alumnus: Alumnus; onDone: () => void }) {
  const [topic, setTopic] = useState('')
  const ask = useRequestMentorship()

  return (
    <form
      className="alumni__ask"
      onSubmit={(e) => {
        e.preventDefault()
        ask.mutate({ alumnus: alumnus.id, topic }, { onSuccess: onDone })
      }}
    >
      <input
        className="input"
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
        placeholder={t('О чём хотите спросить?')}
        required
      />
      <button className="btn btn-primary btn-sm" type="submit" disabled={ask.isPending}>
        {t('Отправить в школу')}
      </button>
      <p className="muted alumni__note">
        {t('Запрос сначала посмотрит сотрудник школы и только потом передаст выпускнику.')}
      </p>
    </form>
  )
}

export default function Alumni() {
  const { me } = useAuth()
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [asking, setAsking] = useState<number | null>(null)
  const [sent, setSent] = useState(false)
  const alumni = useAlumni(filters)
  const essays = useArchivedEssays()
  const mentorships = useMentorships()
  const { approve, decline } = useReviewMentorship()

  const isStaff = me?.role !== 'student'
  const pending = (mentorships.data?.results ?? []).filter((r) => r.status === 'requested')

  if (alumni.isLoading) return <Loading />
  if (alumni.error) return <ErrorNote error={alumni.error} />

  const rows = alumni.data?.results ?? []
  const countries = [...new Set(rows.map((a) => a.country).filter(Boolean))].sort()

  return (
    <div>
      <ScreenHead
        title={t('Выпускники')}
        subtitle={t('Куда поступили, с какими баллами и кто готов помочь советом.')}
      />

      {isStaff && pending.length > 0 && (
        <div className="card card-pad alumni__queue">
          <span className="eyebrow">{t('Запросы на менторство')}</span>
          <p className="muted alumni__note">{t('Пока вы не одобрите, выпускник запроса не увидит.')}</p>
          {pending.map((row) => (
            <div key={row.id} className="alumni__queue-row">
              <div>
                <b>{row.student_name}</b> → {row.alumnus_name}
                <p className="muted alumni__note">{row.topic}</p>
              </div>
              <div className="alumni__queue-actions">
                <button className="btn btn-primary btn-sm" onClick={() => approve.mutate({ id: row.id })}>
                  {t('Передать выпускнику')}
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => decline.mutate({ id: row.id })}>
                  {t('Отклонить')}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {!isStaff && mentorships.data && mentorships.data.results.length > 0 && (
        <div className="card card-pad" style={{ marginBottom: 16 }}>
          <span className="eyebrow">{t('Ваши запросы')}</span>
          {mentorships.data.results.map((row) => (
            <div key={row.id} className="row-between alumni__mine">
              <span>
                <b>{row.alumnus_name}</b> — {row.topic}
              </span>
              <span className="chip chip-mute">{STATUS_TITLE[row.status] ?? row.status}</span>
            </div>
          ))}
        </div>
      )}

      <div className="toolbar">
        <select
          className="input"
          value={filters.country ?? ''}
          onChange={(e) => setFilters({ ...filters, country: e.target.value })}
        >
          <option value="">{t('Все страны')}</option>
          {countries.map((country) => (
            <option key={country} value={country}>
              {country}
            </option>
          ))}
        </select>
        <input
          className="input"
          placeholder={t('Год выпуска')}
          value={filters.year ?? ''}
          onChange={(e) => setFilters({ ...filters, year: e.target.value })}
        />
        <label className="alumni__check">
          <input
            type="checkbox"
            checked={filters.mentors_only === 'true'}
            onChange={(e) => setFilters({ ...filters, mentors_only: e.target.checked ? 'true' : '' })}
          />
          {t('готовы быть менторами')}
        </label>
        <span className="chip chip-mute num">{rows.length}</span>
      </div>

      {sent && <p className="chip chip-ok">{t('Запрос отправлен в школу')}</p>}

      <div className="grid grid--cards">
        {rows.map((alumnus) => (
          <article key={alumnus.id} className="card card-pad">
            <div className="row-between">
              <div>
                <b style={{ fontSize: 15 }}>{alumnus.full_name}</b>
                <p className="muted alumni__note">выпуск {alumnus.graduation_year}</p>
              </div>
              {alumnus.mentorship_consent && <span className="chip chip-ok">{t('ментор')}</span>}
            </div>

            <p className="alumni__uni">
              {alumnus.university_name ?? 'вуз не указан'}
              {alumnus.program_name && <span className="muted"> · {alumnus.program_name}</span>}
            </p>
            {alumnus.current_occupation && <p className="muted alumni__note">{alumnus.current_occupation}</p>}

            <div className="alumni__scores num">
              {alumnus.admission_ielts && (
                <span className="chip chip-mute">IELTS {alumnus.admission_ielts}</span>
              )}
              {alumnus.admission_sat && <span className="chip chip-mute">SAT {alumnus.admission_sat}</span>}
              {alumnus.admission_gpa && <span className="chip chip-mute">GPA {alumnus.admission_gpa}</span>}
            </div>

            {alumnus.applications.length > 0 && (
              <ul className="alumni__apps">
                {alumnus.applications.map((app) => (
                  <li key={app.id}>
                    {app.university_name} —{' '}
                    <span className="muted">{OUTCOME_TITLE[app.outcome] ?? app.outcome}</span>
                  </li>
                ))}
              </ul>
            )}

            {!isStaff && alumnus.mentorship_consent && (
              <>
                {asking === alumnus.id ? (
                  <AskForm
                    alumnus={alumnus}
                    onDone={() => {
                      setAsking(null)
                      setSent(true)
                    }}
                  />
                ) : (
                  <button
                    className="btn btn-ghost btn-sm alumni__askbtn"
                    onClick={() => setAsking(alumnus.id)}
                  >
                    {t('Попросить о менторстве')}
                  </button>
                )}
              </>
            )}
          </article>
        ))}
        {rows.length === 0 && (
          <Empty
            title={t('Выпускников пока нет')}
            what={t(
              'Здесь появятся те, кто уже поступил: куда, с какими баллами и что писал в эссе. У них можно попросить менторства — школа сама решает, кого к кому направить.',
            )}
          />
        )}
      </div>

      <h2 className="section">{t('Архив эссе')}</h2>
      <p className="muted alumni__note">
        {t('Публикуются только с согласия автора, с указанием, куда человек поступил.')}
      </p>
      <div className="grid grid--cards">
        {(essays.data?.results ?? []).map((essay) => (
          <article key={essay.id} className="card card-pad">
            <b>{essay.title}</b>
            <p className="muted alumni__note">
              {essay.author_label} · {essay.university_name}
            </p>
            <p className="alumni__excerpt">{essay.text.slice(0, 220)}…</p>
          </article>
        ))}
        {essays.data?.results.length === 0 && <p className="muted">{t('Архив пока пуст.')}</p>}
      </div>
    </div>
  )
}
