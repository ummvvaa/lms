/**
 * Экран управления справочником: предметы олимпиад у Армана,
 * виды спорта у Нурлыбека. Устройство одинаковое, различаются только
 * подписи и название колонки-категории.
 *
 * Удаление записи, на которую ссылаются, не проходит. Вместо тупика
 * человек получает два выхода: скрыть из списка выбора или заменить
 * на другую запись вместе со всеми ссылками (фаза 18).
 */
import { useState } from 'react'
import {
  useDirectoryEntries,
  useDirectoryActions,
  useDirectoryDuplicates,
  useSubjectAreas,
  type DirectoryEntry,
  type DirectoryKind,
  type DirectoryUsage,
} from '../api/hooks'
import ConfirmDialog from '../components/ConfirmDialog'
import Empty from '../components/Empty'
import DataTable from '../components/DataTable'
import { Chip, counted, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import './directory-list.css'
import { t } from '../i18n'
import { SelectField } from '../components/SelectField'
import { Input } from '../components/ui/input'
import { Button } from '../components/ui/button'

export interface DirectorySetup {
  kind: DirectoryKind
  title: string
  subtitle: string
  /** как называется одна запись: «предмет», «вид спорта» */
  one: string
  /** подпись поля категории */
  groupLabel: string
  /** имя поля категории в записи; пусто — у справочника нет категории */
  groupField?: 'area' | 'category'
  groups: { value: string; title: string }[]
  /** категория — «из списка или своё»: поле ввода с подсказками. Список
   *  подсказок отдаёт сервер — исходные варианты и всё введённое раньше */
  groupFree?: boolean
  /** у справочника нет числового «порядка»: записи идут по алфавиту */
  noOrder?: boolean
  /** дополнительные числовые поля: шкала экзамена (фаза 39) */
  extras?: { field: 'min_score' | 'max_score'; label: string }[]
  emptyWhat: string
  forms: [string, string, string]
}

const BLANK = { name: '', group: '', description: '', sort_order: 100, extras: {} as Record<string, string> }

export default function DirectoryList({ setup }: { setup: DirectorySetup }) {
  const list = useDirectoryEntries(setup.kind)
  const duplicates = useDirectoryDuplicates(setup.kind)
  const actions = useDirectoryActions(setup.kind)
  const offered = useSubjectAreas(setup.groupFree === true)

  const [draft, setDraft] = useState({ ...BLANK, group: setup.groups[0]?.value ?? '' })
  const [editing, setEditing] = useState<DirectoryEntry | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<{ entry: DirectoryEntry; usage: DirectoryUsage } | null>(null)
  const [replacing, setReplacing] = useState<{ entry: DirectoryEntry; usage: DirectoryUsage } | null>(null)
  const [target, setTarget] = useState<number | null>(null)

  if (list.isLoading) return <Loading kind="table" />
  if (list.isError) return <ErrorNote error={list.error} />

  const rows = list.data?.results ?? []
  const groups = duplicates.data?.groups ?? []

  function report(detail: string) {
    setFlash(detail)
    setProblem(null)
  }

  function submit() {
    const body: Record<string, unknown> = {
      name: draft.name.trim(),
      description: draft.description.trim(),
    }
    if (!setup.noOrder) body.sort_order = Number(draft.sort_order) || 100
    if (setup.groupField) body[setup.groupField] = draft.group.trim()
    for (const extra of setup.extras ?? []) {
      body[extra.field] =
        draft.extras[extra.field] === '' || draft.extras[extra.field] === undefined
          ? null
          : draft.extras[extra.field]
    }
    if (!String(body.name)) {
      setProblem(`Название — обязательное поле: без него ${setup.one} не найти в списке`)
      return
    }
    const done = (detail: string) => {
      report(detail)
      setDraft({ ...BLANK, group: setup.groups[0]?.value ?? '' })
      setEditing(null)
    }
    if (editing) {
      actions.update.mutate(
        { id: editing.id, ...body },
        {
          onSuccess: () => done(`Сохранено: ${body.name}`),
          onError: (error) => setProblem(String((error as Error).message)),
        },
      )
    } else {
      actions.create.mutate(body, {
        onSuccess: () => done(`Заведено: ${body.name}. Теперь оно есть в списке выбора`),
        onError: (error) => setProblem(String((error as Error).message)),
      })
    }
  }

  function startEdit(entry: DirectoryEntry) {
    setEditing(entry)
    setDraft({
      name: entry.name,
      group: setup.groupField ? ((entry[setup.groupField] as string) ?? '') : '',
      description: entry.description,
      sort_order: entry.sort_order,
      extras: Object.fromEntries(
        (setup.extras ?? []).map((extra) => [extra.field, String(entry[extra.field] ?? '')]),
      ),
    })
  }

  async function askDelete(entry: DirectoryEntry) {
    const usage = await actions.usage(entry.id)
    if (usage.can_delete) setConfirm({ entry, usage })
    else setReplacing({ entry, usage })
  }

  return (
    <div>
      <ScreenHead title={setup.title} subtitle={setup.subtitle} />

      {flash && (
        <Chip tone="good" className="dir__flash">
          {flash}
        </Chip>
      )}
      {problem && (
        <Chip tone="bad" className="dir__flash">
          {problem}
        </Chip>
      )}

      <div className="card card-pad dir__form">
        <span className="eyebrow">{editing ? `Правим «${editing.name}»` : `Завести ${setup.one}`}</span>
        <div className="dir__fields">
          <label className="dir__field">
            {t('Название')}
            <Input
              value={draft.name}
              placeholder={setup.forms[0]}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            />
          </label>
          {setup.groupField && setup.groupFree && (
            <label className="dir__field">
              {setup.groupLabel}
              {/* из списка или своё: родной комбобокс браузера — поле ввода
                  с подсказками; на телефоне это системный список */}
              <Input
                list="dir-group-options"
                value={draft.group}
                placeholder={t('Выберите из списка или введите своё')}
                onChange={(event) => setDraft({ ...draft, group: event.target.value })}
              />
              <datalist id="dir-group-options">
                {(offered.data?.areas ?? setup.groups.map((group) => group.title)).map((title) => (
                  <option key={title} value={title} />
                ))}
              </datalist>
            </label>
          )}
          {setup.groupField && !setup.groupFree && (
            <label className="dir__field">
              {setup.groupLabel}
              <SelectField
                value={draft.group}
                onChange={(event) => setDraft({ ...draft, group: event.target.value })}
              >
                {setup.groups.map((group) => (
                  <option key={group.value} value={group.value}>
                    {group.title}
                  </option>
                ))}
              </SelectField>
            </label>
          )}
          {(setup.extras ?? []).map((extra) => (
            <label key={extra.field} className="dir__field dir__field--narrow">
              {t(extra.label)}
              <Input
                type="number"
                value={draft.extras[extra.field] ?? ''}
                onChange={(event) =>
                  setDraft({ ...draft, extras: { ...draft.extras, [extra.field]: event.target.value } })
                }
              />
            </label>
          ))}
          <label className="dir__field dir__field--wide">
            {t('Описание')}
            <Input
              value={draft.description}
              placeholder={setup.forms[1]}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
            />
          </label>
          {!setup.noOrder && (
            <label className="dir__field dir__field--narrow">
              {t('Порядок')}
              <Input
                type="number"
                value={draft.sort_order}
                onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })}
              />
            </label>
          )}
        </div>
        <div className="toolbar">
          <Button size="sm" onClick={submit}>
            {editing ? 'Сохранить' : 'Завести'}
          </Button>
          {editing && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setEditing(null)
                setDraft({ ...BLANK, group: setup.groups[0]?.value ?? '' })
              }}
            >
              {t('Отмена')}
            </Button>
          )}
        </div>
      </div>

      {groups.length > 0 && (
        <div className="card card-pad dir__dupes">
          <span className="eyebrow">{t('Возможно, это одно и то же')}</span>
          <p className="muted">
            {t(
              'Написания похожи. Сами мы их не склеиваем — решаете вы. «Заменить» перенесёт все ссылки на выбранную запись, а лишнюю уберёт.',
            )}
          </p>
          {groups.map((group) => (
            <p key={group.key} className="dir__dupe">
              {group.entries.map((entry) => (
                <Chip key={entry.id} tone="warn">
                  {entry.name} · {counted(entry.usage_total, ['ссылка', 'ссылки', 'ссылок'])}
                </Chip>
              ))}
            </p>
          ))}
        </div>
      )}

      {rows.length === 0 ? (
        <Empty
          icon="book"
          title={setup.title}
          what={setup.emptyWhat}
          action={`Завести ${setup.one}`}
          onAction={() => document.querySelector<HTMLInputElement>('.dir__field input')?.focus()}
        />
      ) : (
        <DataCard title={setup.title} count={rows.length || undefined}>
          <DataTable
            columns={[
              {
                key: 'name',
                title: t('Название'),
                width: '34%',
                cell: (entry: DirectoryEntry) => (
                  <>
                    <b>{entry.name}</b>
                    {entry.description && <span className="t-note"> · {entry.description}</span>}
                  </>
                ),
                sortBy: (entry: DirectoryEntry) => entry.name.toLowerCase(),
              },
              { key: 'category', title: setup.groupLabel, width: '16%', cell: (entry: DirectoryEntry) => entry.category_title || <span className="t-note">{t('нет')}</span>, sortBy: (entry: DirectoryEntry) => entry.category_title },
              {
                key: 'usage',
                title: t('Где используется'),
                width: '16%',
                align: 'right',
                cell: (entry: DirectoryEntry) => (entry.usage_total === 0 ? <span className="t-note">{t('нигде')}</span> : <span className="num">{counted(entry.usage_total, ['запись', 'записи', 'записей'])}</span>),
                sortBy: (entry: DirectoryEntry) => entry.usage_total,
              },
              {
                key: 'active',
                title: t('В списке выбора'),
                width: '14%',
                cell: (entry: DirectoryEntry) => (
                  <Chip tone={entry.is_active ? 'good' : 'neutral'} size="sm">
                    {entry.is_active ? t('показывается') : t('скрыт')}
                  </Chip>
                ),
                sortBy: (entry: DirectoryEntry) => (entry.is_active ? 0 : 1),
              },
              {
                key: 'acts',
                title: '',
                width: '20%',
                align: 'right',
                cell: (entry: DirectoryEntry) => (
                  <span className="acad__inline">
                    <Button variant="outline" size="sm" onClick={() => startEdit(entry)}>
                      {t('Править')}
                    </Button>
                    {entry.is_active ? (
                      <Button variant="outline" size="sm" onClick={() => actions.hide.mutate(entry.id, { onSuccess: (answer) => report(answer.detail) })}>
                        {t('Скрыть')}
                      </Button>
                    ) : (
                      <Button variant="outline" size="sm" onClick={() => actions.show.mutate(entry.id, { onSuccess: (answer) => report(answer.detail) })}>
                        {t('Вернуть')}
                      </Button>
                    )}
                    <Button variant="outline" size="sm" onClick={() => void askDelete(entry)}>
                      {t('Удалить')}
                    </Button>
                  </span>
                ),
              },
            ]}
            rows={rows}
            rowKey={(entry) => entry.id}
          />
        </DataCard>
      )}

      <ConfirmDialog
        open={confirm !== null}
        title={`Удалить «${confirm?.entry.name ?? ''}»?`}
        what={confirm?.usage.message}
        consequences={['Запись исчезнет насовсем: истории у справочника нет']}
        busy={actions.remove.isPending}
        onCancel={() => setConfirm(null)}
        onConfirm={() => {
          const entry = confirm?.entry
          if (!entry) return
          actions.remove.mutate(entry.id, {
            onSuccess: (answer) => {
              report(answer.detail)
              setConfirm(null)
            },
            onError: (error) => {
              setProblem(String((error as Error).message))
              setConfirm(null)
            },
          })
        }}
      />

      {replacing && (
        <div className="confirm__backdrop" role="presentation" onClick={() => setReplacing(null)}>
          <div
            className="confirm"
            role="alertdialog"
            aria-modal="true"
            aria-label={`Удалить «${replacing.entry.name}» нельзя`}
            onClick={(event) => event.stopPropagation()}
          >
            <h2 className="confirm__title">Удалить «{replacing.entry.name}» нельзя</h2>
            <p className="confirm__what">{replacing.usage.message}</p>
            <ul className="confirm__list">
              {replacing.usage.options.map((option) => (
                <li key={option.action}>
                  <b>{option.title}</b> — {option.hint}
                </li>
              ))}
            </ul>
            <label className="dir__field">
              {t('Заменить на')}
              <SelectField
                value={target ?? ''}
                onChange={(event) => setTarget(Number(event.target.value) || null)}
              >
                <option value="">{t('выберите запись')}</option>
                {rows
                  .filter((row) => row.id !== replacing.entry.id)
                  .map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
              </SelectField>
            </label>
            <div className="confirm__actions">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setReplacing(null)
                  setTarget(null)
                }}
              >
                {t('Отмена')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  actions.hide.mutate(replacing.entry.id, {
                    onSuccess: (answer) => {
                      report(answer.detail)
                      setReplacing(null)
                    },
                  })
                }
              >
                {t('Скрыть из списка')}
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={target === null || actions.replace.isPending}
                onClick={() =>
                  target !== null &&
                  actions.replace.mutate(
                    { id: replacing.entry.id, target },
                    {
                      onSuccess: (answer) => {
                        report(answer.detail)
                        setReplacing(null)
                        setTarget(null)
                      },
                      onError: (error) => setProblem(String((error as Error).message)),
                    },
                  )
                }
              >
                {t('Заменить и удалить')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
