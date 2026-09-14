/**
 * История загрузок с отменой импорта целиком.
 *
 * Отмена работает тем же способом, что откат предложений: обратный набор
 * изменений через журнал. Поле, которое после загрузки правили руками,
 * откат не трогает и говорит об этом поимённо.
 */
import { useState } from 'react'
import {
  useCleanupHistory,
  useHistoryCleanupPreview,
  useImportBatches,
  useRevertImport,
  type ImportBatchRow,
  type RevertReport,
} from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { downloadFile } from '../api/client'
import { useAdmissionImports, type AdmissionImportReport } from '../api/hooks'
import ConfirmDialog from './ConfirmDialog'
import Modal from './Modal'
import { Chip, ErrorNote, Loading } from './ui'
import { t } from '../i18n'
import { SelectField } from './SelectField'
import { Input } from './ui/input'
import { Button } from './ui/button'
import { Badge } from './ui/badge'

const STATUS_TONE: Record<string, 'ok' | 'warn' | 'mute'> = {
  applied: 'ok',
  reverted: 'mute',
  partial: 'warn',
}

function when(value: string): string {
  return new Date(value).toLocaleString('ru', { dateStyle: 'short', timeStyle: 'short' })
}

/** Очистка истории: записи о загрузках уходят, правки в журнале остаются. */
function Cleanup() {
  const [open, setOpen] = useState(false)
  const [days, setDays] = useState(180)
  const [done, setDone] = useState<string | null>(null)
  const preview = useHistoryCleanupPreview(days, open)
  const cleanup = useCleanupHistory()

  if (!open) {
    return (
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        {t('Очистить историю…')}
      </Button>
    )
  }

  return (
    <div className="card card-pad imp__cleanup">
      <div className="row-between">
        <b>{t('Очистка истории загрузок')}</b>
        <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
          {t('Скрыть')}
        </Button>
      </div>
      <div className="toolbar" style={{ margin: '10px 0 0' }}>
        <label className="imp__filter">
          {t('Старше скольких дней')}
          <SelectField
            value={days}
            aria-label={t('Старше скольких дней')}
            onChange={(event) => setDays(Number(event.target.value))}
          >
            {[30, 90, 180, 365].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </SelectField>
        </label>
        <Button
          size="sm"
          disabled={(preview.data?.entries ?? 0) === 0 || cleanup.isPending}
          onClick={() => cleanup.mutate(days, { onSuccess: (result) => setDone(result.detail) })}
        >
          {t('Очистить')}
        </Button>
      </div>
      {preview.data && <p className="muted imp__sub">{preview.data.detail}</p>}
      {done && (
        <Badge variant="ok" className="badge--line">
          {done}
        </Badge>
      )}
    </div>
  )
}

function Row({ row, onReverted }: { row: ImportBatchRow; onReverted: (report: RevertReport) => void }) {
  const [ask, setAsk] = useState(false)
  const revert = useRevertImport()

  return (
    <article className="card card-pad imp__row">
      <div className="row-between imp__head">
        <div>
          <b>{row.file_name || row.kind_title}</b>
          <p className="muted imp__sub">
            {/* пусто — загрузка старше фазы 29: тогда автора не записывали.
                Новые записи приходят с именем всегда */}
            {row.actor_name || 'автор не сохранён'}
            {/* файл залил не владелец домена — администратор за домен (фаза 35):
                директор должен видеть, откуда взялись значения, которых он не вносил */}
            {row.on_behalf && row.domain_title && (
              <span className="imp__behalf"> · администратор за домен «{row.domain_title}»</span>
            )}
            {' · '}
            {when(row.created_at)} · строк в файле {row.rows_total}
          </p>
        </div>
        <div className="imp__chips">
          {row.domain_title && <Chip tone="mute">{row.domain_title}</Chip>}
          <Chip tone={STATUS_TONE[row.status] ?? 'mute'}>{row.status_title}</Chip>
        </div>
      </div>

      <p className="muted imp__sub">
        Изменено записей: {row.rows_updated}
        {row.rows_created > 0 && ` · создано: ${row.rows_created}`}
        {row.rows_failed > 0 && ` · с ошибкой: ${row.rows_failed}`} · правок в журнале: {row.changes}
      </p>
      {row.note && <p className="muted imp__sub">{row.note}</p>}

      {row.status === 'applied' && (
        <div className="imp__actions">
          <Button variant="destructive" size="sm" onClick={() => setAsk(true)}>
            {t('Отменить импорт')}
          </Button>
          {revert.isError && <ErrorNote error={revert.error} />}
        </div>
      )}

      <ConfirmDialog
        open={ask}
        title={`Отменить загрузку «${row.file_name || row.kind_title}»?`}
        what={`Прежние значения вернутся у ${row.changes} полей.`}
        consequences={[
          'Поля, которые правили руками уже после загрузки, останутся как есть — о каждом скажем отдельно',
          'Возврат тоже попадёт в журнал изменений: по строке на каждое поле',
          row.rows_created > 0
            ? `Записи, созданные этой загрузкой (${row.rows_created}), отмена не удаляет`
            : 'Загрузка ничего не создавала — только меняла значения',
        ]}
        confirmLabel={t('Отменить импорт')}
        busy={revert.isPending}
        error={revert.isError ? (revert.error as Error).message : null}
        onCancel={() => setAsk(false)}
        onConfirm={() =>
          revert.mutate(row.id, {
            onSuccess: (report) => {
              setAsk(false)
              onReverted(report)
            },
          })
        }
      />
    </article>
  )
}

/** Столько загрузок показываем сразу: остальное — по кнопке. */
const VISIBLE = 5

/** Подписи доменов для чипов истории — те же слова, что в реестре доменов. */
const DOMAIN_TITLES: Record<string, string> = {
  behavior: 'Профиль и дисциплина',
  admission: 'Поступление',
  exam: 'Экзамены',
  talent: 'Таланты',
  sport: 'Спорт',
  documents: 'Документы',
}

export default function ImportHistory() {
  const { me } = useAuth()
  const isAdmin = me?.role === 'admin'
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [all, setAll] = useState(false)
  const [report, setReport] = useState<RevertReport | null>(null)
  const list = useImportBatches({ since, until })
  // загрузки мастера (фаза 72) — в тот же список, вид загрузки колонкой
  const wizard = useAdmissionImports()
  const [opened, setOpened] = useState<AdmissionImportReport | null>(null)
  const rows = list.data ?? []
  const shown = all ? rows : rows.slice(0, VISIBLE)
  const wizardRows = (wizard.data?.rows ?? []).filter((row) => {
    const day = row.created_at.slice(0, 10)
    return (!since || day >= since) && (!until || day <= until)
  })

  return (
    <section className="card card-pad imp">
      <div className="row-between imp__toolbar">
        <span className="eyebrow">{t('История загрузок')}</span>
        <div className="imp__filters">
          <label className="imp__filter">
            {t('с')}
            <Input
              type="date"
              value={since}
              aria-label={t('Загрузки с даты')}
              onChange={(event) => setSince(event.target.value)}
            />
          </label>
          <label className="imp__filter">
            {t('по')}
            <Input
              type="date"
              value={until}
              aria-label={t('Загрузки по дату')}
              onChange={(event) => setUntil(event.target.value)}
            />
          </label>
        </div>
      </div>

      {isAdmin && <Cleanup />}

      {report && (
        <div className="imp__report">
          <Badge variant="ok" className="badge--line">
            {report.detail}
          </Badge>
          {report.skipped.length > 0 && (
            <ul className="imp__skipped">
              {report.skipped.map((item) => (
                <li key={item.entry}>
                  {item.field_title}: {item.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {list.isLoading && <Loading kind="table" />}
      {list.isError && <ErrorNote error={list.error} />}

      {!list.isLoading && rows.length === 0 && (
        <p className="muted imp__empty">
          {isAdmin
            ? t(
                'Загрузок пока не было. Каждый применённый файл попадёт сюда, и его можно будет отменить целиком.',
              )
            : t(
                'По вашему домену загрузок ещё не было. Когда администратор загрузит файл, он появится здесь, и его можно будет отменить.',
              )}
        </p>
      )}

      <div className="imp__list">
        {wizardRows.map((row) => (
          <article key={`wizard-${row.id}`} className="card card-pad imp__row">
            <div className="row-between imp__head">
              <div>
                <b>{row.file_name || t('файл без имени')}</b>
                <p className="muted imp__sub">
                  {row.uploaded_by || t('автор не сохранён')} · {when(row.created_at)} · {t('листов')} {row.sheets}
                </p>
              </div>
              <div className="imp__chips">
                <Chip tone="brand">{t('мастер импорта')}</Chip>
                {row.domains.map((code) => (
                  <Chip key={code} tone="mute">
                    {DOMAIN_TITLES[code] ?? code}
                  </Chip>
                ))}
              </div>
            </div>
            <p className="muted imp__sub">
              {t('Учеников обновлено:')} {row.students_updated} · {t('попыток')} {row.attempts_created} ·{' '}
              {t('документов')} {row.documents_created} · {t('паролей')} {row.credentials_saved}
              {row.rows_skipped > 0 && ` · ${t('пропущено строк')} ${row.rows_skipped}`}
            </p>
            <div className="imp__actions">
              <Button variant="outline" size="sm" onClick={() => setOpened(row)}>
                {t('Открыть отчёт')}
              </Button>
            </div>
          </article>
        ))}
        {shown.map((row) => (
          <Row key={row.id} row={row} onReverted={setReport} />
        ))}
      </div>

      {opened && (
        <Modal title={`${t('Отчёт о загрузке')} · ${opened.file_name}`} onClose={() => setOpened(null)} wide>
          <ul className="wizard__domains">
            {opened.rows
              .filter((row) => row.kind === 'домен')
              .map((row) => (
                <li key={row.text}>{row.text}</li>
              ))}
          </ul>
          {opened.rows.filter((row) => row.kind !== 'домен').length === 0 && (
            <p className="muted">{t('Всё загрузилось без замечаний')}</p>
          )}
          {opened.rows.filter((row) => row.kind !== 'домен').length > 0 && (
            <div className="tblwrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>{t('Лист')}</th>
                    <th>{t('Строка')}</th>
                    <th>{t('Ученик')}</th>
                    <th>{t('Что случилось')}</th>
                  </tr>
                </thead>
                <tbody>
                  {opened.rows
                    .filter((row) => row.kind !== 'домен')
                    .map((row, index) => (
                      <tr key={index}>
                        <td>{row.sheet}</td>
                        <td className="num">{row.row}</td>
                        <td>{row.student}</td>
                        <td>{row.text}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="ctask__actions">
            <span className="cfilters__spacer" />
            <Button
              size="sm"
              variant="outline"
              onClick={() => void downloadFile(`/admission-imports/${opened.id}/export/`, 'otchet-importa.xlsx')}
            >
              {t('Скачать отчёт')}
            </Button>
          </div>
        </Modal>
      )}

      {rows.length > VISIBLE && (
        <Button variant="outline" size="sm" className="queue__more" onClick={() => setAll(!all)}>
          {all ? 'Показать только последние' : `Показать все — ещё ${rows.length - VISIBLE}`}
        </Button>
      )}
    </section>
  )
}
