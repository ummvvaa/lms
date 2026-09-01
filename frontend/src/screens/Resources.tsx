/**
 * Ресурсы школы (фаза 45): статьи и памятки, которые сейчас лежат в чатах.
 *
 * Читают все, ведут пять директоров — у раздела нет владельца-домена:
 * про экзамены пишет академический директор, про заявки — директор
 * по поступлению, про олимпиады — директор талантов. Кто написал, видно
 * в самой карточке.
 *
 * Это не материалы олимпиадников: тот раздел закрыт группой и живёт
 * файлами, а здесь открытый текст школы.
 */
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  useResource,
  useResourceActions,
  useResourceOverview,
  useResources,
  type ResourceRow,
} from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import Empty from '../components/Empty'
import Modal from '../components/Modal'
import RowForm, { type FieldDef, type RowValues } from '../components/RowForm'
import RowMenu, { RowMenuItem } from '../components/RowMenu'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import { CatalogCard, Segmented, StatCard, StatRow } from '../components/patterns'
import Icon from '../layout/icons'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import './resources.css'
import { t } from '../i18n'

/** Ведут раздел пять директоров: у ресурса нет владельца-домена. */
const KEEPERS = [
  'director_behavior',
  'director_admission',
  'director_exam',
  'director_talent',
  'director_sport',
]

function accentOf(row: { category_accent: string }): string {
  return row.category_accent || 'indigo'
}

/** Цвет категории — тон плитки и шапки карточки. */
function toneOf(row: { category_accent: string }): 'brand' | 'teal' | 'indigo' | 'ok' | 'warn' | 'risk' {
  const accent = accentOf(row)
  return (['brand', 'teal', 'indigo', 'ok', 'warn', 'risk'].includes(accent) ? accent : 'indigo') as
    'brand' | 'teal' | 'indigo' | 'ok' | 'warn' | 'risk'
}

function Card({ row, onOpen }: { row: ResourceRow; onOpen: () => void }) {
  return (
    <CatalogCard
      icon="openbook"
      tone={toneOf(row)}
      title={row.title}
      subtitle={row.summary || undefined}
      chips={
        <>
          <Badge variant="mute">{row.category_name}</Badge>
          <Badge variant="mute">{`${row.reading_minutes} ${t('мин чтения')}`}</Badge>
          {row.is_read && <Badge variant="ok">{t('прочитано')}</Badge>}
        </>
      }
      footer={t('Читать')}
      onFooter={onOpen}
    />
  )
}

/** Рекомендуемое: широкая карточка — цветная область слева, текст справа. */
function FeaturedCard({ row, onOpen }: { row: ResourceRow; onOpen: () => void }) {
  return (
    <article className={`card res__featuredcard res__featuredcard--${toneOf(row)}`}>
      <div className="res__featuredart" aria-hidden="true">
        <Icon name="openbook" size={30} />
      </div>
      <div className="res__featuredbody">
        <div className="res__meta">
          <Badge variant="mute">{row.category_name}</Badge>
          <Badge variant="mute">{`${row.reading_minutes} ${t('мин чтения')}`}</Badge>
          {row.is_read && <Badge variant="ok">{t('прочитано')}</Badge>}
        </div>
        <b className="res__title">{row.title}</b>
        {row.summary && <p className="muted res__summary">{row.summary}</p>}
        <button type="button" className="res__read" onClick={onOpen}>
          {t('Читать')}
          <Icon name="chevronRight" size={13} />
        </button>
      </div>
    </article>
  )
}

/** Материал целиком: свой адрес, чтобы его можно было отправить. */
function Article({ id }: { id: number }) {
  const navigate = useNavigate()
  const article = useResource(id)
  const { markRead } = useResourceActions()

  if (article.isLoading) return <Loading />
  if (article.error) return <ErrorNote error={article.error} />
  const row = article.data
  if (!row) return null

  return (
    <div>
      <ScreenHead
        eyebrow={row.category_name}
        title={row.title}
        subtitle={row.summary || undefined}
        actions={
          <>
            <Button variant="outline" onClick={() => navigate('/resources')}>
              {t('К списку')}
            </Button>
            <Button
              variant={row.is_read ? 'outline' : 'default'}
              disabled={markRead.isPending}
              onClick={() =>
                markRead.mutate(
                  { id: row.id, read: !row.is_read },
                  { onSuccess: (result) => toast.success(result.detail) },
                )
              }
            >
              {row.is_read ? t('Снять отметку') : t('Прочитано')}
            </Button>
          </>
        }
      />
      <div className="card card-pad res__article">
        <div className="res__meta">
          <span className="muted res__time">
            {row.reading_minutes} {t('мин чтения')}
          </span>
          {row.author_name && <span className="muted">{row.author_name}</span>}
          {row.published_on && (
            <span className="muted">{new Date(row.published_on).toLocaleDateString('ru')}</span>
          )}
        </div>
        <div className="res__body">
          {row.body.split('\n').map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </div>
        {row.tags_list.length > 0 && (
          <div className="res__tags">
            {row.tags_list.map((tag) => (
              <span key={tag} className="muted res__tag">
                #{tag}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Resources() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { me } = useAuth()
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [editing, setEditing] = useState<ResourceRow | null>(null)
  const [creating, setCreating] = useState(false)

  const overview = useResourceOverview()
  const list = useResources(filters)
  const { create, update, remove } = useResourceActions()

  if (id) return <Article id={Number(id)} />

  const rows = list.data?.results ?? []
  const featured = rows.filter((row) => row.is_featured)
  const rest = rows.filter((row) => !row.is_featured)
  const categories = overview.data?.categories ?? []
  const keeps = KEEPERS.includes(me?.role ?? '')
  const hasFilters = Object.values(filters).some(Boolean)

  const fields: FieldDef[] = [
    { name: 'title', label: t('Заголовок'), kind: 'text', required: true },
    {
      name: 'category',
      label: t('Категория'),
      kind: 'select',
      required: true,
      options: categories.map((row) => ({ value: String(row.id), title: row.name })),
    },
    { name: 'summary', label: t('Короткое описание'), kind: 'text' },
    { name: 'body', label: t('Текст материала'), kind: 'textarea' },
    { name: 'reading_minutes', label: t('Время чтения, минут'), kind: 'number' },
    { name: 'tags', label: t('Метки через запятую'), kind: 'text' },
    { name: 'published_on', label: t('Дата публикации'), kind: 'date' },
    { name: 'is_featured', label: t('Рекомендуем'), kind: 'checkbox' },
    { name: 'is_published', label: t('Показывать ученикам'), kind: 'checkbox' },
  ]

  const payload = (values: RowValues): Record<string, unknown> => ({
    ...values,
    title: String(values.title ?? ''),
    summary: values.summary ?? '',
    body: values.body ?? '',
    tags: values.tags ?? '',
    reading_minutes: values.reading_minutes ?? 5,
    published_on: values.published_on || null,
  })

  return (
    <div>
      <ScreenHead
        title={`${t('Ресурсы')} · ${overview.data?.total ?? 0}`}
        subtitle={t('Статьи и памятки школы: о стипендиях, заявках, вузах, подготовке и олимпиадах.')}
        actions={
          keeps ? <Button onClick={() => setCreating(true)}>{t('Добавить материал')}</Button> : undefined
        }
      />

      <StatRow>
        <StatCard icon="openbook" tone="indigo" label={t('Материалов')} value={overview.data?.total ?? 0} />
        <StatCard icon="star" tone="brand" label={t('Рекомендуем')} value={overview.data?.featured ?? 0} />
        <StatCard icon="check" tone="ok" label={t('Прочитано вами')} value={overview.data?.read ?? 0} />
      </StatRow>

      <div className="toolbar">
        <Input
          className="res__search"
          placeholder={t('Заголовок, описание или метка')}
          value={filters.q ?? ''}
          onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
        />
        <span className="toolbar__spacer" />
        <Badge variant="mute" className="num">
          {rows.length}
        </Badge>
      </div>

      {/* Категории — ряд чипов-переключателей: их бывает шесть и больше,
          и ряд кнопок читался как панель приборов */}
      <Segmented
        value={filters.category ?? ''}
        onChange={(next) => setFilters((prev) => ({ ...prev, category: next }))}
        label={t('Категории материалов')}
        items={[
          { value: '', label: t('Все'), icon: 'layers' },
          ...categories.map((row) => ({
            value: row.code,
            label: row.count === undefined ? row.name : `${row.name} · ${row.count}`,
            icon: 'openbook' as const,
          })),
        ]}
      />

      {list.isLoading && <Loading kind="cards" />}
      {list.error && <ErrorNote error={list.error} />}

      {featured.length > 0 && (
        <>
          <span className="eyebrow">{t('Рекомендуем')}</span>
          <div className="res__featured">
            {featured.map((row) => (
              <div key={row.id} className="res__wrap">
                <FeaturedCard row={row} onOpen={() => navigate(`/resources/${row.id}`)} />
                {keeps && (
                  <div className="res__rowmenu">
                    <RowMenu>
                      <RowMenuItem onClick={() => setEditing(row)}>{t('Править')}</RowMenuItem>
                      <RowMenuItem
                        risk
                        onClick={() =>
                          remove.mutate(row.id, { onError: (error) => toast.error(error.message) })
                        }
                      >
                        {t('Удалить')}
                      </RowMenuItem>
                    </RowMenu>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {rest.length > 0 && (
        <div className="catgrid">
          {rest.map((row) => (
            <div key={row.id} className="res__wrap">
              <Card row={row} onOpen={() => navigate(`/resources/${row.id}`)} />
              {keeps && (
                <div className="res__rowmenu">
                  <RowMenu>
                    <RowMenuItem onClick={() => setEditing(row)}>{t('Править')}</RowMenuItem>
                    <RowMenuItem
                      risk
                      onClick={() =>
                        remove.mutate(row.id, { onError: (error) => toast.error(error.message) })
                      }
                    >
                      {t('Удалить')}
                    </RowMenuItem>
                  </RowMenu>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {!list.isLoading && rows.length === 0 && (
        <Empty
          icon="openbook"
          title={hasFilters ? t('По этому запросу материалов нет') : t('В разделе пока нет материалов')}
          what={
            keeps
              ? t('Заведите первую памятку — ученики увидят её здесь.')
              : t('Памятки пишут директора — как появятся, они будут здесь.')
          }
          hint={t(
            'Ресурсы ведут пять директоров: про экзамены — академический, про заявки — по поступлению, про олимпиады — талантов. Категории пополняются справочником.',
          )}
          action={keeps ? t('Добавить материал') : undefined}
          onAction={keeps ? () => setCreating(true) : undefined}
        />
      )}

      {creating && (
        <Modal
          title={t('Новый материал')}
          note={t('Обязательны заголовок и категория')}
          onClose={() => setCreating(false)}
        >
          <RowForm
            fields={fields}
            // умолчания новой памятки: показывать ученикам и пять минут чтения.
            // Пустая галочка «Показывать ученикам» означала бы, что материал
            // заводят и он никому не виден — а кнопка называется «Опубликовать»
            row={{ is_published: true, reading_minutes: 5 }}
            busy={create.isPending}
            submitLabel={t('Опубликовать')}
            onCancel={() => setCreating(false)}
            onSubmit={(values) =>
              create.mutate(payload(values), {
                onSuccess: () => setCreating(false),
                onError: (error) => toast.error(error.message),
              })
            }
          />
        </Modal>
      )}

      {editing && (
        <Modal title={editing.title} onClose={() => setEditing(null)}>
          <RowForm
            fields={fields}
            row={{
              title: editing.title,
              category: editing.category,
              summary: editing.summary,
              body: editing.body,
              reading_minutes: editing.reading_minutes,
              tags: editing.tags,
              published_on: editing.published_on,
              is_featured: editing.is_featured,
              is_published: editing.is_published,
            }}
            busy={update.isPending}
            submitLabel={t('Сохранить')}
            onCancel={() => setEditing(null)}
            onSubmit={(values) =>
              update.mutate(
                { id: editing.id, ...payload(values) },
                {
                  onSuccess: () => setEditing(null),
                  onError: (error) => toast.error(error.message),
                },
              )
            }
          />
        </Modal>
      )}
    </div>
  )
}
