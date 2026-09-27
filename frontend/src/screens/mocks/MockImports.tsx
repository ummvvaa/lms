/**
 * Экран «Пробники» (фаза 63) — у Кымбат и администратора.
 *
 * Пробник проводит учитель; аккаунта у него нет. Здесь список загрузок,
 * мастер «Загрузить пробник» и страница результатов по группе. Куратор
 * файлом не грузит: он вносит балл пробника руками в карточке ученика,
 * и раздел ему закрыт на сервере.
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
  type MockImportRow,
  type MockResultRow,
} from '../../api/hooks'
import ConfirmDialog from '../../components/ConfirmDialog'
import DataTable, { type Column } from '../../components/DataTable'
import { ExportPreview } from '../../components/ExportPreview'
import Notice from '../../components/Notice'
import { Segmented, StatRow } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { GroupPick } from '../academics/shared'
import { useGroup } from '../curator/state'
import MockWizard, { FormatDialog } from './MockWizard'
import './mocks.css'

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

  const columns: Column<MockImportRow>[] = [
    { key: 'exam', title: t('Экзамен'), width: '12%', cell: (row) => <b>{row.exam_type}</b>, sortBy: (row) => row.exam_type },
    { key: 'group', title: t('Группа'), width: '12%', cell: (row) => row.group, sortBy: (row) => row.group },
    { key: 'date', title: t('Дата'), width: '14%', cell: (row) => <span className="num">{dateOf(row.date)}</span>, sortBy: (row) => row.date },
    { key: 'students', title: t('Учеников'), width: '10%', align: 'right', cell: (row) => <span className="num">{row.students}</span>, sortBy: (row) => row.students },
    {
      key: 'who',
      title: t('Загрузил'),
      width: '20%',
      cell: (row) => (
        <>
          {row.uploaded_by}
          {row.teacher && <span className="t-note"> · {t('учитель')} {row.teacher}</span>}
        </>
      ),
    },
    { key: 'file', title: t('Файл'), width: '18%', cell: (row) => <span className="t-note">{row.file_name}</span> },
    {
      key: 'acts',
      title: '',
      width: '14%',
      align: 'right',
      cell: (row) =>
        archived && data.may_restore ? (
          <Button
            variant="secondary"
            size="sm"
            disabled={restore.isPending}
            onClick={(event) => {
              event.stopPropagation()
              restore.mutate(row.id, {
                onSuccess: () => toast.success(t('Пробник вернулся из архива')),
                onError: (e) => toast.error(e.message),
              })
            }}
          >
            {t('Вернуть из архива')}
          </Button>
        ) : (
          <Button variant="outline" size="sm" onClick={() => navigate(`/mock-imports/${row.id}`)}>
            {t('Открыть')}
          </Button>
        ),
    },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Пробники')}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => setFormat(true)}>
              {t('Формат файла')}
            </Button>
            {data.may_upload && (
              <Button size="sm" onClick={() => setWizard(true)}>
                {t('Загрузить пробник')}
              </Button>
            )}
          </>
        }
      />
      <div className="acad__toolbar">
        <GroupPick groups={data.groups} value={group} onChange={setGroup} all={t('Все группы')} />
        <Segmented
          value={archived ? 'archived' : 'live'}
          onChange={(next) => setArchived(next === 'archived')}
          label={t('Какие загрузки')}
          items={[
            { value: 'live', label: t('Загруженные') },
            { value: 'archived', label: t('В архиве') },
          ]}
        />
      </div>

      <Notice className="cnote">
        {t(
          'Результаты ложатся сразу подтверждёнными, с пометкой кто загрузил. Ученик видит свой балл как «пробник школы» и не может его править. Официальный балл это не меняет: сертификат и пробник — две разные строки.',
        )}
      </Notice>

      <div className="card">
        <DataTable
          columns={columns}
          rows={data.results}
          rowKey={(row) => row.id}
          onRowClick={(row) => navigate(`/mock-imports/${row.id}`)}
          empty={<span className="t-note">{archived ? t('В архиве пусто') : t('Пробников в этих группах ещё не загружали')}</span>}
        />
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
  const [exporting, setExporting] = useState(false)

  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const original = () =>
    void downloadFile(`/mock-imports/${data.id}/file/`, data.file_name || 'mock.xlsx').catch(() =>
      toast.error(t('Не удалось скачать файл')),
    )

  const columns: Column<MockResultRow>[] = [
    { key: 'name', title: t('Ученик'), width: '30%', cell: (row) => <b>{row.full_name}</b>, sortBy: (row) => row.full_name },
    ...data.sections.map((name) => ({
      key: name,
      title: SECTION_SHORT[name] ?? name,
      width: '9%',
      align: 'right' as const,
      cell: (row: MockResultRow) => <span className="num">{row.sections[name] ?? t('нет')}</span>,
      sortBy: (row: MockResultRow) => row.sections[name],
    })),
    { key: 'total', title: t('Балл'), width: '12%', align: 'right', cell: (row) => (row.total === null ? <span className="t-note">{t('не сдавал')}</span> : <b className="num">{row.total}</b>), sortBy: (row) => row.total },
    { key: 'target', title: t('Цель'), width: '10%', align: 'right', cell: (row) => (row.target === null ? <span className="t-note">{t('нет')}</span> : <span className={`num${row.below_target ? ' cstale' : ''}`}>{row.target}</span>), sortBy: (row) => row.target },
    { key: 'flag', title: '', width: '12%', cell: (row) => (row.below_target ? <Chip tone="warn" size="sm">{t('ниже цели')}</Chip> : null) },
  ]

  return (
    <div>
      <ScreenHead
        title={`${data.exam_type} · ${data.group}`}
        crumb={{ label: t('Пробники'), to: '/mock-imports' }}
        subtitle={`${dateOf(data.date)} · ${t('загрузил')} ${data.uploaded_by}${data.teacher ? ` · ${t('учитель')} ${data.teacher}` : ''}`}
        pills={data.status === 'archived' ? [{ label: t('В архиве') }] : undefined}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={original}>
              {t('Скачать исходник')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setExporting(true)}>
              {t('Выгрузить')}
            </Button>
            {data.status === 'applied' && data.may_upload && (
              <Button variant="outline" size="sm" onClick={() => setAsking(true)}>
                {t('В архив')}
              </Button>
            )}
            {data.status === 'archived' && data.may_restore && (
              <Button
                size="sm"
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
        <Kpi tone="good" label={t('Сдавали')} value={data.took} />
        <Kpi
          tone={data.missed ? 'warn' : 'neutral'}
          label={t('Не сдавали')}
          value={data.missed || null}
          none={t('сдали все')}
          note={data.missed ? t('им можно напомнить') : undefined}
          action={data.missed > 0 && data.may_upload && data.status === 'applied' ? {
            label: t('Напомнить'),
            onClick: () =>
              remind.mutate(data.id, {
                onSuccess: (result) => toast.success(`${t('Задача отправлена ученикам:')} ${result.created}`),
                onError: (e) => toast.error(e.message),
              }),
          } : undefined}
        />
        <Kpi label={t('Средний балл группы')} value={data.average} none={t('нет')} note={t('виден только сотрудникам')} />
      </StatRow>

      <div className="card">
        <DataTable columns={columns} rows={data.results} rowKey={(row) => row.student} onRowClick={(row) => navigate(`/students/${row.student}?tab=exams`)} empty={<span className="t-note">{t('результатов нет')}</span>} />
      </div>

      {data.skipped_report.length > 0 && (
        <DataCard title={t('Пропущено при загрузке')} count={data.skipped_report.length}>
          <ul className="mocks__rules t-note">
            {data.skipped_report.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </DataCard>
      )}

      <Notice className="cnote">
        {t(
          'Средний по группе виден только сотрудникам. Ученику показывается его результат — рейтингов между учениками нет.',
        )}
      </Notice>

      <ConfirmDialog
        open={asking}
        title={t('Убрать пробник в архив')}
        what={t('Файл и результаты не удаляются — уходят в архив. У учеников баллы этого пробника скроются, из корзин он тоже пропадёт.')}
        consequences={[t('Вернуть сможет Кымбат или администратор.')]}
        confirmLabel={t('В архив')}
        busy={archive.isPending}
        onCancel={() => setAsking(false)}
        onConfirm={() =>
          archive.mutate(data.id, {
            onSuccess: () => {
              toast.success(t('Пробник в архиве'))
              setAsking(false)
              navigate('/mock-imports')
            },
            onError: (e) => toast.error(e.message),
          })
        }
      />

      {exporting && (
        <ExportPreview
          path={`/mock-imports/${data.id}/export/`}
          fallback={`пробник-${data.exam_type}-${data.group}.xlsx`}
          title={t('Выгрузка результатов пробника')}
          onClose={() => setExporting(false)}
        />
      )}
    </div>
  )
}
