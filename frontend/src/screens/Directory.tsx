/**
 * Справочник вузов глазами директора по поступлению.
 *
 * Здесь видно, откуда взялась каждая запись и подтверждена ли она
 * (инвариант №14). Стартовый справочник — заготовка: он заводится одной
 * кнопкой и одной же кнопкой убирается целиком, не задевая то,
 * что школа завела руками.
 */
import { useState } from 'react'
import {
  useCreateSeedCatalog,
  useDirectory,
  useDropSeedCatalog,
  useCreateUniversity,
  useSeedStats,
  useUpdateUniversity,
  useVerifyRecord,
  type DirectoryUniversity,
} from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import Empty from '../components/Empty'
import Modal from '../components/Modal'
import RowForm from '../components/RowForm'
import ConfirmDialog from '../components/ConfirmDialog'
import DeleteButton from '../components/DeleteButton'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import ProgramList from '../components/ProgramList'
import { Chip, ErrorNote, Loading, ScreenHead, UnverifiedNote } from '../components/ui'
import './directory.css'
import { t } from '../i18n'
import { Input } from '../components/ui/input'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'

const SOURCE_TITLES: Record<string, string> = {
  school: 'Заведено школой',
  seed: 'Стартовый справочник',
  import: 'Импорт файла',
  sync: 'Фоновая сверка',
}

/** Правка вуза: название, страна, сайт, домен. */
function UniversityForm({ row, onClose }: { row: DirectoryUniversity; onClose: () => void }) {
  const update = useUpdateUniversity()
  const [draft, setDraft] = useState({
    name: row.name,
    country: row.country,
    website: row.website ?? '',
    domain: row.domain ?? '',
  })
  const [problem, setProblem] = useState<string | null>(null)

  return (
    <div className="prog__form">
      <div className="prog__grid">
        <label className="prog__field">
          <span className="muted">{t('Название')}</span>
          <Input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
        </label>
        <label className="prog__field">
          <span className="muted">{t('Страна')}</span>
          <Input
            value={draft.country}
            onChange={(event) => setDraft({ ...draft, country: event.target.value })}
          />
        </label>
        <label className="prog__field">
          <span className="muted">{t('Сайт')}</span>
          <Input
            value={draft.website}
            onChange={(event) => setDraft({ ...draft, website: event.target.value })}
          />
        </label>
        <label className="prog__field">
          <span className="muted">{t('Домен')}</span>
          <Input
            value={draft.domain}
            placeholder="utoronto.ca"
            onChange={(event) => setDraft({ ...draft, domain: event.target.value })}
          />
        </label>
      </div>
      <p className="muted prog__hint">
        {t('По домену модель ищет требования на официальном сайте — без него сверка не работает.')}
      </p>
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <Button
          size="sm"
          onClick={() => {
            if (!draft.name.trim()) {
              setProblem(t('Название — обязательное поле'))
              return
            }
            update.mutate(
              { id: row.id, ...draft, name: draft.name.trim() },
              { onSuccess: onClose, onError: (e) => setProblem(String((e as Error).message)) },
            )
          }}
        >
          {t('Сохранить')}
        </Button>
        <Button variant="outline" size="sm" onClick={onClose}>
          {t('Отмена')}
        </Button>
        {problem && <Badge variant="risk">{problem}</Badge>}
      </div>
    </div>
  )
}

function UniversityRow({ row, canEdit }: { row: DirectoryUniversity; canEdit: boolean }) {
  const verify = useVerifyRecord()
  const [openPrograms, setOpenPrograms] = useState(false)
  const [editing, setEditing] = useState(false)
  return (
    <article className="card card-pad dir__row">
      <div className="row-between dir__rowhead">
        <div>
          <b className="dir__name">{row.name}</b>
          <p className="muted dir__sub">
            {row.country}
            {row.domain && ` · ${row.domain}`}
          </p>
        </div>
        <div className="dir__marks">
          <Chip tone={row.data_source === 'seed' ? 'warn' : 'mute'}>
            {SOURCE_TITLES[row.data_source] ?? row.data_source}
          </Chip>
          {row.is_verified ? (
            <Chip tone="ok">{t('подтверждено')}</Chip>
          ) : (
            <Chip tone="warn">{t('не подтверждено')}</Chip>
          )}
        </div>
      </div>

      {!row.is_verified && <UnverifiedNote note={row.verification_note} website={row.website} />}

      {canEdit && (
        <div className="dir__actions">
          {/* на виду только работа с данными: «Изменить» и «Подтвердить».
              Удаление — в меню: экран, заполненный красными кнопками,
              перетягивает внимание с того, ради чего сюда заходят */}
          <Button variant="outline" size="sm" onClick={() => setEditing(!editing)}>
            {t('Изменить')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={verify.isPending}
            onClick={() => verify.mutate({ kind: 'university', id: row.id, verified: !row.is_verified })}
          >
            {row.is_verified ? 'Вернуть признак «не подтверждено»' : 'Подтвердить данные'}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setOpenPrograms(!openPrograms)}>
            {openPrograms ? 'Скрыть программы' : 'Программы, требования и раунды'}
          </Button>
          <span className="dir__spacer" />
          <RowMenu>
            <RowMenuItem risk keepOpen>
              <DeleteButton
                model="universities.University"
                id={row.id}
                path="/universities/"
                invalidate={[['universities'], ['catalog']]}
                label={t('Удалить вуз')}
              />
            </RowMenuItem>
          </RowMenu>
          {verify.isError && <ErrorNote error={verify.error} />}
          {verify.isSuccess && <span className="muted dir__hint">{verify.data.detail}</span>}
        </div>
      )}

      {editing && <UniversityForm row={row} onClose={() => setEditing(false)} />}

      {openPrograms && <ProgramList universityId={row.id} canEdit={canEdit} />}
    </article>
  )
}

export default function Directory() {
  const { me } = useAuth()
  const canEdit = me?.role === 'director_admission'
  const [search, setSearch] = useState('')
  const [askDrop, setAskDrop] = useState(false)
  const [adding, setAdding] = useState(false)

  const create = useCreateUniversity()
  const list = useDirectory(search)
  const stats = useSeedStats(canEdit)
  const createSeed = useCreateSeedCatalog()
  const dropSeed = useDropSeedCatalog()

  const rows = list.data?.results ?? []
  const seedCount = stats.data?.universities ?? 0
  const held = stats.data?.held_by_students ?? 0

  return (
    <section className="screen">
      <ScreenHead
        eyebrow={t('Справочник')}
        title={t('Вузы и программы')}
        subtitle={t('Откуда взялась запись и подтверждены ли её данные — видно у каждой строки')}
      />

      {canEdit && (
        <div className="card card-pad dir__seed">
          <div>
            <b>{t('Стартовый справочник')}</b>
            <p className="muted dir__sub">
              {seedCount > 0
                ? `Заготовка на ${seedCount} вузов. Данные не подтверждены — сверьте их с сайтами вузов и снимите плашки.`
                : 'Заготовка из 20 вузов, куда обычно поступают выпускники. Все записи придут с плашкой «не подтверждено».'}
            </p>
            {stats.data && (
              <p className="muted dir__sub">
                Заведено школой: {stats.data.own_universities}. Их ни заведение, ни удаление заготовки не
                трогает.
              </p>
            )}
          </div>
          <div className="dir__seedactions">
            <Button size="sm" disabled={createSeed.isPending} onClick={() => createSeed.mutate()}>
              {createSeed.isPending ? 'Заводим…' : 'Заполнить стартовый справочник'}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={seedCount === 0}
              onClick={() => setAskDrop(true)}
            >
              {t('Удалить стартовый справочник')}
            </Button>
          </div>
          {createSeed.isError && <ErrorNote error={createSeed.error} />}
          {createSeed.isSuccess && <span className="muted dir__hint">{createSeed.data.detail}</span>}
          {dropSeed.isSuccess && (
            <span className="muted dir__hint">
              {dropSeed.data.detail}
              {dropSeed.data.removed?.kept_universities
                ? `. Оставлено вузов со своими программами школы: ${dropSeed.data.removed.kept_universities}`
                : ''}
            </span>
          )}
        </div>
      )}

      <div className="dir__toolbar">
        <Input
          value={search}
          placeholder={t('Найти вуз по названию или стране')}
          aria-label={t('Поиск по справочнику')}
          onChange={(event) => setSearch(event.target.value)}
        />
        <span className="muted dir__hint">Найдено: {list.data?.count ?? 0}</span>
        {canEdit && (
          <Button size="sm" onClick={() => setAdding(true)}>
            {t('Добавить вуз')}
          </Button>
        )}
      </div>

      {adding && (
        <Modal
          title={t('Новый вуз')}
          note={t('Домен сайта нужен сверке: по нему модель ищет только на официальном сайте')}
          onClose={() => setAdding(false)}
        >
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
            onSubmit={(values) => {
              create.mutate({
                name: String(values.name ?? ''),
                country: String(values.country ?? ''),
                website: String(values.website ?? ''),
                domain: String(values.domain ?? ''),
              })
              setAdding(false)
            }}
          />
        </Modal>
      )}

      {list.isLoading && <Loading kind="table" />}
      {list.isError && <ErrorNote error={list.error} />}

      {!list.isLoading && rows.length === 0 && (
        <Empty
          // без своей кнопки: «Заполнить стартовый справочник» и «Добавить вуз»
          // стоят прямо над пустым состоянием, второй экземпляр только путал
          icon="building"
          title={t('Справочник пуст')}
          what={t(
            'Заполните стартовый справочник или заведите первый вуз; файл требований загружает администратор.',
          )}
          hint={t(
            'Стартовый справочник — 20 вузов, куда обычно поступают выпускники; все его записи придут с плашкой «не подтверждено».',
          )}
        />
      )}

      <div className="dir__list">
        {rows.map((row) => (
          <UniversityRow key={row.id} row={row} canEdit={canEdit} />
        ))}
      </div>

      <ConfirmDialog
        open={askDrop}
        title={t('Удалить стартовый справочник?')}
        what={`Уйдут ${seedCount} вузов заготовки со всеми их программами, требованиями и раундами.`}
        consequences={[
          `Вузы, заведённые школой (${stats.data?.own_universities ?? 0}), останутся на месте`,
          held > 0
            ? `Внимание: ${held} записей в списках учеников ссылаются на программы заготовки — они уйдут вместе с ней`
            : 'Ни один ученик не держит эти программы в своём списке',
          'Вуз, под которым школа завела свою программу, останется — уйдут только его программы-заглушки',
          'Заготовку можно завести заново той же кнопкой',
        ]}
        confirmWord={t('УДАЛИТЬ')}
        confirmLabel={t('Удалить заготовку')}
        busy={dropSeed.isPending}
        error={dropSeed.isError ? (dropSeed.error as Error).message : null}
        onCancel={() => setAskDrop(false)}
        onConfirm={() =>
          dropSeed.mutate(held > 0, {
            onSuccess: () => setAskDrop(false),
          })
        }
      />
    </section>
  )
}
