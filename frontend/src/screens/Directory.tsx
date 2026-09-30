/**
 * Справочник вузов глазами директора по поступлению.
 *
 * Здесь видно, откуда взялась каждая запись и подтверждена ли она
 * (инвариант №14). Стартовый справочник — заготовка: он заводится одной
 * кнопкой и одной же кнопкой убирается целиком, не задевая то,
 * что школа завела руками.
 *
 * Вид (решение владельца, 27.09.2026): вузы таблицей на всю ширину;
 * выбранный вуз открывается широкой панелью справа — сведения,
 * подтверждение данных и программы таблицей (программа, требования,
 * раунды, действия). Главное действие в шапке одно — «Добавить вуз»,
 * стартовый справочник — в меню «Ещё».
 */
import { useState } from 'react'
import { toast } from 'sonner'
import {
  useCreateSeedCatalog,
  useCreateUniversity,
  useDirectory,
  useDropSeedCatalog,
  useSeedStats,
  useUpdateUniversity,
  useVerifyRecord,
  type DirectoryUniversity,
} from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import ConfirmDialog from '../components/ConfirmDialog'
import DataTable, { type Column } from '../components/DataTable'
import DeleteButton from '../components/DeleteButton'
import EditDrawer from '../components/EditDrawer'
import Field from '../components/Field'
import PhoneFold from '../components/PhoneFold'
import ProgramList from '../components/ProgramList'
import RowForm from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { Row, Rows } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead, UnverifiedNote } from '../components/ui'
import { Button } from '../components/ui/button'
import { t, tk, tn } from '../i18n'
import './academics/academics.css'
import './directory.css'

const SOURCE_TITLES: Record<string, string> = {
  school: tk('Заведено школой'),
  seed: tk('Стартовый справочник'),
  import: tk('Импорт файла'),
  sync: tk('Фоновая сверка'),
}

/** Правка вуза: название, страна, сайт, домен. */
function UniversityForm({ row, onClose }: { row: DirectoryUniversity; onClose: () => void }) {
  const update = useUpdateUniversity()
  const [draft, setDraft] = useState({ name: row.name, country: row.country, website: row.website ?? '', domain: row.domain ?? '' })
  const [problem, setProblem] = useState<string | null>(null)
  return (
    <div className="acad__form">
      <Field name="name" label={t('Название')} value={draft.name} required error={problem ?? undefined} onChange={(value) => setDraft({ ...draft, name: value })} />
      <Field name="country" label={t('Страна')} value={draft.country} onChange={(value) => setDraft({ ...draft, country: value })} />
      <Field name="website" label={t('Сайт')} value={draft.website} onChange={(value) => setDraft({ ...draft, website: value })} />
      <Field name="domain" label={t('Домен')} value={draft.domain} placeholder="utoronto.ca" onChange={(value) => setDraft({ ...draft, domain: value })} />
      <div className="acad__actions">
        <Button
          disabled={update.isPending}
          onClick={() => {
            if (!draft.name.trim()) {
              setProblem(t('Название — обязательное поле'))
              return
            }
            update.mutate({ id: row.id, ...draft, name: draft.name.trim() }, { onSuccess: onClose, onError: (e) => setProblem(String((e as Error).message)) })
          }}
        >
          {t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </div>
  )
}

/** Широкая панель выбранного вуза: сведения, подтверждение, программы таблицей. */
function UniversityDrawer({ row, canEdit, onClose }: { row: DirectoryUniversity; canEdit: boolean; onClose: () => void }) {
  const verify = useVerifyRecord()
  const [editing, setEditing] = useState(false)
  return (
    <EditDrawer
      open
      onClose={onClose}
      className="drawer--xwide"
      title={row.name}
      sub={`${row.country}${row.domain ? ` · ${row.domain}` : ''} · ${t(SOURCE_TITLES[row.data_source] ?? row.data_source)}`}
      footer={
        canEdit ? (
          <>
            <Button variant={row.is_verified ? 'outline' : 'default'} disabled={verify.isPending} onClick={() => verify.mutate({ kind: 'university', id: row.id, verified: !row.is_verified }, { onSuccess: (answer) => toast.success(answer.detail), onError: (error) => toast.error(error.message) })}>
              {row.is_verified ? t('Снять подтверждение') : t('Подтвердить данные')}
            </Button>
            <Button variant="outline" onClick={() => setEditing(!editing)}>
              {editing ? t('Скрыть правку') : t('Изменить вуз')}
            </Button>
            <DeleteButton model="universities.University" id={row.id} path="/universities/" invalidate={[['universities'], ['catalog']]} label={t('Удалить вуз')} onDeleted={onClose} />
          </>
        ) : undefined
      }
    >
      <div className="acad__form">
        {editing ? (
          <UniversityForm key={row.id} row={row} onClose={() => setEditing(false)} />
        ) : (
          <Rows>
            <Row title={t('Данные')} value={row.is_verified ? <Chip tone="good" size="sm">{t('подтверждено')}</Chip> : <Chip tone="warn" size="sm">{t('не подтверждено')}</Chip>} />
            {row.website && <Row title={t('Сайт')} value={row.website} />}
          </Rows>
        )}
        {!row.is_verified && <UnverifiedNote note={row.verification_note} website={row.website} />}
        <ProgramList universityId={row.id} canEdit={canEdit} />
      </div>
    </EditDrawer>
  )
}

export default function Directory() {
  const { me } = useAuth()
  const canEdit = me?.role === 'director_admission'
  const [search, setSearch] = useState('')
  const [askDrop, setAskDrop] = useState(false)
  const [adding, setAdding] = useState(false)
  const [pickedId, setPickedId] = useState<number | null>(null)

  const create = useCreateUniversity()
  const list = useDirectory(search)
  const stats = useSeedStats(canEdit)
  const createSeed = useCreateSeedCatalog()
  const dropSeed = useDropSeedCatalog()

  const rows = list.data?.results ?? []
  const picked = rows.find((row) => row.id === pickedId) ?? null
  const seedCount = stats.data?.universities ?? 0
  const held = stats.data?.held_by_students ?? 0

  const columns: Column<DirectoryUniversity>[] = [
    { key: 'name', title: t('Вуз'), width: '40%', cell: (row) => <b>{row.name}</b>, sortBy: (row) => row.name.toLowerCase() },
    { key: 'country', title: t('Страна'), width: '18%', cell: (row) => row.country, sortBy: (row) => row.country },
    { key: 'source', title: t('Источник'), width: '22%', cell: (row) => <Chip tone={row.data_source === 'seed' ? 'warn' : 'neutral'} size="sm">{t(SOURCE_TITLES[row.data_source] ?? row.data_source)}</Chip>, sortBy: (row) => row.data_source },
    {
      key: 'verified',
      title: t('Данные'),
      width: '20%',
      cell: (row) => (row.is_verified ? <Chip tone="good" size="sm">{t('подтверждено')}</Chip> : <Chip tone="warn" size="sm">{t('не подтверждено')}</Chip>),
      sortBy: (row) => (row.is_verified ? 0 : 1),
    },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Вузы и программы')}
        pills={[
          { label: t('Найдено: {count}', { count: list.data?.count ?? 0 }) },
          ...(canEdit && seedCount > 0 ? [{ label: t('Заготовка: {count}', { count: seedCount }) }] : []),
        ]}
        actions={
          canEdit ? (
            <>
              <Button onClick={() => setAdding(true)}>{t('Добавить вуз')}</Button>
              <RowMenu>
                <RowMenuItem disabled={createSeed.isPending} onClick={() => createSeed.mutate(undefined, { onSuccess: (answer) => toast.success(answer.detail), onError: (error) => toast.error(error.message) })}>
                  {t('Заполнить стартовый справочник')}
                </RowMenuItem>
                {seedCount > 0 && (
                  <RowMenuItem risk onClick={() => setAskDrop(true)}>
                    {t('Удалить заготовку')}
                  </RowMenuItem>
                )}
              </RowMenu>
            </>
          ) : undefined
        }
      />

      <div className="acad__stack">
        <PhoneFold active={Boolean(search)}>
          <div className="acad__toolbar">
            <Field name="search" label={t('Поиск')} value={search} placeholder={t('Найти вуз по названию или стране')} onChange={setSearch} />
          </div>
        </PhoneFold>
        {list.isLoading && <Loading kind="table" />}
        {list.isError && <ErrorNote error={list.error} />}
        <DataCard
          title={t('Вузы')}
          count={list.data?.count || undefined}
          empty={!list.isLoading && rows.length === 0 && (search ? t('по этому поиску ничего нет') : t('вузов пока нет'))}
          emptyAction={
            canEdit && !search ? (
              <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
                {t('Добавить вуз')}
              </Button>
            ) : undefined
          }
        >
          <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} onRowClick={(row) => setPickedId(row.id)} selected={(row) => row.id === picked?.id} limit={20} />
        </DataCard>
      </div>

      {picked && <UniversityDrawer key={picked.id} row={picked} canEdit={canEdit} onClose={() => setPickedId(null)} />}

      <EditDrawer open={adding} onClose={() => setAdding(false)} title={t('Новый вуз')}>
        <RowForm
          fields={[
            { name: 'name', label: t('Название вуза'), kind: 'text', required: true },
            { name: 'country', label: t('Страна'), kind: 'text', required: true },
            { name: 'website', label: t('Сайт'), kind: 'text' },
            { name: 'domain', label: t('Домен сайта'), kind: 'text', placeholder: 'utoronto.ca' },
          ]}
          busy={create.isPending}
          submitLabel={t('Завести')}
          onCancel={() => setAdding(false)}
          onSubmit={(values) =>
            create.mutate(
              { name: String(values.name ?? ''), country: String(values.country ?? ''), website: String(values.website ?? ''), domain: String(values.domain ?? '') },
              {
                onSuccess: (row) => {
                  setAdding(false)
                  setPickedId(row.id)
                },
                onError: (error) => toast.error(error.message),
              },
            )
          }
        />
      </EditDrawer>

      <ConfirmDialog
        open={askDrop}
        title={t('Удалить стартовый справочник?')}
        what={tn(
          seedCount,
          'Уйдёт {n} вуз заготовки со всеми его программами, требованиями и раундами.|Уйдут {n} вуза заготовки со всеми их программами, требованиями и раундами.|Уйдут {n} вузов заготовки со всеми их программами, требованиями и раундами.',
        )}
        consequences={[
          t('Вузы, заведённые школой ({count}), останутся на месте', { count: stats.data?.own_universities ?? 0 }),
          held > 0
            ? tn(
                held,
                'Внимание: {n} запись в списках учеников ссылается на программы заготовки — она уйдёт вместе с ней|Внимание: {n} записи в списках учеников ссылаются на программы заготовки — они уйдут вместе с ней|Внимание: {n} записей в списках учеников ссылаются на программы заготовки — они уйдут вместе с ней',
              )
            : t('Ни один ученик не держит эти программы в своём списке'),
          t('Вуз, под которым школа завела свою программу, останется — уйдут только его программы-заглушки'),
          t('Заготовку можно завести заново той же кнопкой'),
        ]}
        confirmWord={t('УДАЛИТЬ')}
        confirmLabel={t('Удалить заготовку')}
        busy={dropSeed.isPending}
        error={dropSeed.isError ? (dropSeed.error as Error).message : null}
        onCancel={() => setAskDrop(false)}
        onConfirm={() =>
          dropSeed.mutate(held > 0, {
            onSuccess: (answer) => {
              setAskDrop(false)
              toast.success(answer.detail)
            },
          })
        }
      />
    </div>
  )
}
