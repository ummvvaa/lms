/**
 * Открытые ответы учеников — Writing и Speaking проверяет человек.
 *
 * Вариантов у этих секций нет, и верность машина не считает: ученик пишет
 * эссе или тезисы устного ответа, ответ сохраняется и ждёт здесь. Кымбат
 * читает его рядом с заданием и критериями, ставит оценку по шкале экзамена
 * и пишет комментарий — их ученик увидит в разборе тренировки. Имени
 * проверяющего ученик не видит.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useOpenAnswers, useReviewOpenAnswer, type OpenAnswerRow } from '../api/hooks'
import Empty from './Empty'
import Modal from './Modal'
import { Chip, DataCard, ErrorNote, Loading, ScreenTabs } from './ui'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Textarea } from './ui/textarea'
import { t } from '../i18n'

type State = 'waiting' | 'reviewed'

const limitOf = (row: OpenAnswerRow): string =>
  row.word_limit
    ? `${t('лимит слов')}: ${row.word_limit}`
    : row.minute_limit
      ? `${t('лимит минут')}: ${row.minute_limit}`
      : ''

function Review({ row, onClose }: { row: OpenAnswerRow; onClose: () => void }) {
  const review = useReviewOpenAnswer()
  const [score, setScore] = useState(row.score === null ? '' : String(row.score))
  const [comment, setComment] = useState(row.comment)

  return (
    <Modal
      title={`${row.student}${row.group ? ` · ${row.group}` : ''}`}
      note={`${row.exam_type} · ${row.section_title} · ${row.topic}`}
      wide
      onClose={onClose}
    >
      <div className="oans">
        <section>
          <span className="eyebrow">{t('Задание')}</span>
          <p className="oans__text">{row.task}</p>
          {limitOf(row) && <p className="muted">{limitOf(row)}</p>}
        </section>
        {row.criteria && (
          <section>
            <span className="eyebrow">{t('Критерии оценки')}</span>
            <p className="oans__text">{row.criteria}</p>
          </section>
        )}
        <section>
          <span className="eyebrow">
            {t('Ответ ученика')} · {t('слов')}: {row.words}
          </span>
          <p className="oans__text oans__answer">{row.answer}</p>
        </section>
        <div className="oans__form">
          <label className="qform__field">
            <span className="rowform__label">{t('Оценка по шкале экзамена')}</span>
            <Input
              className="num"
              inputMode="decimal"
              value={score}
              onChange={(event) => setScore(event.target.value)}
            />
          </label>
          <label className="qform__field qform__field--wide">
            <span className="rowform__label">{t('Комментарий — его увидит ученик')}</span>
            <Textarea rows={4} value={comment} onChange={(event) => setComment(event.target.value)} />
          </label>
        </div>
        <div className="rowform__actions">
          <Button variant="outline" size="sm" onClick={onClose}>
            {t('Отмена')}
          </Button>
          <Button
            size="sm"
            disabled={review.isPending}
            onClick={() =>
              review.mutate(
                { id: row.id, score: score.trim() === '' ? null : score.trim().replace(',', '.'), comment },
                {
                  onSuccess: () => {
                    toast.success(t('Проверка сохранена'))
                    onClose()
                  },
                  onError: (error) => toast.error(error.message),
                },
              )
            }
          >
            {t('Сохранить проверку')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function OpenAnswers() {
  const [state, setState] = useState<State>('waiting')
  const [opened, setOpened] = useState<OpenAnswerRow | null>(null)
  const list = useOpenAnswers(state)
  const rows = list.data?.results ?? []

  return (
    <DataCard
      title={t('Открытые ответы')}
      note={t('Writing и Speaking: ответ ученика ждёт вашей оценки и комментария')}
      count={list.data?.waiting ?? 0}
    >
      <ScreenTabs<State>
        value={state}
        onChange={setState}
        items={[
          { value: 'waiting', label: t('Ждут проверки') },
          { value: 'reviewed', label: t('Проверенные') },
        ]}
      />
      {list.isLoading && <Loading kind="table" />}
      {list.error && <ErrorNote error={list.error} />}
      {!list.isLoading && rows.length === 0 && (
        <Empty
          icon="doc"
          title={state === 'waiting' ? t('Проверять нечего') : t('Проверенных ответов пока нет')}
          what={t('Ответ появится здесь, когда ученик завершит тренировку по Writing или Speaking.')}
        />
      )}
      {rows.map((row) => (
        <div key={row.id} className="oans__row">
          <span className="oans__rowtext">
            <b>
              {row.student}
              {row.group ? ` · ${row.group}` : ''}
            </b>
            <span className="muted">
              {row.exam_type} · {row.section_title} · {row.topic} · {t('слов')}: {row.words}
            </span>
          </span>
          {row.reviewed && row.score !== null && (
            <Chip tone="good" className="num">
              {row.score}
            </Chip>
          )}
          <Button variant="outline" size="sm" onClick={() => setOpened(row)}>
            {row.reviewed ? t('Открыть') : t('Проверить')}
          </Button>
        </div>
      ))}
      {opened && <Review row={opened} onClose={() => setOpened(null)} />}
    </DataCard>
  )
}
