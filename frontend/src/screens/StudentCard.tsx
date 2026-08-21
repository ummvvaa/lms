/**
 * Карточка ученика: пять доменов на одной странице.
 * Свой домен редактируется, чужие показаны с подписью «ведёт: <имя>».
 */
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  useBatchSave,
  useDomainMeta,
  useStudent,
  useStudentHistory,
  type StudentCard as Card,
} from '../api/hooks'
import type { Domain, DomainField } from '../api/types'
import { ErrorNote, Loading, Ring } from '../components/ui'
import './card.css'

const SOURCE_TITLES: Record<string, string> = {
  manual: 'руками',
  import: 'импорт',
  ai: 'ИИ',
  sync: 'сверка',
}

function shown(student: Card, domain: Domain, field: DomainField): string {
  const profile = (student as unknown as Record<string, Record<string, unknown>>)[domain.code]
  const raw = profile?.[field.name]
  if (raw === null || raw === undefined || raw === '') return '—'
  if (typeof raw === 'boolean') return raw ? 'да' : 'нет'
  const choice = field.choices?.find((c) => c.value === raw)
  return choice ? choice.title : String(raw)
}

export default function StudentCardScreen() {
  const { id } = useParams()
  const navigate = useNavigate()
  const studentId = Number(id)
  const meta = useDomainMeta()
  const student = useStudent(Number.isFinite(studentId) ? studentId : null)
  const history = useStudentHistory(Number.isFinite(studentId) ? studentId : null)
  const batch = useBatchSave()

  const [tab, setTab] = useState<'domains' | 'history'>('domains')
  const [edits, setEdits] = useState<Record<string, string>>({})

  const domains = useMemo(() => meta.data?.domains ?? [], [meta.data])
  const mine = domains.find((d) => d.is_mine)

  if (student.isLoading || meta.isLoading) return <Loading />
  if (student.error) return <ErrorNote error={student.error} />
  if (!student.data) return null

  const card = student.data
  const readiness = card.readiness

  async function save() {
    if (!mine) return
    const model = mine.models[0]
    const changes = Object.entries(edits).map(([field, value]) => ({
      student: studentId,
      model: model.label,
      field,
      value: value.trim() === '' ? null : value.trim(),
    }))
    await batch.mutateAsync(changes)
    setEdits({})
    void student.refetch()
    void history.refetch()
  }

  return (
    <div>
      <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)}>
        ← Назад
      </button>

      <div className="card card-pad card__hero">
        <div className="card__who">
          <h1 className="card__name">{card.full_name}</h1>
          <p className="muted card__meta">
            {card.grade} класс · группа {card.group_code ?? '—'} · {card.email}
          </p>
        </div>
        {readiness && (
          <Ring percent={readiness.score} size={84}>
            <div>
              <div className="num card__score">{readiness.score}%</div>
              <div className="card__scorelabel">готовность</div>
            </div>
          </Ring>
        )}
      </div>

      <div className="tabs">
        <button className={`tab${tab === 'domains' ? ' tab--active' : ''}`} onClick={() => setTab('domains')}>
          Пять доменов
        </button>
        <button className={`tab${tab === 'history' ? ' tab--active' : ''}`} onClick={() => setTab('history')}>
          История изменений
        </button>
        {Object.keys(edits).length > 0 && (
          <>
            <span className="chip chip-warn num">Не сохранено: {Object.keys(edits).length}</span>
            <button className="btn btn-primary btn-sm" onClick={() => void save()} disabled={batch.isPending}>
              Сохранить
            </button>
          </>
        )}
      </div>

      {tab === 'domains' && (
        <div className="grid grid--two">
          {domains.map((domain) => {
            const model = domain.models[0]
            const editable = domain.is_mine
            return (
              <section key={domain.code} className={`card card-pad domain${editable ? ' domain--mine' : ''}`}>
                <div className="domain__head">
                  <span className="eyebrow">
                    {domain.emoji} {domain.title}
                  </span>
                  <span className={`chip ${editable ? 'chip-brand' : 'chip-mute'}`}>
                    {editable ? 'вы редактируете' : `ведёт: ${domain.owner_name}`}
                  </span>
                </div>
                <dl className="domain__fields">
                  {model.fields.map((field) => (
                    <div key={field.name} className="domain__row">
                      <dt className="muted">{field.title}</dt>
                      <dd>
                        {editable ? (
                          <input
                            className="cell num domain__input"
                            value={
                              edits[field.name] ??
                              (shown(card, domain, field) === '—' ? '' : shown(card, domain, field))
                            }
                            onChange={(e) => setEdits((prev) => ({ ...prev, [field.name]: e.target.value }))}
                          />
                        ) : (
                          <span className="num domain__value">{shown(card, domain, field)}</span>
                        )}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            )
          })}
        </div>
      )}

      {tab === 'history' && (
        <div className="card card-pad">
          {history.isLoading && <Loading />}
          {history.data?.length === 0 && <p className="muted">Изменений пока не было.</p>}
          <table className="history">
            <tbody>
              {history.data?.map((entry) => (
                <tr key={entry.id}>
                  <td className="muted history__when">{new Date(entry.created_at).toLocaleString('ru')}</td>
                  <td className="history__field">{entry.field_name}</td>
                  <td className="num history__change">
                    <span className="muted">{entry.old_value || '—'}</span> → <b>{entry.new_value || '—'}</b>
                  </td>
                  <td>
                    <span className="chip chip-mute">{SOURCE_TITLES[entry.source] ?? entry.source}</span>
                  </td>
                  <td className="muted history__actor">{entry.actor_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
