/**
 * Управление теорией — академический директор на «Пробных» (фаза 42).
 *
 * Уроки без истории, удаление физическое. Файл урока загружается отдельно
 * и отдаётся ученику только после проверки прав.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useTheory, useTheoryRows } from '../api/hooks'
import { t } from '../i18n'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { NativeSelectOption } from './ui/native-select'
import { SelectField } from './SelectField'
import { Textarea } from './ui/textarea'

const EXAMS = ['IELTS', 'TOEFL', 'SAT', 'ACT', 'ENT', 'HSK', 'Duolingo']
const SECTIONS = [
  { value: '', title: '—' },
  { value: 'listening', title: 'Listening' },
  { value: 'reading', title: 'Reading' },
  { value: 'writing', title: 'Writing' },
  { value: 'speaking', title: 'Speaking' },
  { value: 'math', title: 'Math' },
  { value: 'verbal', title: 'Verbal' },
]
const LEVELS = [
  { value: 'basic', title: 'Базовый' },
  { value: 'medium', title: 'Средний' },
  { value: 'advanced', title: 'Продвинутый' },
]

export default function TheoryManager() {
  const { create, remove } = useTheoryRows()
  const [exam, setExam] = useState('IELTS')
  const list = useTheory(exam)
  const [draft, setDraft] = useState({
    section: '',
    title: '',
    level: 'basic',
    reading_minutes: '5',
    body: '',
  })

  const submit = () => {
    if (!draft.title.trim()) {
      toast.error(t('Заполните название урока'))
      return
    }
    create.mutate(
      {
        exam_type: exam,
        section: draft.section,
        title: draft.title,
        level: draft.level,
        reading_minutes: Number(draft.reading_minutes) || 5,
        body: draft.body,
      },
      {
        onSuccess: () => {
          toast.success(t('Урок добавлен'))
          setDraft({ section: '', title: '', level: 'basic', reading_minutes: '5', body: '' })
        },
        onError: (error) => toast.error(error.message),
      },
    )
  }

  const rows = list.data?.results ?? []

  return (
    <div className="card card-pad">
      <span className="eyebrow">{t('Теория')}</span>
      <p className="muted prep__note">
        {t('Короткие уроки с уровнем и временем чтения. Их читают ученики в центре подготовки.')}
      </p>

      <div className="toolbar" style={{ marginTop: 12 }}>
        <SelectField value={exam} onChange={(e) => setExam(e.target.value)} aria-label={t('Экзамен')}>
          {EXAMS.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </SelectField>
      </div>

      <div className="propose__form">
        <div className="toolbar">
          <Input
            placeholder={t('Название урока')}
            value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            aria-label={t('Название урока')}
          />
          <SelectField
            value={draft.section}
            onChange={(e) => setDraft({ ...draft, section: e.target.value })}
            aria-label={t('Секция')}
          >
            {SECTIONS.map((s) => (
              <NativeSelectOption key={s.value} value={s.value}>
                {s.title}
              </NativeSelectOption>
            ))}
          </SelectField>
          <SelectField
            value={draft.level}
            onChange={(e) => setDraft({ ...draft, level: e.target.value })}
            aria-label={t('Уровень')}
          >
            {LEVELS.map((l) => (
              <NativeSelectOption key={l.value} value={l.value}>
                {t(l.title)}
              </NativeSelectOption>
            ))}
          </SelectField>
          <Input
            type="number"
            value={draft.reading_minutes}
            onChange={(e) => setDraft({ ...draft, reading_minutes: e.target.value })}
            aria-label={t('Минут чтения')}
            style={{ maxWidth: 80 }}
          />
        </div>
        <Textarea
          rows={3}
          placeholder={t('Текст урока')}
          value={draft.body}
          onChange={(e) => setDraft({ ...draft, body: e.target.value })}
          aria-label={t('Текст урока')}
        />
        <div className="propose__actions">
          <Button size="sm" disabled={create.isPending} onClick={submit}>
            {t('Добавить урок')}
          </Button>
        </div>
      </div>

      <ul className="rows__list">
        {rows.map((lesson) => (
          <li key={lesson.id} className="rows__item">
            <div className="rows__body">
              <span className="rows__label">{lesson.title}</span>
              <span className="muted rows__note">
                {lesson.section_title || t('Общее')} · {lesson.level_title} · {lesson.reading_minutes}{' '}
                {t('мин')}
              </span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(lesson.id, {
                  onSuccess: () => toast.success(t('Урок удалён')),
                  onError: (error) => toast.error(error.message),
                })
              }
            >
              {t('Удалить')}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  )
}
