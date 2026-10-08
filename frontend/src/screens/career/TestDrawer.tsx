/**
 * Окно теста профориентации по центру, широкое (решение владельца: тексты
 * утверждений должны читаться целиком): название, состояние, порог для
 * разбора, кому открыт, файл, шкалы, утверждения с ключом и интерпретация. Текст утверждений
 * и шкал здесь не правится — тест перезагружается файлом, иначе ключ разошёлся
 * бы с файлом (решение владельца, 08.10.2026). Удаление: без попыток — насовсем,
 * с попытками — в архив.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareerTest, useCareerTestDelete, useCareerTestPatch, type CareerTestRow } from '../../api/career'
import { downloadFile } from '../../api/client'
import ConfirmDialog from '../../components/ConfirmDialog'
import Modal from '../../components/Modal'
import Field from '../../components/Field'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Chip, ErrorNote, Loading } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Switch } from '../../components/ui/switch'
import { t, tn } from '../../i18n'
import { formatDate } from '../../lib/format'
import AssignDrawer from './AssignDrawer'

export default function TestDrawer({ row, manage, onClose }: { row: CareerTestRow; manage: boolean; onClose: () => void }) {
  const query = useCareerTest(row.id)
  const patch = useCareerTestPatch()
  const remove = useCareerTestDelete()
  const [title, setTitle] = useState(row.title)
  const [threshold, setThreshold] = useState(String(row.analysis_min_score))
  const [assigning, setAssigning] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const test = query.data
  const used = row.done + row.in_progress > 0
  const dirty = title.trim() !== row.title || Number(threshold) !== row.analysis_min_score
  const thresholdOk = Number.isInteger(Number(threshold)) && threshold.trim() !== ''

  const save = () =>
    patch.mutate(
      { id: row.id, ...(title.trim() !== row.title ? { title: title.trim() } : {}), ...(Number(threshold) !== row.analysis_min_score ? { analysis_min_score: Number(threshold) } : {}) },
      { onError: (error) => toast.error(error.message) },
    )
  const download = () => void downloadFile(`/career/tests/${row.id}/file/`, row.file_name || `career-test-${row.id}.xlsx`).catch((error: Error) => toast.error(error.message))

  if (assigning && test) return <AssignDrawer test={test} onClose={() => setAssigning(false)} />

  const groupsNote = (test?.groups ?? []).map((g) => (g.whole ? t('{group} — вся группа', { group: g.code }) : t('{group} — {n}', { group: g.code, n: tn(g.students.length, '{n} ученик|{n} ученика|{n} учеников') })))

  const foot = (
    <div className="toolbar ctest__foot">
      {manage && (
        <Button disabled={!dirty || !thresholdOk || patch.isPending} onClick={save}>
          {patch.isPending ? t('Сохраняется…') : t('Сохранить')}
        </Button>
      )}
      {manage && (
        <Button variant="outline" onClick={() => setDeleting(true)}>
          {used ? t('В архив') : t('Удалить')}
        </Button>
      )}
      <Button variant="outline" onClick={onClose}>
        {t('Закрыть')}
      </Button>
    </div>
  )

  return (
    <Modal wide title={row.title} note={[formatDate(row.created_at), row.created_by?.short ?? '', row.file_name].filter(Boolean).join(' · ')} onClose={onClose}>
      {query.isLoading && <Loading />}
      {query.error && <ErrorNote error={query.error} />}
      <div className="toolbar mb-0">
        <Chip size="sm" tone={row.is_active ? 'good' : 'neutral'}>
          {row.is_active ? t('включён') : t('выключен')}
        </Chip>
        <span className="t-note num">{[tn(row.items, '{n} утверждение|{n} утверждения|{n} утверждений'), tn(row.scales, '{n} шкала|{n} шкалы|{n} шкал'), t('сдали {done} из {total}', { done: row.done, total: row.assigned })].join(' · ')}</span>
        <Button variant="link" size="sm" onClick={download}>
          {t('Скачать файл')}
        </Button>
      </div>
      {manage && (
        <label className="field__check">
          <Switch checked={row.is_active} onCheckedChange={(on) => patch.mutate({ id: row.id, is_active: Boolean(on) }, { onError: (error) => toast.error(error.message) })} />
          <span className="field__checklabel">{t('Открыт ученикам')}</span>
        </label>
      )}
      {manage ? (
        <>
          <Field kind="text" name="title" label={t('Название')} value={title} onChange={setTitle} />
          <Field kind="number" name="threshold" label={t('Порог для разбора')} value={threshold} onChange={setThreshold} hint={t('Шкалы с баллом ниже порога в разбор модели не уходят')} error={thresholdOk ? undefined : t('Порог для разбора — целое число')} />
        </>
      ) : (
        <Field.Static label={t('Порог для разбора')}>{String(row.analysis_min_score)}</Field.Static>
      )}

      <span className="eyebrow">{t('Кому открыт тест')}</span>
      {groupsNote.length === 0 ? <p className="t-note">{t('никому не открыт')}</p> : (
        <Rows>
          {groupsNote.map((text) => (
            <Row key={text} icon="people" title={text} />
          ))}
        </Rows>
      )}
      {manage && (
        <div className="toolbar mb-0">
          <Button variant="secondary" size="sm" disabled={!test} onClick={() => setAssigning(true)}>
            {t('Кому')}
          </Button>
        </div>
      )}

      {test && test.instruction && (
        <>
          <span className="eyebrow">{t('Инструкция')}</span>
          <p className="acad__note">{test.instruction}</p>
        </>
      )}
      {test && test.options.length > 0 && (
        <>
          <span className="eyebrow">{t('Варианты ответа')}</span>
          <p className="t-note num">{test.options.map((option) => `${option.label} ${option.value}`).join(' · ')}</p>
        </>
      )}
      {test && (
        <>
          <span className="eyebrow">{t('Шкалы')}</span>
          <Rows>
            <ShowAll limit={6}>
              {test.scales.map((scale) => (
                <Row key={scale.id} title={scale.title} note={scale.code} />
              ))}
            </ShowAll>
          </Rows>
          <span className="eyebrow">{t('Утверждения')}</span>
          <Rows>
            <ShowAll limit={8}>
              {test.items.map((item) => (
                <Row key={item.id} lead={<b className="num ctake__num">{item.number}</b>} title={item.text} note={item.choices.length ? item.choices.map((c) => `${c.label} → ${c.scale}`).join(' · ') : `${item.scale}${item.sign < 0 ? ' −' : ''}`} />
              ))}
            </ShowAll>
          </Rows>
          {test.ranges.length > 0 && (
            <>
              <span className="eyebrow">{t('Интерпретация')}</span>
              <Rows>
                {test.ranges.map((range, i) => (
                  <Row key={i} title={range.label} note={[range.scale, `${range.low}…${range.high}`].filter(Boolean).join(' · ')} />
                ))}
              </Rows>
            </>
          )}
        </>
      )}
      {foot}
      <ConfirmDialog
        open={deleting}
        title={used ? t('Убрать тест «{title}» в архив?', { title: row.title }) : t('Удалить тест «{title}»?', { title: row.title })}
        what={used ? t('попытки и разборы учеников останутся, тест исчезнет из списков') : t('тест никто не проходил — он удалится вместе с файлом')}
        confirmLabel={used ? t('В архив') : t('Удалить')}
        busy={remove.isPending}
        onCancel={() => setDeleting(false)}
        onConfirm={() =>
          remove.mutate(row.id, {
            onSuccess: () => {
              setDeleting(false)
              onClose()
            },
            onError: (error) => toast.error(error.message),
          })
        }
      />
    </Modal>
  )
}
