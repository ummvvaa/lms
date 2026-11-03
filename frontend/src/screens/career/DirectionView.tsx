/**
 * Направление разбора для чтения — у профориентолога без правки и у ученика.
 * Порядок: направление и его название за рубежом → почему подходит →
 * профессии → что сдавать → что подтянуть в школе → что сделать сейчас →
 * программы каталога. Пустые поля не выводятся; текст переносится целиком.
 */
import type { CareerDirection } from '../../api/career'
import { Row, Rows } from '../../components/patterns'
import { EmptyNote } from '../../components/ui'
import { t, tk } from '../../i18n'

export const DIRECTION_FIELDS = [
  { name: 'professions', label: tk('Профессии') },
  { name: 'exams', label: tk('Что сдавать для поступления') },
  { name: 'subjects', label: tk('Что подтянуть в школе') },
  { name: 'next_steps', label: tk('Что сделать уже сейчас') },
] as const

/** Программы каталога направления; у нового разбора пустой список — подсказка, у старого — ничего. */
export function DirectionPrograms({ direction, legacy }: { direction: CareerDirection; legacy?: boolean }) {
  if (direction.programs.length === 0)
    return legacy ? null : (
      <div className="canal__fact">
        <span className="eyebrow">{t('Программы каталога')}</span>
        <EmptyNote what={tk('В каталоге пока нет программ по этому направлению — уточните у директора по поступлению')} />
      </div>
    )
  return (
    <div className="canal__fact">
      <span className="eyebrow">{t('Программы каталога')}</span>
      <Rows>
        {direction.programs.map((program) => (
          <Row key={program.id} icon="cap" title={program.name} note={`${program.university} · ${program.level_title}`} />
        ))}
      </Rows>
    </div>
  )
}

/** Название направления и под ним мелко — как оно называется за рубежом. */
export function DirectionHead({ direction }: { direction: CareerDirection }) {
  return (
    <div className="canal__head">
      <b className="canal__title">{direction.title}</b>
      {direction.title_abroad && <span className="t-note canal__abroad">{direction.title_abroad}</span>}
    </div>
  )
}

/** Профессии, экзамены, предметы, шаги и программы — без правки. */
export function DirectionFacts({ direction, legacy }: { direction: CareerDirection; legacy?: boolean }) {
  return (
    <>
      {DIRECTION_FIELDS.map(({ name, label }) =>
        direction[name] ? (
          <div key={name} className="canal__fact">
            <span className="eyebrow">{t(label)}</span>
            <p className="canal__text">{direction[name]}</p>
          </div>
        ) : null,
      )}
      <DirectionPrograms direction={direction} legacy={legacy} />
    </>
  )
}

export default function DirectionView({ direction, reasoning, legacy }: { direction: CareerDirection; reasoning: string; legacy?: boolean }) {
  return (
    <div className="canal__dir">
      <DirectionHead direction={direction} />
      {reasoning && (
        <div className="canal__fact">
          <span className="eyebrow">{t('Почему подходит')}</span>
          <p className="canal__text">{reasoning}</p>
        </div>
      )}
      <DirectionFacts direction={direction} legacy={legacy} />
    </div>
  )
}
