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
  type DirectoryEntry,
  type DirectoryKind,
  type DirectoryUsage,
} from '../api/hooks'
import ConfirmDialog from '../components/ConfirmDialog'
import Empty from '../components/Empty'
import { counted, ErrorNote, Loading, ScreenHead } from '../components/ui'
import './directory-list.css'
import { t } from '../i18n'
import { NativeSelect } from '../components/ui/native-select'
import { Input } from '../components/ui/input'

export interface DirectorySetup {
  kind: DirectoryKind
  title: string
  subtitle: string
  /** как называется одна запись: «предмет», «вид спорта» */
  one: string
  /** подпись поля категории */
  groupLabel: string
  /** имя поля категории в записи */
  groupField: 'area' | 'category'
  groups: { value: string; title: string }[]
  emptyWhat: string
  forms: [string, string, string]
}

const BLANK = { name: '', group: '', description: '', sort_order: 100 }

export default function DirectoryList({ setup }: { setup: DirectorySetup }) {
  const list = useDirectoryEntries(setup.kind)
  const duplicates = useDirectoryDuplicates(setup.kind)
  const actions = useDirectoryActions(setup.kind)

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
    const body = {
      name: draft.name.trim(),
      [setup.groupField]: draft.group,
      description: draft.description.trim(),
      sort_order: Number(draft.sort_order) || 100,
    }
    if (!body.name) {
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
      group: (entry[setup.groupField] as string) ?? '',
      description: entry.description,
      sort_order: entry.sort_order,
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

      {flash && <p className="chip chip-ok dir__flash">{flash}</p>}
      {problem && <p className="chip chip-risk dir__flash">{problem}</p>}

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
          <label className="dir__field">
            {setup.groupLabel}
            <NativeSelect
              value={draft.group}
              onChange={(event) => setDraft({ ...draft, group: event.target.value })}
            >
              {setup.groups.map((group) => (
                <option key={group.value} value={group.value}>
                  {group.title}
                </option>
              ))}
            </NativeSelect>
          </label>
          <label className="dir__field dir__field--wide">
            {t('Описание')}
            <Input
              value={draft.description}
              placeholder={setup.forms[1]}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
            />
          </label>
          <label className="dir__field dir__field--narrow">
            {t('Порядок')}
            <Input
              type="number"
              value={draft.sort_order}
              onChange={(event) => setDraft({ ...draft, sort_order: Number(event.target.value) })}
            />
          </label>
        </div>
        <div className="toolbar">
          <button className="btn btn-primary btn-sm" onClick={submit}>
            {editing ? 'Сохранить' : 'Завести'}
          </button>
          {editing && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setEditing(null)
                setDraft({ ...BLANK, group: setup.groups[0]?.value ?? '' })
              }}
            >
              {t('Отмена')}
            </button>
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
                <span key={entry.id} className="chip chip-warn">
                  {entry.name} · {counted(entry.usage_total, ['ссылка', 'ссылки', 'ссылок'])}
                </span>
              ))}
            </p>
          ))}
        </div>
      )}

      {rows.length === 0 ? (
        <Empty
          title={setup.title}
          what={setup.emptyWhat}
          action={`Завести ${setup.one}`}
          onAction={() => document.querySelector<HTMLInputElement>('.dir__field input')?.focus()}
        />
      ) : (
        <div className="card card-pad">
          <table className="tbl dir__table">
            <thead>
              <tr>
                <th>{t('Название')}</th>
                <th>{setup.groupLabel}</th>
                <th>{t('Где используется')}</th>
                <th>{t('В списке выбора')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((entry) => (
                <tr key={entry.id} className={entry.is_active ? undefined : 'dir__row--hidden'}>
                  <td style={{ fontWeight: 650 }}>
                    {entry.name}
                    {entry.description && <div className="muted dir__note">{entry.description}</div>}
                  </td>
                  <td className="muted">{entry.category_title}</td>
                  <td className="num">
                    {entry.usage_total === 0 ? (
                      <span className="muted">{t('нигде')}</span>
                    ) : (
                      counted(entry.usage_total, ['запись', 'записи', 'записей'])
                    )}
                  </td>
                  <td>
                    <span className={`chip ${entry.is_active ? 'chip-ok' : 'chip-mute'}`}>
                      {entry.is_active ? 'показывается' : 'скрыт'}
                    </span>
                  </td>
                  <td className="dir__actions">
                    <button className="btn btn-ghost btn-sm" onClick={() => startEdit(entry)}>
                      {t('Править')}
                    </button>
                    {entry.is_active ? (
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() =>
                          actions.hide.mutate(entry.id, { onSuccess: (answer) => report(answer.detail) })
                        }
                      >
                        {t('Скрыть')}
                      </button>
                    ) : (
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() =>
                          actions.show.mutate(entry.id, { onSuccess: (answer) => report(answer.detail) })
                        }
                      >
                        {t('Вернуть')}
                      </button>
                    )}
                    <button className="btn btn-ghost btn-sm" onClick={() => void askDelete(entry)}>
                      {t('Удалить')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
              <NativeSelect
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
              </NativeSelect>
            </label>
            <div className="confirm__actions">
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setReplacing(null)
                  setTarget(null)
                }}
              >
                {t('Отмена')}
              </button>
              <button
                className="btn btn-ghost btn-sm"
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
              </button>
              <button
                className="btn btn-danger btn-sm"
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
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
