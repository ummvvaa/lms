/**
 * Экран «Пробники» (фаза 63) — у куратора и у Кымбат.
 *
 * Пробник проводит учитель; аккаунта у него нет. Здесь список загрузок,
 * мастер «Загрузить пробник» и страница результатов по группе. Куратор
 * видит свои группы, Кымбат — все: границу держит сервер, а не этот экран.
 *
 * Средний по группе стоит только здесь и в ответе сотруднику: ученику
 * его не показывают нигде — сравнений между детьми у нас нет.
 */
import { useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { downloadFile } from '../../api/client'
import {
  useArchiveMock,
  useMockImports,
  useMockResults,
  useRemindMock,
  useRestoreMock,
} from '../../api/hooks'
import Modal from '../../components/Modal'
import { StatCard, StatRow } from '../../components/patterns'
import { ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import GroupSwitch from './GroupSwitch'
import MockWizard, { FormatDialog } from './MockWizard'
import { useGroup } from './state'
import './curator.css'

const SECTION_SHORT: Record<string, string> = {
  listening: 'L',
  reading: 'R',
  writing: 'W',
  speaking: 'S',
}

const dateOf = (raw: string) => new Date(raw).toLocaleDateString('ru')

/** Список загрузок. */
export default function MockImports() {
  const [group, setGroup] = useGroup()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const archived = params.get('archived') === 'true'
  const { data, isLoading, error } = useMockImports(group, archived)
  const [wizard, setWizard] = useState(false)
  const [format, setFormat] = useState(false)
  const restore = useRestoreMock()

  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const setArchived = (value: boolean) => {
    const updated = new URLSearchParams(params)
    if (value) updated.set('archived', 'true')
    else updated.delete('archived')
    setParams(updated, { replace: true })
  }

  return (
    <div>
      <ScreenHead
        title={t('Пробники')}
        subtitle={t('Пробник проводит учитель и присылает таблицу — вы загружаете её файлом.')}
        actions={
          <>
            <Button variant="outline" onClick={() => setFormat(true)}>
              {t('Формат файла')}
            </Button>
            {data.may_upload && <Button onClick={() => setWizard(true)}>{t('Загрузить пробник')}</Button>}
          </>
        }
      />
      <GroupSwitch groups={data.groups} value={group} onChange={setGroup} />

      <p className="cnote">
        {t(
          'Результаты ложатся сразу подтверждёнными, с пометкой кто загрузил. Ученик видит свой балл как «пробник школы» и не может его править. Официальный балл это не меняет: сертификат и пробник — две разные строки.',
        )}
      </p>

      <div className="cfilters">
        <button
          type="button"
          className={`cchip${archived ? '' : ' cchip--on'}`}
          onClick={() => setArchived(false)}
        >
          {t('Загруженные')}
        </button>
        <button
          type="button"
          className={`cchip${archived ? ' cchip--on' : ''}`}
          onClick={() => setArchived(true)}
        >
          {t('В архиве')}
        </button>
      </div>

      <div className="card card-pad">
        <div className="tblwrap">
          <table className="tbl">
            <colgroup>
              <col style={{ width: '12%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '16%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '18%' }} />
              <col style={{ width: '18%' }} />
              <col style={{ width: '12%' }} />
            </colgroup>
            <thead>
              <tr>
                <th>{t('Экзамен')}</th>
                <th>{t('Группа')}</th>
                <th>{t('Дата')}</th>
                <th className="r">{t('Учеников')}</th>
                <th>{t('Загрузил')}</th>
                <th>{t('Файл')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.results.map((row) => (
                <tr key={row.id}>
                  <td data-head="">
                    <b>{row.exam_type}</b>
                  </td>
                  <td data-label={t('Группа')}>{row.group}</td>
                  <td data-label={t('Дата')}>{dateOf(row.date)}</td>
                  <td data-label={t('Учеников')} className="r num">
                    {row.students}
                  </td>
                  <td data-label={t('Загрузил')}>
                    {row.uploaded_by}
                    {row.teacher && <span className="muted"> · {t('учитель')} {row.teacher}</span>}
                  </td>
                  <td data-label={t('Файл')} className="muted">
                    {row.file_name}
                  </td>
                  <td className="r">
                    <span className="ctasks__acts">
                      <Button variant="outline" size="sm" onClick={() => navigate(`/mock-imports/${row.id}`)}>
                        {t('Открыть')}
                      </Button>
                      {archived && data.may_restore && (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={restore.isPending}
                          onClick={() =>
                            restore.mutate(row.id, {
                              onSuccess: () => toast.success(t('Пробник вернулся из архива')),
                              onError: (e) => toast.error(e.message),
                            })
                          }
                        >
                          {t('Вернуть из архива')}
                        </Button>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.results.length === 0 && (
          <p className="muted">
            {archived ? t('В архиве пусто') : t('Пробников в этих группах ещё не загружали')}
          </p>
        )}
      </div>

      {wizard && (
        <MockWizard
          groups={data.groups}
          exams={data.exams}
          group={group}
          onClose={() => setWizard(false)}
          onDone={(id) => {
            setWizard(false)
            navigate(`/mock-imports/${id}`)
          }}
        />
      )}
      {format && <FormatDialog onClose={() => setFormat(false)} />}
    </div>
  )
}

/** Страница результатов одного пробника. */
export function MockResults() {
  const { id } = useParams()
  const navigate = useNavigate()
  const mockId = Number(id)
  const { data, isLoading, error } = useMockResults(Number.isFinite(mockId) ? mockId : null)
  const archive = useArchiveMock()
  const restore = useRestoreMock()
  const remind = useRemindMock()
  const [asking, setAsking] = useState(false)

  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const download = () =>
    void downloadFile(`/mock-imports/${data.id}/export/`, `пробник-${data.exam_type}-${data.group}.xlsx`).catch(() =>
      toast.error(t('Не удалось собрать файл')),
    )
  const original = () =>
    void downloadFile(`/mock-imports/${data.id}/file/`, data.file_name || 'mock.xlsx').catch(() =>
      toast.error(t('Не удалось скачать файл')),
    )

  return (
    <div>
      <Button variant="ghost" size="sm" onClick={() => navigate('/mock-imports')}>
        {t('← Пробники')}
      </Button>
      <ScreenHead
        title={`${data.exam_type} · ${data.group}`}
        subtitle={`${dateOf(data.date)} · ${t('загрузил')} ${data.uploaded_by}${
          data.teacher ? ` · ${t('учитель')} ${data.teacher}` : ''
        }`}
        actions={
          <>
            {data.status === 'archived' && <Badge variant="mute">{t('В архиве')}</Badge>}
            <Button variant="outline" onClick={original}>
              {t('Скачать исходник')}
            </Button>
            <Button variant="outline" onClick={download}>
              {t('Выгрузить')}
            </Button>
            {data.status === 'applied' && data.may_upload && (
              <Button variant="outline" onClick={() => setAsking(true)}>
                {t('В архив')}
              </Button>
            )}
            {data.status === 'archived' && data.may_restore && (
              <Button
                disabled={restore.isPending}
                onClick={() =>
                  restore.mutate(data.id, {
                    onSuccess: () => toast.success(t('Пробник вернулся из архива')),
                    onError: (e) => toast.error(e.message),
                  })
                }
              >
                {t('Вернуть из архива')}
              </Button>
            )}
          </>
        }
      />

      <StatRow>
        <StatCard icon="people" tone="ok" label={t('Сдавали')} value={data.took} />
        <StatCard
          icon="people"
          tone={data.missed ? 'warn' : 'mute'}
          label={t('Не сдавали')}
          value={data.missed}
          note={data.missed ? t('им можно напомнить') : t('сдали все')}
        />
        <StatCard
          icon="target"
          tone="indigo"
          label={t('Средний балл группы')}
          value={data.average ?? '—'}
          note={t('виден только вам и Кымбат')}
        />
      </StatRow>

      <div className="card card-pad">
        <div className="tblwrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>{t('Ученик')}</th>
                {data.sections.map((name) => (
                  <th key={name} className="r">
                    {SECTION_SHORT[name] ?? name}
                  </th>
                ))}
                <th className="r">{t('Балл')}</th>
                <th className="r">{t('Цель')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.results.map((row) => (
                <tr key={row.student}>
                  <td data-head="">
                    <a className="cdocs__name" href={`/students/${row.student}?tab=exams`}>
                      {row.full_name}
                    </a>
                  </td>
                  {data.sections.map((name) => (
                    <td key={name} data-label={name} className="r num">
                      {row.sections[name] ?? '—'}
                    </td>
                  ))}
                  <td data-label={t('Балл')} className="r num">
                    {row.total ?? <span className="muted">{t('не сдавал')}</span>}
                  </td>
                  <td data-label={t('Цель')} className="r num">
                    {row.target === null ? (
                      <span className="muted">{t('нет')}</span>
                    ) : (
                      <span className={row.below_target ? 'cstale' : ''}>{row.target}</span>
                    )}
                  </td>
                  <td className="r">
                    {row.below_target && <Badge variant="warn">{t('ниже цели')}</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.missed > 0 && data.may_upload && data.status === 'applied' && (
          <div className="ctask__actions">
            <Button
              variant="outline"
              disabled={remind.isPending}
              onClick={() =>
                remind.mutate(data.id, {
                  onSuccess: (result) =>
                    toast.success(`${t('Задача отправлена ученикам:')} ${result.created}`),
                  onError: (e) => toast.error(e.message),
                })
              }
            >
              {t('Напомнить не сдавшим')}
            </Button>
          </div>
        )}
      </div>

      {data.skipped_report.length > 0 && (
        <div className="card card-pad">
          <span className="eyebrow">{t('Пропущено при загрузке')}</span>
          <ul className="muted cmock__rules">
            {data.skipped_report.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="cnote">
        {t('Средний по группе виден только вам и Кымбат. Ученику показывается его результат — рейтингов между учениками нет.')}
      </p>

      {asking && (
        <Modal title={t('Убрать пробник в архив')} onClose={() => setAsking(false)}>
          <div className="ctask">
            <p>
              {t('Файл и результаты не удаляются — уходят в архив. У учеников баллы этого пробника скроются, из корзин он тоже пропадёт.')}
            </p>
            <p className="muted">{t('Вернуть сможет Кымбат или администратор.')}</p>
            <div className="ctask__actions">
              <Button variant="outline" onClick={() => setAsking(false)}>
                {t('Отмена')}
              </Button>
              <Button
                disabled={archive.isPending}
                onClick={() =>
                  archive.mutate(data.id, {
                    onSuccess: () => {
                      toast.success(t('Пробник в архиве'))
                      setAsking(false)
                      navigate('/mock-imports')
                    },
                    onError: (e) => toast.error(e.message),
                  })
                }
              >
                {t('В архив')}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
