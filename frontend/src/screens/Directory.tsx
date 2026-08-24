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
  useSeedStats,
  useVerifyRecord,
  type DirectoryUniversity,
} from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import ConfirmDialog from '../components/ConfirmDialog'
import DeleteButton from '../components/DeleteButton'
import ProgramList from '../components/ProgramList'
import { Chip, ErrorNote, Loading, ScreenHead, UnverifiedNote } from '../components/ui'
import './directory.css'

const SOURCE_TITLES: Record<string, string> = {
  school: 'Заведено школой',
  seed: 'Стартовый справочник',
  import: 'Импорт файла',
  sync: 'Фоновая сверка',
}

function UniversityRow({ row, canEdit }: { row: DirectoryUniversity; canEdit: boolean }) {
  const verify = useVerifyRecord()
  const [openPrograms, setOpenPrograms] = useState(false)
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
          {row.is_verified ? <Chip tone="ok">подтверждено</Chip> : <Chip tone="warn">не подтверждено</Chip>}
        </div>
      </div>

      {!row.is_verified && <UnverifiedNote note={row.verification_note} website={row.website} />}

      {canEdit && (
        <div className="dir__actions">
          <button
            className="btn btn-ghost btn-sm"
            disabled={verify.isPending}
            onClick={() => verify.mutate({ kind: 'university', id: row.id, verified: !row.is_verified })}
          >
            {row.is_verified ? 'Вернуть признак «не подтверждено»' : 'Подтвердить данные'}
          </button>
          {verify.isError && <ErrorNote error={verify.error} />}
          {verify.isSuccess && <span className="muted dir__hint">{verify.data.detail}</span>}
          {/* удаление отодвинуто вправо и покрашено иначе: рядом
              с «Подтвердить» ему не место */}
          <button className="btn btn-ghost btn-sm" onClick={() => setOpenPrograms(!openPrograms)}>
            {openPrograms ? 'Скрыть программы' : 'Программы, требования и раунды'}
          </button>
          <span className="dir__spacer" />
          <DeleteButton
            model="universities.University"
            id={row.id}
            path="/universities/"
            invalidate={[['universities'], ['catalog']]}
            label="Удалить вуз"
          />
        </div>
      )}

      {openPrograms && <ProgramList universityId={row.id} canEdit={canEdit} />}
    </article>
  )
}

export default function Directory() {
  const { me } = useAuth()
  const canEdit = me?.role === 'director_admission'
  const [search, setSearch] = useState('')
  const [askDrop, setAskDrop] = useState(false)

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
        eyebrow="Справочник"
        title="Вузы и программы"
        subtitle="Откуда взялась запись и подтверждены ли её данные — видно у каждой строки"
      />

      {canEdit && (
        <div className="card card-pad dir__seed">
          <div>
            <b>Стартовый справочник</b>
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
            <button
              className="btn btn-primary btn-sm"
              disabled={createSeed.isPending}
              onClick={() => createSeed.mutate()}
            >
              {createSeed.isPending ? 'Заводим…' : 'Заполнить стартовый справочник'}
            </button>
            <button
              className="btn btn-danger btn-sm"
              disabled={seedCount === 0}
              onClick={() => setAskDrop(true)}
            >
              Удалить стартовый справочник
            </button>
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
        <input
          className="input"
          value={search}
          placeholder="Найти вуз по названию или стране"
          aria-label="Поиск по справочнику"
          onChange={(event) => setSearch(event.target.value)}
        />
        <span className="muted dir__hint">Найдено: {list.data?.count ?? 0}</span>
      </div>

      {list.isLoading && <Loading />}
      {list.isError && <ErrorNote error={list.error} />}

      {!list.isLoading && rows.length === 0 && (
        <div className="card card-pad dir__empty">
          <b>Справочник пуст</b>
          <p className="muted">
            Пока в базе нет ни одного вуза. Заполните стартовый справочник кнопкой выше или загрузите свой
            файл требований на экране импорта.
          </p>
        </div>
      )}

      <div className="dir__list">
        {rows.map((row) => (
          <UniversityRow key={row.id} row={row} canEdit={canEdit} />
        ))}
      </div>

      <ConfirmDialog
        open={askDrop}
        title="Удалить стартовый справочник?"
        what={`Уйдут ${seedCount} вузов заготовки со всеми их программами, требованиями и раундами.`}
        consequences={[
          `Вузы, заведённые школой (${stats.data?.own_universities ?? 0}), останутся на месте`,
          held > 0
            ? `Внимание: ${held} записей в списках учеников ссылаются на программы заготовки — они уйдут вместе с ней`
            : 'Ни один ученик не держит эти программы в своём списке',
          'Вуз, под которым школа завела свою программу, останется — уйдут только его программы-заглушки',
          'Заготовку можно завести заново той же кнопкой',
        ]}
        confirmWord="УДАЛИТЬ"
        confirmLabel="Удалить заготовку"
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
