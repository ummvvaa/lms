/**
 * Платформенные моки — отдельным списком у академического директора.
 *
 * Балл, полученный на платформе, сам по себе текущий балл ученика не меняет:
 * решение «учитывать» принимает человек, и оно уходит в журнал.
 */
import { usePlatformMocks, useReviewMock } from '../api/hooks'

export default function PlatformMocks() {
  const mocks = usePlatformMocks()
  const review = useReviewMock()

  const rows = mocks.data ?? []
  if (rows.length === 0) return null

  const waiting = rows.filter((row) => !row.counted_in_profile && !row.reviewed_at)

  return (
    <div className="card card-pad queue" id="platform-mocks">
      <span className="eyebrow">🎯 Пробные, пройденные на платформе</span>
      <p className="muted queue__note">
        {waiting.length > 0
          ? `${waiting.length} ждут вашего решения. Пока вы не отметите, текущий балл ученика они не меняют.`
          : 'Все результаты просмотрены.'}
      </p>
      <table className="history">
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td className="muted">{new Date(row.created_at).toLocaleDateString('ru')}</td>
              <td style={{ fontWeight: 650 }}>{row.student_name}</td>
              <td>{row.mock}</td>
              <td className="num">
                {row.score ?? '—'}{' '}
                <span className="muted">
                  ({row.correct}/{row.total})
                </span>
              </td>
              <td>
                {row.counted_in_profile ? (
                  <span className="chip chip-ok">учтён в баллах</span>
                ) : row.reviewed_at ? (
                  <span className="chip chip-mute">не учитывать</span>
                ) : (
                  <span className="chip chip-warn">ждёт решения</span>
                )}
              </td>
              <td>
                <span style={{ display: 'flex', gap: 6 }}>
                  <button
                    className="btn btn-primary btn-sm"
                    disabled={review.isPending || row.counted_in_profile}
                    onClick={() => review.mutate({ id: row.id, count_it: true })}
                  >
                    Учесть в баллах
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    disabled={review.isPending}
                    onClick={() => review.mutate({ id: row.id, count_it: false })}
                  >
                    Не учитывать
                  </button>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
