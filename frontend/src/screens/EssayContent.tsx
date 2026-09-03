/**
 * Конструктор эссе — управление у директора по поступлению (фаза 43).
 *
 * Типы документов, гайды, вопросы быстрой проверки и примеры «чтения дня»
 * ведёт директор по поступлению. В код это не зашито: справочник живёт
 * в базе и правится здесь.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useEssayContent, useEssayDocTypes, useEssayExamples, type EssayDocType } from '../api/hooks'
import { Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { NativeSelectOption } from '../components/ui/native-select'
import { SelectField } from '../components/SelectField'
import { Textarea } from '../components/ui/textarea'
import { t } from '../i18n'

function GuideForm({ docType }: { docType: EssayDocType }) {
  const { saveGuide } = useEssayContent()
  const [draft, setDraft] = useState({
    what_is: docType.guide?.what_is ?? '',
    prompts: docType.guide?.prompts ?? '',
    mistakes: docType.guide?.mistakes ?? '',
    tips: docType.guide?.tips ?? '',
  })
  const fields: [keyof typeof draft, string][] = [
    ['what_is', 'Что это за документ'],
    ['prompts', 'Какие бывают вопросы (по одному в строке)'],
    ['mistakes', 'Частые ошибки (по одной в строке)'],
    ['tips', 'Советы (по одному в строке)'],
  ]
  return (
    <div className="propose__form">
      {fields.map(([key, label]) => (
        <label key={key} className="propose__field">
          <span className="muted propose__label">{t(label)}</span>
          <Textarea
            rows={2}
            value={draft[key]}
            onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
          />
        </label>
      ))}
      <div className="propose__actions">
        <Button
          size="sm"
          disabled={saveGuide.isPending}
          onClick={() =>
            saveGuide.mutate(
              { doc_type: docType.id, ...draft },
              {
                onSuccess: () => toast.success(t('Гайд сохранён')),
                onError: (error) => toast.error(error.message),
              },
            )
          }
        >
          {t('Сохранить гайд')}
        </Button>
      </div>
    </div>
  )
}

function CheckForm({ docType }: { docType: EssayDocType }) {
  const { createCheck } = useEssayContent()
  const [draft, setDraft] = useState({ text: '', a: '', b: '', c: '', d: '', correct: 'A', explanation: '' })
  return (
    <div className="propose__form">
      <Input
        placeholder={t('Вопрос')}
        value={draft.text}
        onChange={(e) => setDraft({ ...draft, text: e.target.value })}
      />
      <div className="toolbar">
        <Input placeholder="A" value={draft.a} onChange={(e) => setDraft({ ...draft, a: e.target.value })} />
        <Input placeholder="B" value={draft.b} onChange={(e) => setDraft({ ...draft, b: e.target.value })} />
        <Input placeholder="C" value={draft.c} onChange={(e) => setDraft({ ...draft, c: e.target.value })} />
        <Input placeholder="D" value={draft.d} onChange={(e) => setDraft({ ...draft, d: e.target.value })} />
        <SelectField
          value={draft.correct}
          onChange={(e) => setDraft({ ...draft, correct: e.target.value })}
          aria-label={t('Верный вариант')}
        >
          {['A', 'B', 'C', 'D'].map((l) => (
            <NativeSelectOption key={l} value={l}>
              {l}
            </NativeSelectOption>
          ))}
        </SelectField>
      </div>
      <Input
        placeholder={t('Объяснение')}
        value={draft.explanation}
        onChange={(e) => setDraft({ ...draft, explanation: e.target.value })}
      />
      <div className="propose__actions">
        <Button
          size="sm"
          disabled={createCheck.isPending || !draft.text.trim()}
          onClick={() =>
            createCheck.mutate(
              {
                doc_type: docType.id,
                text: draft.text,
                option_a: draft.a,
                option_b: draft.b,
                option_c: draft.c,
                option_d: draft.d,
                correct: draft.correct,
                explanation: draft.explanation,
              },
              {
                onSuccess: () => {
                  toast.success(t('Вопрос добавлен'))
                  setDraft({ text: '', a: '', b: '', c: '', d: '', correct: 'A', explanation: '' })
                },
                onError: (error) => toast.error(error.message),
              },
            )
          }
        >
          {t('Добавить вопрос')}
        </Button>
      </div>
      <ul className="rows__list">
        {docType.check_questions.map((q) => (
          <li key={q.id} className="rows__item">
            <div className="rows__body">
              <span className="rows__label">{q.text}</span>
              <span className="muted rows__note">
                {t('верный')}: {q.correct}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Types() {
  const types = useEssayDocTypes()
  const { createType } = useEssayContent()
  const [name, setName] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)

  if (types.isLoading) return <Loading />
  const rows = types.data?.results ?? []

  return (
    <div>
      <div className="card card-pad">
        <span className="eyebrow">{t('Новый тип документа')}</span>
        <div className="toolbar" style={{ marginTop: 12 }}>
          <Input placeholder={t('Название типа')} value={name} onChange={(e) => setName(e.target.value)} />
          <Button
            size="sm"
            disabled={createType.isPending || !name.trim()}
            onClick={() =>
              createType.mutate(
                { code: name.trim().toLowerCase().replace(/\s+/g, '_').slice(0, 40), name },
                {
                  onSuccess: () => {
                    toast.success(t('Тип добавлен'))
                    setName('')
                  },
                  onError: (error) => toast.error(error.message),
                },
              )
            }
          >
            {t('Добавить тип')}
          </Button>
        </div>
      </div>

      {rows.map((docType) => (
        <div key={docType.id} className="card card-pad" style={{ marginTop: 12 }}>
          <button
            className="essay__head"
            onClick={() => setExpanded(expanded === docType.id ? null : docType.id)}
          >
            <div>
              <b>{docType.name}</b>
              <p className="muted essay__note">
                {docType.description} · {t('лимит')} {docType.default_word_limit}
              </p>
            </div>
          </button>
          {expanded === docType.id && (
            <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
              <span className="eyebrow">{t('Гайд из четырёх шагов')}</span>
              <GuideForm docType={docType} />
              <span className="eyebrow" style={{ display: 'block', marginTop: 16 }}>
                {t('Вопросы быстрой проверки')}
              </span>
              <CheckForm docType={docType} />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function Examples() {
  const examples = useEssayExamples()
  const { createExample } = useEssayContent()
  const [draft, setDraft] = useState({ title: '', source_url: '', body: '' })

  const rows = examples.data?.results ?? []
  return (
    <div>
      <div className="card card-pad">
        <span className="eyebrow">{t('Новый пример для чтения дня')}</span>
        <div className="propose__form">
          <Input
            placeholder={t('Название')}
            value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          />
          <Input
            placeholder={t('Ссылка (не обязательно)')}
            value={draft.source_url}
            onChange={(e) => setDraft({ ...draft, source_url: e.target.value })}
          />
          <Textarea
            rows={3}
            placeholder={t('Текст примера')}
            value={draft.body}
            onChange={(e) => setDraft({ ...draft, body: e.target.value })}
          />
          <div className="propose__actions">
            <Button
              size="sm"
              disabled={createExample.isPending || !draft.title.trim()}
              onClick={() =>
                createExample.mutate(draft, {
                  onSuccess: () => {
                    toast.success(t('Пример добавлен'))
                    setDraft({ title: '', source_url: '', body: '' })
                  },
                  onError: (error) => toast.error(error.message),
                })
              }
            >
              {t('Добавить пример')}
            </Button>
          </div>
        </div>
      </div>
      <div className="card card-pad" style={{ marginTop: 12 }}>
        <ul className="rows__list">
          {rows.map((example) => (
            <li key={example.id} className="rows__item">
              <div className="rows__body">
                <span className="rows__label">{example.title}</span>
                <span className="muted rows__note">{example.doc_type_name}</span>
              </div>
            </li>
          ))}
          {rows.length === 0 && <p className="muted essay__note">{t('Примеров пока нет.')}</p>}
        </ul>
      </div>
    </div>
  )
}

export default function EssayContent() {
  const [tab, setTab] = useState<'types' | 'examples'>('types')
  return (
    <div>
      <ScreenHead
        title={t('Конструктор эссе')}
        subtitle={t('Типы документов, гайды, быстрая проверка и примеры чтения дня.')}
      />
      <ScreenTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'types', label: t('Типы и гайды') },
          { value: 'examples', label: t('Чтение дня') },
        ]}
      />
      {tab === 'types' ? <Types /> : <Examples />}
    </div>
  )
}
