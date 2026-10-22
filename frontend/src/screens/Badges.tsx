/**
 * Справочник бейджей у директора школы.
 *
 * Условие бейджа — строка справочника: мера плюс порог. Новый бейдж
 * заводится без выката, но мера берётся из закрытого набора — за балл
 * экзамена, GPA или статус бейджа быть не может (инвариант №12).
 *
 * Вид — по макету: плитки по три в ряд — медаль, название и подпись,
 * как увидит ученик, мера с порогом, переключатель «показывать» и меню;
 * правка — в правой панели, по нажатию на плитку или из меню.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useBadgeDirectory, type BadgeDirectoryRow } from '../api/hooks'
import EditDrawer from '../components/EditDrawer'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { Switch } from '../components/ui/switch'
import { t } from '../i18n'
import Icon, { type IconName } from '../layout/icons'
import './badges.css'

/**
 * Меры, которые система умеет считать. Ни одной про баллы — инвариант №12.
 * Функция, а не таблица модуля: подписи переводятся при рендере, на языке человека.
 */
function metrics() {
  return [
    { value: 'tasks_done', title: t('Выполненные задачи роадмапа') },
    { value: 'exercises_solved', title: t('Решённые упражнения') },
    { value: 'mocks_taken', title: t('Пройденные Mock Test онлайн') },
    { value: 'profile_sections', title: t('Заполненные разделы профиля') },
    { value: 'essays_started', title: t('Начатые эссе') },
    { value: 'onboarding_done', title: t('Пройденная анкета первого входа') },
    { value: 'materials_approved', title: t('Материалы, прошедшие проверку') },
    { value: 'resources_read', title: t('Прочитанные материалы раздела «Ресурсы»') },
    { value: 'streak_days', title: t('Дней подряд с действиями') },
    { value: 'plans_created', title: t('Созданные планы по вузам') },
    { value: 'documents_uploaded', title: t('Загруженные документы портфолио') },
  ]
}

/** Поля формы бейджа — функцией по той же причине: подписи на языке человека. */
function fields(): FieldDef[] {
  return [
    { name: 'code', label: t('Код бейджа'), kind: 'text', required: true, placeholder: 'first_plan' },
    { name: 'name', label: t('Название бейджа'), kind: 'text', required: true },
    { name: 'description', label: t('Описание бейджа'), kind: 'text' },
    { name: 'metric', label: t('Что считает бейдж'), kind: 'select', required: true, options: metrics() },
    { name: 'threshold', label: t('Сколько нужно'), kind: 'number', required: true },
    { name: 'icon', label: t('Иконка'), kind: 'text', placeholder: 'medal' },
    { name: 'order', label: t('Порядок'), kind: 'number' },
    { name: 'is_active', label: t('Показывать бейдж'), kind: 'checkbox' },
  ]
}

function payload(values: RowValues): Record<string, unknown> {
  return {
    ...values,
    description: values.description ?? '',
    icon: values.icon || 'medal',
    threshold: values.threshold ?? 1,
    order: values.order ?? 100,
  }
}

export default function Badges() {
  const { query, create, update, remove } = useBadgeDirectory()
  const [editing, setEditing] = useState<BadgeDirectoryRow | null>(null)
  const [creating, setCreating] = useState(false)

  if (query.isLoading) return <Loading kind="table" />
  if (query.error) return <ErrorNote error={query.error} />

  const rows = query.data?.results ?? []
  const fail = (error: Error) => toast.error(error.message)

  // порядок плиток — как у ученика на экране достижений
  const sorted = [...rows].sort((a, b) => a.order - b.order || a.id - b.id)
  const shown = rows.filter((row) => row.is_active).length

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Достижения школы')}
        subtitle={rows.length > 0 ? t('Бейджи, которые ученики получают сами — за дела в LMS. Включено {on} из {total}', { on: shown, total: rows.length }) : undefined}
        actions={<Button onClick={() => setCreating(true)}>{t('Добавить бейдж')}</Button>}
      />

      {rows.length === 0 ? (
        <DataCard
          title={t('Бейджи')}
          empty={t('заведите первый бейдж — ученики увидят его на экране достижений')}
          emptyAction={
            <Button variant="secondary" size="sm" onClick={() => setCreating(true)}>
              {t('Добавить бейдж')}
            </Button>
          }
        />
      ) : (
        <div className="lay-3">
          {sorted.map((row) => (
            <section key={row.id} className={`card card-pad badgetile${row.is_active ? '' : ' badgetile--off'}${row.id === editing?.id ? ' badgetile--on' : ''}`}>
              <div className="badgetile__top">
                <span className="badgetile__medal" aria-hidden="true">
                  <Icon name={(row.icon || 'medal') as IconName} size={24} />
                </span>
                <span className="badgetile__acts">
                  <Switch
                    checked={row.is_active}
                    aria-label={t('Показывать бейдж: {name}', { name: row.name })}
                    disabled={update.isPending}
                    onCheckedChange={(next) => update.mutate({ id: row.id, is_active: next }, { onError: fail })}
                  />
                  <RowMenu>
                    <RowMenuItem onClick={() => setEditing(row)}>{t('Править')}</RowMenuItem>
                    <RowMenuItem risk onClick={() => remove.mutate(row.id, { onError: fail })}>
                      {t('Удалить')}
                    </RowMenuItem>
                  </RowMenu>
                </span>
              </div>
              <div className="badgetile__text">
                <span className="t-card">{row.name}</span>
                {row.description && <span className="t-note">{row.description}</span>}
              </div>
              <div className="badgetile__rule">
                <span className="t-note">{row.metric_title}</span>
                <b className="num">{row.threshold}</b>
              </div>
            </section>
          ))}
        </div>
      )}

      <EditDrawer
        open={creating || editing !== null}
        onClose={() => {
          setCreating(false)
          setEditing(null)
        }}
        title={editing ? editing.name : t('Новый бейдж')}
        sub={t('Мера и порог: «решено 100 заданий», «7 дней подряд»')}
      >
        <RowForm
          key={editing?.id ?? 'new'}
          fields={fields()}
          row={
            editing
              ? {
                  code: editing.code,
                  name: editing.name,
                  description: editing.description,
                  metric: editing.metric,
                  threshold: editing.threshold,
                  icon: editing.icon,
                  order: editing.order,
                  is_active: editing.is_active,
                }
              : { is_active: true, threshold: 1, order: 100, icon: 'medal' }
          }
          busy={create.isPending || update.isPending}
          submitLabel={editing ? t('Сохранить') : t('Завести')}
          onCancel={() => {
            setCreating(false)
            setEditing(null)
          }}
          onSubmit={(values) =>
            editing
              ? update.mutate({ id: editing.id, ...payload(values) }, { onSuccess: () => setEditing(null), onError: fail })
              : create.mutate(payload(values), { onSuccess: () => setCreating(false), onError: fail })
          }
        />
      </EditDrawer>
    </div>
  )
}
