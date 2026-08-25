/**
 * Программы одного вуза: правка, заведение и удаление.
 *
 * До фазы 29 отсюда можно было только удалить: чтобы поднять порог IELTS
 * с 6.0 до 6.5, требования приходилось стереть и завести заново. Теперь
 * каждый уровень правится на месте — вуз, программа, требования, раунд.
 *
 * Правка руками от директора по поступлению снимает плашку
 * «не подтверждено»: он владелец домена и сверяет данные по сайту —
 * второй кнопки «подтвердить» после каждой правки быть не должно.
 *
 * Удаление убрано в меню: справочник — это работа с данными, а не
 * поле красных кнопок, и промахиваться здесь не по чему.
 */
import { useState } from 'react'
import {
  useCreateProgram,
  useCreateRequirement,
  useCreateRound,
  useProgramsOf,
  useUpdateProgram,
  useUpdateRequirement,
  useUpdateRound,
  type DirectoryProgram,
} from '../api/hooks'
import DeleteButton from './DeleteButton'
import RowMenu, { RowMenuItem, RowMenuSeparator } from './RowMenu'
import { Chip, ErrorNote, Loading } from './ui'
import { t } from '../i18n'
import { NativeSelect } from './ui/native-select'
import { Input } from './ui/input'
import { Checkbox } from './ui/checkbox'

const INVALIDATE = [['programs'], ['universities'], ['catalog']]

const LEVELS = [
  { value: 'bachelor', title: 'Бакалавриат' },
  { value: 'master', title: 'Магистратура' },
]

const ROUND_TYPES = ['ED', 'EA', 'RD', 'RO']

/** Поле формы: подпись сверху, значение снизу — одинаково везде. */
function Field({
  label,
  value,
  onChange,
  type = 'text',
  placeholder,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
  placeholder?: string
}) {
  return (
    <label className="prog__field">
      <span className="muted">{label}</span>
      <Input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}

/** Правка требований: пустое поле значит «требования нет», а не ноль. */
function RequirementForm({ program, onClose }: { program: DirectoryProgram; onClose: () => void }) {
  const update = useUpdateRequirement()
  const create = useCreateRequirement()
  const current = program.requirement
  const [draft, setDraft] = useState({
    min_gpa: current?.min_gpa?.toString() ?? '',
    min_ielts: current?.min_ielts?.toString() ?? '',
    min_toefl: current?.min_toefl?.toString() ?? '',
    min_sat: current?.min_sat?.toString() ?? '',
    min_act: current?.min_act?.toString() ?? '',
    required_subjects: current?.required_subjects ?? '',
    portfolio_note: current?.portfolio_note ?? '',
  })
  const [portfolio, setPortfolio] = useState(current?.portfolio_required ?? false)
  const [problem, setProblem] = useState<string | null>(null)

  const save = () => {
    // пустая строка — это «требования нет» (решение фазы 4), поэтому
    // она уходит как null, а не как ноль: иначе все проходили бы порог
    const body = {
      program: program.id,
      min_gpa: draft.min_gpa.trim() || null,
      min_ielts: draft.min_ielts.trim() || null,
      min_toefl: draft.min_toefl.trim() || null,
      min_sat: draft.min_sat.trim() || null,
      min_act: draft.min_act.trim() || null,
      required_subjects: draft.required_subjects.trim(),
      portfolio_required: portfolio,
      portfolio_note: draft.portfolio_note.trim(),
    }
    const done = { onSuccess: onClose, onError: (e: unknown) => setProblem(String((e as Error).message)) }
    if (current) update.mutate({ id: current.id, ...body }, done)
    else create.mutate(body, done)
  }

  return (
    <div className="prog__form">
      <div className="prog__grid">
        <Field label="GPA" value={draft.min_gpa} onChange={(v) => setDraft({ ...draft, min_gpa: v })} />
        <Field label="IELTS" value={draft.min_ielts} onChange={(v) => setDraft({ ...draft, min_ielts: v })} />
        <Field label="TOEFL" value={draft.min_toefl} onChange={(v) => setDraft({ ...draft, min_toefl: v })} />
        <Field label="SAT" value={draft.min_sat} onChange={(v) => setDraft({ ...draft, min_sat: v })} />
        <Field label="ACT" value={draft.min_act} onChange={(v) => setDraft({ ...draft, min_act: v })} />
      </div>
      <Field
        label={t('Требуемые предметы')}
        value={draft.required_subjects}
        onChange={(v) => setDraft({ ...draft, required_subjects: v })}
        placeholder={t('через запятую')}
      />
      <label className="prog__check">
        <Checkbox checked={portfolio} onCheckedChange={setPortfolio} />
        {t('Нужно портфолио')}
      </label>
      <Field
        label={t('Требования к портфолио')}
        value={draft.portfolio_note}
        onChange={(v) => setDraft({ ...draft, portfolio_note: v })}
      />
      <p className="muted prog__hint">
        {t('Пустое поле значит «требования нет», а не ноль: по незаполненному порогу проходят все.')}
      </p>
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <button className="btn btn-primary btn-sm" onClick={save}>
          {t('Сохранить')}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>
          {t('Отмена')}
        </button>
        {problem && <span className="chip chip-risk">{problem}</span>}
      </div>
    </div>
  )
}

/** Правка или заведение раунда: тип и дедлайн. */
function RoundForm({
  programId,
  round,
  onClose,
}: {
  programId: number
  round?: { id: number; round_type: string; deadline: string }
  onClose: () => void
}) {
  const update = useUpdateRound()
  const create = useCreateRound()
  const [type, setType] = useState(round?.round_type ?? 'RD')
  const [deadline, setDeadline] = useState(round?.deadline ?? '')
  const [problem, setProblem] = useState<string | null>(null)

  const save = () => {
    if (!deadline) {
      setProblem(t('Без даты раунд не имеет смысла: по ней считаются задачи учеников'))
      return
    }
    const body = { program: programId, round_type: type, deadline }
    const done = { onSuccess: onClose, onError: (e: unknown) => setProblem(String((e as Error).message)) }
    if (round) update.mutate({ id: round.id, ...body }, done)
    else create.mutate(body, done)
  }

  return (
    <div className="prog__form">
      <div className="toolbar" style={{ marginBottom: 8 }}>
        <label className="prog__field">
          <span className="muted">{t('Тип раунда')}</span>
          <NativeSelect value={type} onChange={(event) => setType(event.target.value)}>
            {ROUND_TYPES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </NativeSelect>
        </label>
        <Field label={t('Дедлайн')} type="date" value={deadline} onChange={setDeadline} />
      </div>
      <p className="muted prog__hint">
        {t('Дедлайн принадлежит вузу: сдвиньте его здесь — он сдвинется у всех, кто подаётся.')}
      </p>
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <button className="btn btn-primary btn-sm" onClick={save}>
          {t('Сохранить')}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>
          {t('Отмена')}
        </button>
        {problem && <span className="chip chip-risk">{problem}</span>}
      </div>
    </div>
  )
}

/** Правка или заведение программы. */
function ProgramForm({
  universityId,
  program,
  onClose,
}: {
  universityId: number
  program?: DirectoryProgram
  onClose: () => void
}) {
  const update = useUpdateProgram()
  const create = useCreateProgram()
  const [name, setName] = useState(program?.name ?? '')
  const [level, setLevel] = useState(program?.level ?? 'bachelor')
  const [problem, setProblem] = useState<string | null>(null)

  const save = () => {
    if (!name.trim()) {
      setProblem(t('Название — обязательное поле'))
      return
    }
    const body = { university: universityId, name: name.trim(), level }
    const done = { onSuccess: onClose, onError: (e: unknown) => setProblem(String((e as Error).message)) }
    if (program) update.mutate({ id: program.id, ...body }, done)
    else create.mutate(body, done)
  }

  return (
    <div className="prog__form">
      <div className="toolbar" style={{ marginBottom: 8 }}>
        <Field label={t('Название программы')} value={name} onChange={setName} />
        <label className="prog__field">
          <span className="muted">{t('Уровень')}</span>
          <NativeSelect value={level} onChange={(event) => setLevel(event.target.value)}>
            {LEVELS.map((row) => (
              <option key={row.value} value={row.value}>
                {row.title}
              </option>
            ))}
          </NativeSelect>
        </label>
      </div>
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <button className="btn btn-primary btn-sm" onClick={save}>
          {t('Сохранить')}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>
          {t('Отмена')}
        </button>
        {problem && <span className="chip chip-risk">{problem}</span>}
      </div>
    </div>
  )
}

export default function ProgramList({ universityId, canEdit }: { universityId: number; canEdit: boolean }) {
  const list = useProgramsOf(universityId)
  const [editing, setEditing] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  if (list.isLoading) return <Loading kind="table" />
  if (list.isError) return <ErrorNote error={list.error} />
  const rows = list.data?.results ?? []

  return (
    <div className="prog">
      {rows.length === 0 && !adding && (
        <p className="muted rows__empty">{t('У этого вуза пока нет ни одной программы.')}</p>
      )}

      {rows.map((program) => (
        <div key={program.id} className="prog__row">
          <div className="row-between prog__head">
            <div>
              <b className="prog__name">{program.name}</b>
              {!program.is_verified && <Chip tone="warn">{t('не подтверждено')}</Chip>}
            </div>
            {canEdit && (
              <span className="prog__actions">
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setEditing(editing === `p${program.id}` ? null : `p${program.id}`)}
                >
                  {t('Изменить')}
                </button>
                <RowMenu>
                  <RowMenuItem onClick={() => setEditing(`req${program.id}`)}>
                    {program.requirement ? t('Изменить требования') : t('Завести требования')}
                  </RowMenuItem>
                  <RowMenuItem onClick={() => setEditing(`newround${program.id}`)}>
                    {t('Добавить раунд')}
                  </RowMenuItem>
                  <RowMenuSeparator />
                  <RowMenuItem risk keepOpen>
                    <DeleteButton
                      model="universities.Program"
                      id={program.id}
                      path="/programs/"
                      invalidate={INVALIDATE}
                      label={t('Удалить программу')}
                    />
                  </RowMenuItem>
                </RowMenu>
              </span>
            )}
          </div>

          {editing === `p${program.id}` && (
            <ProgramForm universityId={universityId} program={program} onClose={() => setEditing(null)} />
          )}

          <div className="prog__parts">
            <div className="prog__part">
              <span className="muted">{t('Требования')}</span>
              {program.requirement ? (
                <>
                  <span className="num">
                    GPA {program.requirement.min_gpa ?? '—'} · IELTS {program.requirement.min_ielts ?? '—'} ·
                    SAT {program.requirement.min_sat ?? '—'}
                  </span>
                  {canEdit && (
                    <button className="btn btn-ghost btn-sm" onClick={() => setEditing(`req${program.id}`)}>
                      {t('Изменить')}
                    </button>
                  )}
                  {canEdit && (
                    <RowMenu>
                      <RowMenuItem risk keepOpen>
                        <DeleteButton
                          model="universities.AdmissionRequirement"
                          id={program.requirement.id}
                          path="/requirements/"
                          invalidate={INVALIDATE}
                          label={t('Убрать требования')}
                        />
                      </RowMenuItem>
                    </RowMenu>
                  )}
                </>
              ) : (
                <>
                  <span className="muted">{t('не заведены')}</span>
                  {canEdit && (
                    <button className="btn btn-ghost btn-sm" onClick={() => setEditing(`req${program.id}`)}>
                      {t('Завести требования')}
                    </button>
                  )}
                </>
              )}
            </div>

            {editing === `req${program.id}` && (
              <RequirementForm program={program} onClose={() => setEditing(null)} />
            )}

            <div className="prog__part">
              <span className="muted">{t('Раунды')}</span>
              {program.rounds.length === 0 && <span className="muted">{t('не заведены')}</span>}
              {program.rounds.map((round) => (
                <span key={round.id} className="prog__round">
                  <span className="chip chip-mute num">
                    {round.round_type} · {new Date(round.deadline).toLocaleDateString('ru')}
                  </span>
                  {canEdit && (
                    <>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => setEditing(editing === `r${round.id}` ? null : `r${round.id}`)}
                      >
                        {t('Изменить')}
                      </button>
                      <RowMenu>
                        <RowMenuItem risk keepOpen>
                          <DeleteButton
                            model="universities.AdmissionRound"
                            id={round.id}
                            path="/rounds/"
                            invalidate={INVALIDATE}
                            label={t('Убрать раунд')}
                          />
                        </RowMenuItem>
                      </RowMenu>
                    </>
                  )}
                </span>
              ))}
              {canEdit && (
                <button className="btn btn-ghost btn-sm" onClick={() => setEditing(`newround${program.id}`)}>
                  {t('Добавить раунд')}
                </button>
              )}
            </div>

            {editing?.startsWith('r') && !editing.startsWith('req') && !editing.startsWith('newround') && (
              <RoundForm
                programId={program.id}
                round={program.rounds.find((row) => `r${row.id}` === editing)}
                onClose={() => setEditing(null)}
              />
            )}
            {editing === `newround${program.id}` && (
              <RoundForm programId={program.id} onClose={() => setEditing(null)} />
            )}
          </div>
        </div>
      ))}

      {canEdit && (
        <div className="prog__row">
          {adding ? (
            <ProgramForm universityId={universityId} onClose={() => setAdding(false)} />
          ) : (
            <button className="btn btn-ghost btn-sm" onClick={() => setAdding(true)}>
              {t('Добавить программу')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
