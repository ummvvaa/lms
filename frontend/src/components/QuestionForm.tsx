/**
 * Форма задания банка — по секции.
 *
 * Раньше форма была одна на всё: четыре варианта и верный ответ. Для Listening
 * в ней не было аудио, для Reading — текста, а у Writing и Speaking вариантов
 * не бывает вовсе. Состав формы теперь следует из выбранной секции и умеет то
 * же, что файл массовой загрузки (`guides/QUESTION_BANK.md`):
 *
 * - Listening — аудио сверху (mp3/m4a до 20 МБ, без него не сохраняется),
 *   под ним вопросы с вариантами;
 * - Reading — пассаж сверху, вопросы под ним, добавляются кнопкой;
 * - Writing, Speaking — без вариантов: задание, критерии оценки, предел;
 * - остальные секции (SAT и прочее) — вопрос с вариантами; пассаж по желанию.
 *
 * Правила держит сервер (`prep.serializers`), форма только собирает нужные
 * поля: отказ сервера показывается словами под формой.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { PlusIcon, Trash2Icon } from 'lucide-react'
import {
  usePassageRows,
  usePassageWithQuestions,
  useQuestionRows,
  type BankPassage,
  type BankQuestion,
  type QuestionWrite,
} from '../api/hooks'
import ConfirmDialog from './ConfirmDialog'
import { SelectField } from './SelectField'
import { Chip, ErrorNote, Loading } from './ui'
import { Button } from './ui/button'
import { Checkbox } from './ui/checkbox'
import { Input } from './ui/input'
import { Textarea } from './ui/textarea'
import { t } from '../i18n'

export const EXAM_TYPES = ['IELTS', 'TOEFL', 'SAT', 'ACT'].map((value) => ({ value, title: value }))

export const SECTIONS = [
  { value: 'listening', title: 'Listening' },
  { value: 'reading', title: 'Reading' },
  { value: 'writing', title: 'Writing' },
  { value: 'speaking', title: 'Speaking' },
  { value: 'math', title: 'Math' },
  { value: 'verbal', title: 'Verbal' },
]

export const DIFFICULTIES = [
  { value: 'easy', title: 'Простое' },
  { value: 'medium', title: 'Среднее' },
  { value: 'hard', title: 'Сложное' },
]

const LETTERS = ['A', 'B', 'C', 'D']
const OPEN_SECTIONS = ['writing', 'speaking']

interface QuestionDraft {
  /** id существующего вопроса; у нового — нет */
  id?: number
  text: string
  options: Record<string, string>
  correct: string
  explanation: string
}

const blankQuestion = (): QuestionDraft => ({
  text: '',
  options: Object.fromEntries(LETTERS.map((letter) => [letter, ''])),
  correct: '',
  explanation: '',
})

const draftOf = (question: BankQuestion): QuestionDraft => ({
  id: question.id,
  text: question.text,
  options: Object.fromEntries(
    LETTERS.map((letter) => [letter, question.options.find((o) => o.letter === letter)?.text ?? '']),
  ),
  correct: question.options.find((o) => o.is_correct)?.letter ?? '',
  explanation: question.explanation,
})

function Field({ label, wide, children }: { label: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <label className={`qform__field${wide ? ' qform__field--wide' : ''}`}>
      <span className="rowform__label">{label}</span>
      {children}
    </label>
  )
}

/** Один вопрос с вариантами: текст, A–D, верный, объяснение. */
function ChoiceQuestion({
  number,
  draft,
  onChange,
  onRemove,
}: {
  number: number | null
  draft: QuestionDraft
  onChange: (next: QuestionDraft) => void
  onRemove?: () => void
}) {
  return (
    <fieldset className="qform__question">
      {number !== null && (
        <legend className="qform__legend">
          {t('Вопрос')} {number}
          {onRemove && (
            <Button
              variant="ghost"
              size="icon"
              aria-label={`${t('Убрать вопрос')} ${number}`}
              onClick={onRemove}
            >
              <Trash2Icon />
            </Button>
          )}
        </legend>
      )}
      <Field label={t('Текст задания')} wide>
        <Textarea
          rows={2}
          value={draft.text}
          onChange={(e) => onChange({ ...draft, text: e.target.value })}
        />
      </Field>
      <div className="qform__options">
        {LETTERS.map((letter) => (
          <Field key={letter} label={`${t('Вариант')} ${letter}`}>
            <Input
              value={draft.options[letter] ?? ''}
              onChange={(e) =>
                onChange({ ...draft, options: { ...draft.options, [letter]: e.target.value } })
              }
            />
          </Field>
        ))}
      </div>
      <Field label={t('Верный вариант')}>
        <SelectField value={draft.correct} onChange={(e) => onChange({ ...draft, correct: e.target.value })}>
          <option value="">{t('— не выбрано —')}</option>
          {LETTERS.filter((letter) => (draft.options[letter] ?? '').trim() !== '').map((letter) => (
            <option key={letter} value={letter}>
              {letter}
            </option>
          ))}
        </SelectField>
      </Field>
      <Field label={t('Объяснение для разбора')} wide>
        <Textarea
          rows={2}
          value={draft.explanation}
          onChange={(e) => onChange({ ...draft, explanation: e.target.value })}
        />
      </Field>
    </fieldset>
  )
}

export default function QuestionForm({
  editing,
  onDone,
  onCancel,
}: {
  /** правка существующего задания; у нового — `null` */
  editing: BankQuestion | null
  onDone: () => void
  onCancel: () => void
}) {
  const questions = useQuestionRows()
  const passages = usePassageRows()
  // задание с источником правится вместе с ним и соседними вопросами: пассаж
  // один, вопросов несколько — править их поодиночке значит потерять остальные из виду
  const loaded = usePassageWithQuestions(editing?.passage ?? null)

  const [examType, setExamType] = useState(editing?.exam_type ?? 'IELTS')
  const [section, setSection] = useState(editing?.section ?? 'listening')
  const [topic, setTopic] = useState(editing?.topic ?? '')
  const [difficulty, setDifficulty] = useState(editing?.difficulty ?? 'medium')
  const [source, setSource] = useState(editing?.source ?? '')

  // открытое задание
  const [task, setTask] = useState(editing?.text ?? '')
  const [criteria, setCriteria] = useState(editing?.criteria ?? '')
  const [sample, setSample] = useState(editing?.sample_answer ?? '')
  const [limit, setLimit] = useState(
    String((editing?.section === 'speaking' ? editing?.minute_limit : editing?.word_limit) ?? ''),
  )

  // источник и вопросы к нему
  const [withPassage, setWithPassage] = useState(editing?.passage != null)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [audio, setAudio] = useState<File | null>(null)
  const [drafts, setDrafts] = useState<QuestionDraft[]>(() => [editing ? draftOf(editing) : blankQuestion()])
  const [removed, setRemoved] = useState<number[]>([])
  const [filledFrom, setFilledFrom] = useState<number | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [hiding, setHiding] = useState(false)

  // пассаж с сервера подставляется в форму один раз, когда пришёл
  const passage: BankPassage | null = loaded.data?.passage ?? null
  if (passage && loaded.data && filledFrom !== passage.id) {
    setFilledFrom(passage.id)
    setTitle(passage.title)
    setBody(passage.body)
    setDrafts(loaded.data.questions.map(draftOf))
  }

  const isOpen = OPEN_SECTIONS.includes(section)
  const isListening = section === 'listening'
  const isReading = section === 'reading'
  // у Listening и Reading источник обязателен; в остальных секциях — по желанию
  const needsSource = isListening || isReading
  const hasSource = !isOpen && (needsSource || withPassage)

  if (editing?.passage != null && loaded.isLoading) return <Loading />
  if (loaded.error) return <ErrorNote error={loaded.error} />

  const common = () => ({
    exam_type: examType,
    section,
    topic: topic.trim(),
    difficulty,
    source: source.trim(),
  })

  const choiceBody = (draft: QuestionDraft, passageId: number | null): QuestionWrite => ({
    ...common(),
    text: draft.text.trim(),
    explanation: draft.explanation.trim(),
    passage: passageId,
    options: LETTERS.filter((letter) => (draft.options[letter] ?? '').trim() !== '').map((letter) => ({
      letter,
      text: draft.options[letter].trim(),
      is_correct: draft.correct === letter,
    })),
  })

  /** То, что видно и без сервера: пустое обязательное поле называем сразу. */
  const firstProblem = (): string | null => {
    if (!topic.trim()) return t('Заполните тему — по ней тренировка подбирает задания')
    if (isOpen) return task.trim() ? null : t('Напишите текст задания')
    if (isListening && !audio && !passage?.has_audio)
      return t('Приложите аудио: задание на аудирование без него не сохраняется')
    if (isReading && !body.trim()) return t('Вставьте текст пассажа — вопросы заводятся к нему')
    if (hasSource && !isListening && !body.trim())
      return t('Вставьте текст пассажа или снимите отметку «Вопросы к тексту»')
    const broken = drafts.findIndex(
      (draft) =>
        !draft.text.trim() ||
        LETTERS.filter((letter) => (draft.options[letter] ?? '').trim() !== '').length < 2 ||
        !draft.correct,
    )
    return broken === -1
      ? null
      : `${t('Вопрос')} ${broken + 1}: ${t('нужен текст, хотя бы два варианта и отмеченный верный')}`
  }

  const save = async () => {
    const found = firstProblem()
    setProblem(found)
    if (found) return
    setBusy(true)
    try {
      if (isOpen) {
        const open: QuestionWrite = {
          ...common(),
          text: task.trim(),
          criteria: criteria.trim(),
          sample_answer: sample.trim(),
          word_limit: section === 'writing' && limit ? Number(limit) : null,
          minute_limit: section === 'speaking' && limit ? Number(limit) : null,
          passage: null,
          options: [],
        }
        if (editing) await questions.update.mutateAsync({ id: editing.id, ...open })
        else await questions.create.mutateAsync(open)
      } else {
        let passageId: number | null = null
        if (hasSource) {
          const fields = {
            exam_type: examType,
            section,
            kind: isListening ? 'listening' : 'reading',
            title: title.trim(),
            body: body.trim(),
            source: source.trim(),
            audio,
          }
          const saved = passage
            ? await passages.update.mutateAsync({ id: passage.id, fields })
            : await passages.create.mutateAsync(fields)
          passageId = saved.id
        }
        for (const draft of drafts) {
          const payload = choiceBody(draft, passageId)
          if (draft.id) await questions.update.mutateAsync({ id: draft.id, ...payload })
          else await questions.create.mutateAsync(payload)
        }
        // убранные из формы вопросы скрываются, как и кнопкой в таблице
        for (const id of removed) await questions.update.mutateAsync({ id, is_active: false })
      }
      toast.success(t('Сохранено'))
      onDone()
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="qform">
      <div className="qform__head">
        <Field label={t('Экзамен')}>
          <SelectField
            value={examType}
            disabled={passage !== null}
            onChange={(e) => setExamType(e.target.value)}
          >
            {EXAM_TYPES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.title}
              </option>
            ))}
          </SelectField>
        </Field>
        <Field label={t('Секция')}>
          {/* секция задаёт состав формы; у заведённого задания она не меняется —
              иначе вопрос с вариантами молча стал бы эссе */}
          <SelectField
            value={section}
            disabled={editing !== null}
            onChange={(e) => setSection(e.target.value)}
          >
            {SECTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.title}
              </option>
            ))}
          </SelectField>
        </Field>
        <Field label={t('Тема')}>
          <Input value={topic} onChange={(e) => setTopic(e.target.value)} />
        </Field>
        <Field label={t('Сложность')}>
          <SelectField value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
            {DIFFICULTIES.map((option) => (
              <option key={option.value} value={option.value}>
                {t(option.title)}
              </option>
            ))}
          </SelectField>
        </Field>
      </div>

      {isOpen && (
        <>
          <p className="muted qform__hint">
            {t(
              'Вариантов у этой секции нет: ученик пишет ответ сам, вы проверяете его руками — оценка и комментарий.',
            )}
          </p>
          <Field label={t('Текст задания')} wide>
            <Textarea rows={4} value={task} onChange={(e) => setTask(e.target.value)} />
          </Field>
          <Field label={t('Критерии оценки — ученик увидит их в разборе')} wide>
            <Textarea rows={3} value={criteria} onChange={(e) => setCriteria(e.target.value)} />
          </Field>
          <Field label={section === 'writing' ? t('Лимит слов') : t('Лимит минут')}>
            <Input
              className="num"
              type="number"
              min={1}
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
            />
          </Field>
          <Field label={t('Образец ответа — по желанию')} wide>
            <Textarea rows={3} value={sample} onChange={(e) => setSample(e.target.value)} />
          </Field>
        </>
      )}

      {!isOpen && !needsSource && (
        <label className="rowform__check">
          <Checkbox checked={withPassage} disabled={passage !== null} onCheckedChange={(on) => setWithPassage(Boolean(on))} />
          <span>{t('Вопросы к тексту (пассаж)')}</span>
        </label>
      )}

      {hasSource && (
        <fieldset className="qform__source">
          <legend className="qform__legend">{isListening ? t('Аудио') : t('Пассаж')}</legend>
          <Field label={t('Заголовок')} wide>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          {isListening && (
            <Field label={t('Аудиофайл: mp3 или m4a, до 20 МБ')} wide>
              <Input
                type="file"
                accept=".mp3,.m4a,audio/mpeg,audio/mp4"
                onChange={(e) => setAudio(e.target.files?.[0] ?? null)}
              />
              {passage?.has_audio && !audio && (
                <span className="qform__audio">
                  <Chip tone="good">{t('аудио загружено')}</Chip>
                  <audio controls preload="none" src={passage.audio_url} />
                </span>
              )}
            </Field>
          )}
          <Field
            label={
              isListening ? t('Расшифровка — по желанию, ученик увидит её в разборе') : t('Текст пассажа')
            }
            wide
          >
            <Textarea rows={isListening ? 3 : 8} value={body} onChange={(e) => setBody(e.target.value)} />
          </Field>
        </fieldset>
      )}

      {!isOpen && (
        <>
          {drafts.map((draft, index) => (
            <ChoiceQuestion
              key={draft.id ?? `new-${index}`}
              number={hasSource ? index + 1 : null}
              draft={draft}
              onChange={(next) => setDrafts(drafts.map((row, place) => (place === index ? next : row)))}
              onRemove={
                hasSource && drafts.length > 1
                  ? () => {
                      if (draft.id) setRemoved([...removed, draft.id])
                      setDrafts(drafts.filter((_, place) => place !== index))
                    }
                  : undefined
              }
            />
          ))}
          {hasSource && (
            <Button variant="outline" size="sm" onClick={() => setDrafts([...drafts, blankQuestion()])}>
              <PlusIcon />
              {t('Добавить вопрос')}
            </Button>
          )}
        </>
      )}

      <Field label={t('Источник')} wide>
        <Input value={source} onChange={(e) => setSource(e.target.value)} />
      </Field>

      {problem && (
        <Chip tone="bad">
          {problem}
        </Chip>
      )}

      <div className="rowform__actions">
        {/* источник убирается вместе со своими вопросами: вопрос к тексту,
            которого нет, ученику показывать нечем */}
        {passage && (
          <Button variant="ghost" size="sm" onClick={() => setHiding(true)}>
            {isListening ? t('Скрыть аудио и его вопросы') : t('Скрыть пассаж и его вопросы')}
          </Button>
        )}
        <Button variant="outline" size="sm" onClick={onCancel}>
          {t('Отмена')}
        </Button>
        <Button size="sm" disabled={busy} onClick={() => void save()}>
          {editing ? t('Сохранить') : t('Завести')}
        </Button>
      </div>
      <ConfirmDialog
        open={hiding}
        title={t('Скрыть источник?')}
        what={`${passage?.title || t('Источник')}: ${t('вопросов')} ${drafts.length}`}
        consequences={[t('Источник и его вопросы уйдут из тренировок. Ответы учеников останутся.')]}
        confirmLabel={t('Скрыть')}
        busy={passages.remove.isPending}
        onCancel={() => setHiding(false)}
        onConfirm={() => {
          if (!passage) return
          passages.remove.mutate(passage.id, {
            onSuccess: () => {
              toast.success(t('Источник скрыт'))
              onDone()
            },
            onError: (error) => setProblem(error.message),
          })
        }}
      />
    </div>
  )
}
