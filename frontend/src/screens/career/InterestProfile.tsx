/**
 * Профиль интересов разбора — по каждой шкале теста, от сильных до отвергаемых:
 * балл, подпись диапазона и что это значит. У профориентолога смысл правится
 * полем, у ученика — его версия на «ты». У разборов до 04.11.2026 профиля нет,
 * блок не выводится. Несколько тестов — шкалы под названием своего теста.
 */
import type { CareerProfileScale } from '../../api/career'
import Field from '../../components/Field'
import { t } from '../../i18n'

type Edit = { value: (scale: CareerProfileScale) => string; onChange: (scale: CareerProfileScale, value: string) => void; version: string }

const scoreOf = (scale: CareerProfileScale) => (scale.top ? t('{count} из {total}', { count: scale.score, total: scale.top }) : String(scale.score))

export default function InterestProfile({ profile, edit }: { profile: CareerProfileScale[]; edit?: Edit }) {
  if (profile.length === 0) return null
  const tests = [...new Set(profile.map((scale) => scale.test))]
  return (
    <div className="cprof">
      <span className="eyebrow">{t('Профиль интересов')}</span>
      {tests.map((test) => (
        <div key={test} className="cprof__test">
          {tests.length > 1 && <span className="t-note cprof__testname">{test}</span>}
          {profile
            .filter((scale) => scale.test === test)
            .map((scale) =>
              edit ? (
                <Field
                  key={scale.id}
                  kind="textarea"
                  rows={1}
                  name={`scale-${scale.id}-${edit.version}`}
                  label={[scale.title, scoreOf(scale), scale.label].filter(Boolean).join(' · ')}
                  value={edit.value(scale)}
                  onChange={(value) => edit.onChange(scale, value)}
                />
              ) : (
                <div key={scale.id} className="cprof__row">
                  <div className="cprof__head">
                    <b className="cprof__title">{scale.title}</b>
                    <span className="num cprof__score">{scoreOf(scale)}</span>
                  </div>
                  {scale.label && <span className="t-note">{scale.label}</span>}
                  {scale.meaning && <p className="canal__text">{scale.meaning}</p>}
                </div>
              ),
            )}
        </div>
      ))}
    </div>
  )
}
