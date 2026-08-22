/**
 * Кабинет ученика: процент готовности и задачи.
 * Внутренних ярлыков здесь нет — их не отдаёт даже API (инвариант №7).
 */
import { useMyProfile } from '../../api/hooks'
import { Bar, ErrorNote, Loading, Ring, ScreenHead } from '../../components/ui'

export default function StudentHome() {
  const { data, isLoading, error } = useMyProfile()
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const readiness = data.readiness

  return (
    <div>
      <ScreenHead
        emoji="◎"
        title={`Привет, ${data.first_name}`}
        subtitle="Где вы сейчас и что двинет вас дальше всего."
      />

      <div className="split">
        <div className="card card-pad" style={{ display: 'grid', placeItems: 'center', padding: 28 }}>
          <Ring percent={readiness?.score ?? 0} size={150}>
            <div>
              <div className="num" style={{ fontSize: 34, fontWeight: 800, lineHeight: 1 }}>
                {readiness?.score ?? 0}%
              </div>
              <div className="muted" style={{ fontSize: 11.5 }}>
                готовность
              </div>
            </div>
          </Ring>
          {readiness?.weakest_title && (
            <p className="muted" style={{ marginTop: 18, textAlign: 'center', fontSize: 13 }}>
              Больше всего сейчас даст работа над блоком «{readiness.weakest_title}».
            </p>
          )}
        </div>

        <div className="card card-pad">
          <span className="eyebrow">Из чего складывается</span>
          <div style={{ marginTop: 14 }}>
            {readiness?.parts.map((part) => (
              <div key={part.code} style={{ padding: '9px 0' }}>
                <div className="row-between" style={{ fontSize: 13, marginBottom: 6 }}>
                  <span style={{ fontWeight: 650 }}>{part.title}</span>
                  <b className="num">{Math.round(part.value)}%</b>
                </div>
                <Bar
                  percent={part.value}
                  color={part.code === readiness.weakest ? 'var(--brand)' : 'var(--teal)'}
                />
              </div>
            ))}
            {(readiness?.skipped ?? []).map((part) => (
              <div key={part.code} style={{ padding: '9px 0', opacity: 0.55 }}>
                <div className="row-between" style={{ fontSize: 13, marginBottom: 6 }}>
                  <span style={{ fontWeight: 650 }}>{part.title}</span>
                  <span className="muted" style={{ fontSize: 12 }}>
                    данных пока нет
                  </span>
                </div>
                <Bar percent={0} color="var(--line)" />
              </div>
            ))}
            {!readiness?.parts.length && !readiness?.skipped.length && (
              <p className="muted">Данных пока нет — профиль ещё заполняется.</p>
            )}
            {(readiness?.skipped.length ?? 0) > 0 && (
              <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
                Блоки без данных в процент не входят — он считается по тем, что заполнены.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
