/**
 * Платформенные моки — отдельным списком у академического директора.
 *
 * Балл, полученный на платформе, сам по себе текущий балл ученика не меняет:
 * решение «учитывать» принимает человек, и оно уходит в журнал.
 */
import { useState } from 'react'
import { usePlatformMocks, useReviewMock } from '../api/hooks'
import { t } from '../i18n'
import { Button } from './ui/button'
import { Badge } from './ui/badge'

/**
 * Столько строк показываем сразу. На школе в 250 человек этот список
 * иначе занимает весь дашборд, а решать надо по тем, что ждут решения.
 */
const VISIBLE = 10

export default function PlatformMocks() {
  const mocks = usePlatformMocks()
  const review = useReviewMock()
  const [all, setAll] = useState(false)

  const rows = mocks.data ?? []
  if (rows.length === 0) return null

  const waiting = rows.filter((row) => !row.counted_in_profile && !row.reviewed_at)
  // сверху то, что ждёт решения: просмотренное листать незачем
  const ordered = [...waiting, ...rows.filter((row) => !waiting.includes(row))]
  const shown = all ? ordered : ordered.slice(0, VISIBLE)

  return (
    <div className="card card-pad queue" id="platform-mocks">
      <span className="eyebrow">{t('Пробные, пройденные на платформе')}</span>
      <p className="muted queue__note">
        {waiting.length > 0
          ? `${waiting.length} ждут вашего решения. Пока вы не отметите, текущий балл ученика они не меняют.`
          : 'Все результаты просмотрены.'}
      </p>
      <table className="history">
        <tbody>
          {shown.map((row) => (
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
                  <Badge variant="ok">{t('учтён в баллах')}</Badge>
                ) : row.reviewed_at ? (
                  <Badge variant="mute">{t('не учитывать')}</Badge>
                ) : (
                  <Badge variant="warn">{t('ждёт решения')}</Badge>
                )}
              </td>
              <td>
                <span style={{ display: 'flex', gap: 6 }}>
                  <Button
                    size="sm"
                    disabled={review.isPending || row.counted_in_profile}
                    onClick={() => review.mutate({ id: row.id, count_it: true })}
                  >
                    {t('Учесть в баллах')}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={review.isPending}
                    onClick={() => review.mutate({ id: row.id, count_it: false })}
                  >
                    {t('Не учитывать')}
                  </Button>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {ordered.length > VISIBLE && (
        <Button variant="outline" size="sm" className="queue__more" onClick={() => setAll(!all)}>
          {all ? 'Свернуть' : `Показать все — ещё ${ordered.length - VISIBLE}`}
        </Button>
      )}
    </div>
  )
}
