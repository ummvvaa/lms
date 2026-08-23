/**
 * Программы одного вуза: требования, дедлайны раундов и их удаление.
 *
 * Всё это справочник без истории — удаляется физически (инвариант №13).
 * Если программу держат списки учеников, сервер отказывает текстом,
 * а не ошибкой.
 */
import { useProgramsOf } from '../api/hooks'
import DeleteButton from './DeleteButton'
import { Chip, ErrorNote, Loading } from './ui'

const INVALIDATE = [['programs'], ['universities'], ['catalog']]

export default function ProgramList({ universityId, canEdit }: { universityId: number; canEdit: boolean }) {
  const list = useProgramsOf(universityId)

  if (list.isLoading) return <Loading />
  if (list.isError) return <ErrorNote error={list.error} />
  const rows = list.data?.results ?? []

  if (rows.length === 0) {
    return <p className="muted rows__empty">У этого вуза пока нет ни одной программы.</p>
  }

  return (
    <div className="prog">
      {rows.map((program) => (
        <div key={program.id} className="prog__row">
          <div className="row-between prog__head">
            <div>
              <b className="prog__name">{program.name}</b>
              {!program.is_verified && <Chip tone="warn">не подтверждено</Chip>}
            </div>
            {canEdit && (
              <DeleteButton
                model="universities.Program"
                id={program.id}
                path="/programs/"
                invalidate={INVALIDATE}
                label="Удалить программу"
              />
            )}
          </div>

          <div className="prog__parts">
            <div className="prog__part">
              <span className="muted">Требования</span>
              {program.requirement ? (
                <>
                  <span className="num">
                    GPA {program.requirement.min_gpa ?? '—'} · IELTS {program.requirement.min_ielts ?? '—'}
                  </span>
                  {canEdit && (
                    <DeleteButton
                      model="universities.AdmissionRequirement"
                      id={program.requirement.id}
                      path="/requirements/"
                      invalidate={INVALIDATE}
                      label="Убрать требования"
                    />
                  )}
                </>
              ) : (
                <span className="muted">не заведены</span>
              )}
            </div>

            <div className="prog__part">
              <span className="muted">Раунды</span>
              {program.rounds.length === 0 && <span className="muted">не заведены</span>}
              {program.rounds.map((round) => (
                <span key={round.id} className="prog__round">
                  <span className="chip chip-mute num">
                    {round.round_type} · {new Date(round.deadline).toLocaleDateString('ru')}
                  </span>
                  {canEdit && (
                    <DeleteButton
                      model="universities.AdmissionRound"
                      id={round.id}
                      path="/rounds/"
                      invalidate={INVALIDATE}
                      label="Убрать раунд"
                    />
                  )}
                </span>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
