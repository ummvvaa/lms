/**
 * «Эссе учеников» — директор по поступлению (макет AEssays, 24.10.2026).
 *
 * Видны только законченные эссе 11 класса — ученик отправил на проверку.
 * Слева список, справа текст выбранного (на чтение: текст правит только
 * ученик) и решение «Норм / Не норм» с комментарием, который ученик увидит
 * у себя в эссе. «Норм» — эссе готово, «Не норм» — на правки.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router'
import { useEssayReview, useEssayReviewDetail, useEssayVerdict, type EssayReviewRow } from '../../api/directors'
import Field from '../../components/Field'
import { Avatar, Segmented, ShowAll } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'
import { formatDateTime } from '../../lib/format'
import './directors.css'

type Filter = 'wait' | 'ok' | 'not_ok' | 'all'

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'wait', label: tk('Ждут проверки') },
  { value: 'ok', label: tk('Норм') },
  { value: 'not_ok', label: tk('Не норм') },
  { value: 'all', label: tk('Все') },
]

const matches = (filter: Filter, row: EssayReviewRow) =>
  filter === 'all' || (filter === 'wait' ? !row.verdict : row.verdict === filter)

function verdictChip(row: EssayReviewRow): { label: string; tone: Tone } {
  if (row.verdict === 'ok') return { label: t('норм'), tone: 'good' }
  if (row.verdict === 'not_ok') return { label: t('не норм'), tone: 'warn' }
  return { label: t('ждёт проверки'), tone: 'accent' }
}

export default function EssayReview() {
  const { data, isLoading, error } = useEssayReview()
  const [params, setParams] = useSearchParams()
  const [filter, setFilter] = useState<Filter>('wait')
  const [group, setGroup] = useState('')
  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const rows = data.rows.filter((row) => matches(filter, row) && (!group || row.student.group === group))
  const picked = Number(params.get('open')) || rows[0]?.id || null
  const pick = (id: number) => setParams({ open: String(id) }, { replace: true })

  return (
    <div className="lay-screen">
      <ScreenHead title={t('Эссе учеников')} subtitle={t('законченные эссе 11 классов · ученик отправил на проверку')} />
      <div className="filters">
        <Segmented
          value={filter}
          onChange={setFilter}
          label={t('Какие эссе')}
          items={FILTERS.map((item) => ({
            value: item.value,
            label: (
              <>
                {t(item.label)}
                <span className="tabs__n num">{data.rows.filter((row) => matches(item.value, row)).length}</span>
              </>
            ),
          }))}
        />
        <Field
          usageFilter
          kind="select"
          name="group"
          label={t('Группа')}
          value={group}
          onChange={setGroup}
          placeholder={t('Все 11 классы')}
          options={data.groups.map((code) => ({ value: code, title: code }))}
        />
      </div>
      <div className="lay-main lay-main--even">
        <DataCard title={t(FILTERS.find((item) => item.value === filter)?.label ?? '')} count={rows.length || undefined} empty={rows.length === 0 && t('с таким фильтром эссе нет')}>
          <div className="dir__rows">
            <ShowAll limit={8}>
              {rows.map((row) => {
                const chip = verdictChip(row)
                return (
                  <div key={row.id} className="dir__row">
                    <Avatar name={row.student.full_name} />
                    <span className="dir__what">
                      <b>{`${row.student.short_name} · ${row.student.group}`}</b>
                      <span className="t-note">
                        {[row.kind, tn(row.words, '{n} слово|{n} слова|{n} слов'), row.submitted_at ? formatDateTime(row.submitted_at) : ''].filter(Boolean).join(' · ')}
                      </span>
                    </span>
                    <Chip tone={chip.tone} size="sm">
                      {chip.label}
                    </Chip>
                    <span className="dir__acts">
                      <Button variant={row.id === picked ? 'secondary' : 'ghost'} size="sm" onClick={() => pick(row.id)}>
                        {t('Открыть')}
                      </Button>
                    </span>
                  </div>
                )
              })}
            </ShowAll>
          </div>
        </DataCard>
        {picked !== null && <EssayPanel id={picked} key={picked} />}
      </div>
    </div>
  )
}

function EssayPanel({ id }: { id: number }) {
  const { data, isLoading, error } = useEssayReviewDetail(id)
  const verdict = useEssayVerdict()
  const [comment, setComment] = useState('')
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const decide = (value: 'ok' | 'not_ok') =>
    verdict.mutate(
      { id, verdict: value, comment },
      {
        onSuccess: () => {
          setComment('')
          toast.success(
            value === 'ok'
              ? t('{name} · эссе отмечено «Норм»', { name: data.student.short_name })
              : t('{name} · эссе отмечено «Не норм», ученик увидит комментарий', { name: data.student.short_name }),
          )
        },
      },
    )
  const limit = data.word_limit ? ` / ${data.word_limit}` : ''
  return (
    <DataCard
      className="card--beam"
      title={data.title}
      note={[`${data.student.short_name} · ${data.student.group}`, data.kind, `${data.words}${limit}`, data.program].filter(Boolean).join(' · ')}
    >
      <div className="dir__essay">{data.text}</div>
      {data.comments.length > 0 && (
        <div className="dir__lines">
          {data.comments.slice(-3).map((c, index) => (
            <div key={index} className="dir__line">
              <span>{c.text}</span>
              <span className="t-note">{`${c.author} · ${formatDateTime(c.at)}`}</span>
            </div>
          ))}
        </div>
      )}
      <Field kind="textarea" name="essay-comment" label={t('Комментарий ученику')} value={comment} onChange={setComment} rows={3} placeholder={t('Что поправить — ученик увидит это у себя в эссе')} />
      {verdict.error && <ErrorNote error={verdict.error} />}
      <div className="acad__actions">
        <Button variant="outline" disabled={verdict.isPending || !comment.trim()} onClick={() => decide('not_ok')}>
          {t('Не норм')}
        </Button>
        <Button disabled={verdict.isPending} onClick={() => decide('ok')}>
          {t('Норм')}
        </Button>
      </div>
    </DataCard>
  )
}
