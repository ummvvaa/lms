/**
 * Справочник вузов глазами директора по поступлению.
 *
 * Здесь видно, откуда взялась каждая запись и подтверждена ли она
 * (инвариант №14). Стартовый справочник — заготовка: он заводится одной
 * кнопкой и одной же кнопкой убирается целиком, не задевая то,
 * что школа завела руками.
 *
 * Вид — вузы строками слева, справа выбранный вуз: правка, подтверждение,
 * программы, требования и раунды. Двадцати карточек подряд больше нет.
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
import { t } from '../i18n'
import { NoteCard } from './academics/shared'
import './academics/academics.css'
import './directory.css'

const SOURCE_TITLES: Record<string, string> = {
  school: 'Заведено школой',
  seed: 'Стартовый справочник',
  import: 'Импорт файла',
  sync: 'Фоновая сверка',
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
      <Field name="domain" label={t('Домен')} value={draft.domain} placeholder="utoronto.ca" hint={t('По домену модель ищет требования на официальном сайте — без него сверка не работает.')} onChange={(value) => setDraft({ ...draft, domain: value })} />
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

/** Правая колонка: выбранный вуз целиком. */
function UniversityPanel({ row, canEdit }: { row: DirectoryUniversity; canEdit: boolean }) {
  const verify = useVerifyRecord()
  const [editing, setEditing] = useState(false)
  return (
    <>
      <DataCard
        title={row.name}
        note={`${row.country}${row.domain ? ` · ${row.domain}` : ''}`}
        right={
          canEdit ? (
            <RowMenu>
              <RowMenuItem onClick={() => setEditing(true)}>{t('Изменить')}</RowMenuItem>
              <RowMenuItem risk keepOpen>
                <DeleteButton model="universities.University" id={row.id} path="/universities/" invalidate={[['universities'], ['catalog']]} label={t('Удалить вуз')} inMenu />
              </RowMenuItem>
            </RowMenu>
          ) : undefined
        }
      >
        <Rows>
          <Row title={t('Источник')} value={SOURCE_TITLES[row.data_source] ?? row.data_source} />
          <Row
            title={t('Данные')}
            value={row.is_verified ? <Chip tone="good" size="sm">{t('подтверждено')}</Chip> : <Chip tone="warn" size="sm">{t('не подтверждено')}</Chip>}
            acts={
              canEdit ? (
                <Button variant="secondary" size="sm" disabled={verify.isPending} onClick={() => verify.mutate({ kind: 'university', id: row.id, verified: !row.is_verified }, { onSuccess: (answer) => toast.success(answer.detail), onError: (error) => toast.error(error.message) })}>
                  {row.is_verified ? t('Снять подтверждение') : t('Подтвердить данные')}
                </Button>
              ) : undefined
            }
          />
          {row.website && <Row title={t('Сайт')} value={row.website} />}
        </Rows>
        {!row.is_verified && <UnverifiedNote note={row.verification_note} website={row.website} />}
      </DataCard>
      <ProgramList universityId={row.id} canEdit={canEdit} />
      <EditDrawer open={editing} onClose={() => setEditing(false)} title={row.name} sub={t('Название, страна, сайт и домен')}>
        <UniversityForm key={row.id} row={row} onClose={() => setEditing(false)} />
      </EditDrawer>
    </>
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
  const picked = rows.find((row) => row.id === pickedId) ?? rows[0] ?? null
  const seedCount = stats.data?.universities ?? 0
  const held = stats.data?.held_by_students ?? 0

  const columns: Column<DirectoryUniversity>[] = [
    {
      key: 'name',
      title: t('Вуз'),
      width: '44%',
      cell: (row) => (
        <>
          <b>{row.name}</b>
          <span className="t-note"> · {row.country}</span>
        </>
      ),
      sortBy: (row) => row.name.toLowerCase(),
    },
    { key: 'source', title: t('Источник'), width: '26%', cell: (row) => <Chip tone={row.data_source === 'seed' ? 'warn' : 'neutral'} size="sm">{SOURCE_TITLES[row.data_source] ?? row.data_source}</Chip>, sortBy: (row) => row.data_source },
    {
      key: 'verified',
      title: t('Данные'),
      width: '30%',
      cell: (row) => (row.is_verified ? <Chip tone="good" size="sm">{t('подтверждено')}</Chip> : <Chip tone="warn" size="sm">{t('не подтверждено')}</Chip>),
      sortBy: (row) => (row.is_verified ? 0 : 1),
    },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Вузы и программы')}
        subtitle={t('Откуда взялась запись и подтверждены ли её данные — видно у каждой строки')}
        pills={[{ label: `${t('Найдено')}: ${list.data?.count ?? 0}` }]}
        actions={
          canEdit ? (
            <>
              <Button variant="outline" disabled={createSeed.isPending} onClick={() => createSeed.mutate(undefined, { onSuccess: (answer) => toast.success(answer.detail), onError: (error) => toast.error(error.message) })}>
                {createSeed.isPending ? t('Заводим…') : t('Заполнить стартовый справочник')}
              </Button>
              <Button onClick={() => setAdding(true)}>{t('Добавить вуз')}</Button>
            </>
          ) : undefined
        }
      />

      <div className="acad__cols">
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
            empty={!list.isLoading && rows.length === 0 && (search ? t('по этому поиску ничего нет') : t('заполните стартовый справочник или заведите первый вуз; файл требований загружает администратор'))}
          >
            <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} onRowClick={(row) => setPickedId(row.id)} selected={(row) => row.id === picked?.id} limit={20} />
          </DataCard>
        </div>
        <div className="acad__stack">
          {picked && <UniversityPanel key={picked.id} row={picked} canEdit={canEdit} />}
          {canEdit && (
            <DataCard
              title={t('Стартовый справочник')}
              note={
                seedCount > 0
                  ? `${t('Заготовка на')} ${seedCount} ${t('вузов')}. ${t('Данные не подтверждены — сверьте их с сайтами вузов и снимите плашки.')}${stats.data ? ` ${t('Заведено школой')}: ${stats.data.own_universities}.` : ''}`
                  : t('Заготовка из 20 вузов, куда обычно поступают выпускники. Все записи придут с плашкой «не подтверждено».')
              }
              right={
                seedCount > 0 ? (
                  <Button variant="outline" size="sm" onClick={() => setAskDrop(true)}>
                    {t('Удалить заготовку')}
                  </Button>
                ) : undefined
              }
            />
          )}
          {!picked && <NoteCard title={t('Как это устроено')}>{t('Стартовый справочник — 20 вузов, куда обычно поступают выпускники; все его записи придут с плашкой «не подтверждено». Файл требований загружает администратор, подтверждает записи директор по поступлению.')}</NoteCard>}
        </div>
      </div>

      <EditDrawer open={adding} onClose={() => setAdding(false)} title={t('Новый вуз')} sub={t('Домен сайта нужен сверке: по нему модель ищет только на официальном сайте')}>
        <RowForm
          fields={[
            { name: 'name', label: 'Название вуза', kind: 'text', required: true },
            { name: 'country', label: 'Страна', kind: 'text', required: true },
            { name: 'website', label: 'Сайт', kind: 'text' },
            { name: 'domain', label: 'Домен сайта', kind: 'text', placeholder: 'utoronto.ca' },
          ]}
          busy={create.isPending}
          submitLabel={t('Завести')}
          onCancel={() => setAdding(false)}
          onSubmit={(values) =>
            create.mutate(
              { name: String(values.name ?? ''), country: String(values.country ?? ''), website: String(values.website ?? ''), domain: String(values.domain ?? '') },
              { onSuccess: (row) => { setAdding(false); setPickedId(row.id) }, onError: (error) => toast.error(error.message) },
            )
          }
        />
      </EditDrawer>

      <ConfirmDialog
        open={askDrop}
        title={t('Удалить стартовый справочник?')}
        what={`${t('Уйдут')} ${seedCount} ${t('вузов заготовки со всеми их программами, требованиями и раундами.')}`}
        consequences={[
          `${t('Вузы, заведённые школой')} (${stats.data?.own_universities ?? 0}), ${t('останутся на месте')}`,
          held > 0 ? `${t('Внимание')}: ${held} ${t('записей в списках учеников ссылаются на программы заготовки — они уйдут вместе с ней')}` : t('Ни один ученик не держит эти программы в своём списке'),
          t('Вуз, под которым школа завела свою программу, останется — уйдут только его программы-заглушки'),
          t('Заготовку можно завести заново той же кнопкой'),
        ]}
        confirmWord={t('УДАЛИТЬ')}
        confirmLabel={t('Удалить заготовку')}
        busy={dropSeed.isPending}
        error={dropSeed.isError ? (dropSeed.error as Error).message : null}
        onCancel={() => setAskDrop(false)}
        onConfirm={() => dropSeed.mutate(held > 0, { onSuccess: (answer) => { setAskDrop(false); toast.success(answer.detail) } })}
      />
    </div>
  )
}
