/**
 * Настройки школы — экран администратора.
 *
 * Правила, которые школа решает сама: пороги, окна, сроки, лимиты. Каждое —
 * одно число: текущее значение, значение по умолчанию и границы приходят
 * с сервера (`core.school_rules`), здесь их не повторяем. Сохранили — число
 * действует со следующего запроса, без перезапуска; каждая правка и сброс —
 * строкой в истории раздела: кто, когда, было → стало.
 *
 * Веса формул и границы категорий — группы: правила, которые имеют смысл
 * только вместе. Группа — одна карточка с одной «Сохранить» и одной
 * «Сбросить»; сумму и порядок экран показывает сразу и не даёт сохранить
 * неверные, сервер проверяет то же самое ещё раз.
 *
 * Правил больше полусотни, поэтому экран разбит на разделы: список слева,
 * правила раздела справа. На телефоне список разделов — сам экран, раздел
 * открывается по нажатию и возвращает крошкой. Раздел живёт в адресе
 * (`?section=`): ссылку на него можно переслать, «Назад» ведёт к списку.
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  useResetSchoolRule,
  useResetSchoolRuleGroup,
  useSchoolRules,
  useSetSchoolRule,
  useSetSchoolRuleGroup,
  type SchoolRule,
  type SchoolRuleGroup,
  type SchoolRulesScreen,
} from '../api/hooks'
import Field from '../components/Field'
import { Row, Rows, Segmented } from '../components/patterns'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { plural, t, tn } from '../i18n'
import { formatDateTime, formatNumber } from '../lib/format'
import { usePhone } from '../phone'
import './school-settings.css'

const HOME = '/school-settings'

const whenAt = (value: string) =>
  formatDateTime(value)

/** Число правила, как его читает человек: дробное — с запятой по языку. */
const shown = (value: number) => formatNumber(value, { maximumFractionDigits: 1 })

/** Единица приходит с сервера на языке читающего; формы числа — через черту: «день|дня|дней». */
// eslint-disable-next-line i18n-concat -- число и единица измерения: порядок «15 мин» одинаков во всех трёх языках
const withUnit = (value: number, unit: string) => (unit ? `${shown(value)} ${plural(value, unit)}` : shown(value))

/** Единица в подписи поля — «Значение, дней»: последняя форма, она же родительный множественного. */
const unitName = (unit: string) => unit.split('|').at(-1) ?? unit

/** Значение из журнала: число показываем по языку, слова «да» и «нет» — как записаны. */
const logged = (value: string) => (/^-?\d+(\.\d+)?$/.test(value) ? shown(Number(value)) : value)

function RuleRow({ rule }: { rule: SchoolRule }) {
  const [draft, setDraft] = useState(String(rule.value))
  const [error, setError] = useState('')
  const save = useSetSchoolRule()
  const reset = useResetSchoolRule()
  const changed = draft.trim() !== String(rule.value)

  const submit = () =>
    save.mutate(
      { code: rule.code, value: draft.trim() },
      {
        onSuccess: () => {
          setError('')
          toast.success(t('Сохранено'))
        },
        onError: (e) => setError((e as Error).message),
      },
    )
  const restore = () =>
    reset.mutate(rule.code, {
      onSuccess: () => {
        setDraft(String(rule.default))
        setError('')
        toast.success(t('Вернули значение по умолчанию'))
      },
      onError: (e) => toast.error((e as Error).message),
    })

  return (
    <div className="rules__row">
      <div className="rules__text">
        <b>{t(rule.title)}</b>
        <span className="t-note">{t(rule.hint)}</span>
        <span className="t-note">
          {rule.kind === 'bool'
            ? Number(rule.default) ? t('По умолчанию: да') : t('По умолчанию: нет')
            : `${t('По умолчанию: {value}', { value: withUnit(rule.default, rule.unit) })} · ${t('от {min} до {max}', { min: shown(rule.minimum), max: shown(rule.maximum) })}`}
        </span>
      </div>
      <div className="rules__edit">
        {rule.kind === 'bool' ? (
          <Segmented
            value={draft.trim() === '0' ? '0' : '1'}
            onChange={(next) => {
              setDraft(next)
              setError('')
            }}
            label={t(rule.title)}
            items={[
              { value: '1', label: t('Да') },
              { value: '0', label: t('Нет') },
            ]}
          />
        ) : (
        <Field
          kind="number"
          name={rule.code}
          label={rule.unit ? `${t('Значение')}, ${unitName(rule.unit)}` : t('Значение')}
          value={draft}
          onChange={(value) => {
            setDraft(value)
            setError('')
          }}
          min={rule.minimum}
          max={rule.maximum}
          step={rule.step}
          error={error || undefined}
        />
        )}
        {rule.kind === 'bool' && error && <span className="t-note text-bad">{error}</span>}
        <div className="rules__actions">
          <Button size="sm" disabled={!changed || save.isPending} onClick={submit}>
            {t('Сохранить')}
          </Button>
          <Button variant="outline" size="sm" disabled={rule.is_default || reset.isPending} onClick={restore}>
            {t('Сбросить')}
          </Button>
        </div>
      </div>
    </div>
  )
}

/** Число из поля: пустое и не число — NaN, чтобы сумма не сошлась молча. */
const typed = (draft: string) => (draft.trim() === '' ? NaN : Number(draft.trim().replace(',', '.')))

/**
 * Группа правил одной карточкой: веса с суммой или границы по убыванию.
 * Сохраняется и сбрасывается только целиком — по одному вес не поправить.
 */
function GroupCard({ group, rules }: { group: SchoolRuleGroup; rules: SchoolRule[] }) {
  const [drafts, setDrafts] = useState<Record<string, string>>(() =>
    Object.fromEntries(rules.map((rule) => [rule.code, String(rule.value)])),
  )
  const [error, setError] = useState('')
  const save = useSetSchoolRuleGroup()
  const reset = useResetSchoolRuleGroup()

  const numbers = rules.map((rule) => typed(drafts[rule.code] ?? ''))
  const inBounds = rules.every((rule, index) => numbers[index] >= rule.minimum && numbers[index] <= rule.maximum)
  const sum = numbers.reduce((total, value) => total + value, 0)
  const holds =
    group.check === 'sum' ? sum === group.total : numbers.every((value, index) => index === 0 || value < numbers[index - 1])
  const changed = rules.some((rule) => (drafts[rule.code] ?? '').trim() !== String(rule.value))
  const isDefault = rules.every((rule) => rule.is_default)

  const submit = () =>
    save.mutate(
      { code: group.code, values: Object.fromEntries(rules.map((rule) => [rule.code, (drafts[rule.code] ?? '').trim()])) },
      {
        onSuccess: () => {
          setError('')
          toast.success(t('Сохранено'))
        },
        onError: (e) => setError((e as Error).message),
      },
    )
  const restore = () =>
    reset.mutate(group.code, {
      onSuccess: () => {
        setDrafts(Object.fromEntries(rules.map((rule) => [rule.code, String(rule.default)])))
        setError('')
        toast.success(t('Вернули значения по умолчанию'))
      },
      onError: (e) => toast.error((e as Error).message),
    })

  return (
    <DataCard title={t(group.title)} note={t(group.hint)}>
      <div className="rules__members">
        {rules.map((rule) => (
          <Field
            key={rule.code}
            kind="number"
            name={rule.code}
            label={rule.unit ? `${t(rule.title)}, ${unitName(rule.unit)}` : t(rule.title)}
            hint={
              rule.hint
                ? `${t(rule.hint)} · ${t('По умолчанию: {value}', { value: withUnit(rule.default, rule.unit) })}`
                : t('По умолчанию: {value}', { value: withUnit(rule.default, rule.unit) })
            }
            value={drafts[rule.code] ?? ''}
            onChange={(value) => {
              setDrafts((prev) => ({ ...prev, [rule.code]: value }))
              setError('')
            }}
            min={rule.minimum}
            max={rule.maximum}
            step={rule.step}
          />
        ))}
      </div>
      <div className="rules__groupfoot">
        {group.check === 'sum' ? (
          <span className={holds ? 't-note num' : 't-note num text-bad'} role="status">
            {Number.isNaN(sum)
              ? t('Заполните все поля: сумма должна быть {total}', { total: group.total })
              : holds
                ? t('Сумма: {sum} из {total}', { sum: shown(sum), total: group.total })
                : t('Сумма: {sum} из {total} — сохранить нельзя', { sum: shown(sum), total: group.total })}
          </span>
        ) : (
          <span className={holds ? 't-note' : 't-note text-bad'} role="status">
            {holds ? t('Границы идут по убыванию') : t('Каждая следующая граница должна быть меньше предыдущей — сохранить нельзя')}
          </span>
        )}
        {error && <span className="t-note text-bad">{error}</span>}
        <div className="rules__actions">
          <Button size="sm" disabled={!changed || !holds || !inBounds || save.isPending} onClick={submit}>
            {t('Сохранить')}
          </Button>
          <Button variant="outline" size="sm" disabled={isDefault || reset.isPending} onClick={restore}>
            {t('Сбросить группу')}
          </Button>
        </div>
      </div>
    </DataCard>
  )
}

/** Список разделов: сколько правил в каждом и сколько из них школа поменяла. */
function SectionList({ data, current }: { data: SchoolRulesScreen; current: string | null }) {
  return (
    <DataCard title={t('Разделы')}>
      <Rows>
        {data.sections.map((section) => {
          const own = data.rules.filter((rule) => rule.section === section.code)
          const changed = own.filter((rule) => !rule.is_default).length
          const count = tn(own.length, '{n} правило|{n} правила|{n} правил')
          return (
            <Row
              key={section.code}
              title={t(section.title)}
              note={changed ? `${count} · ${t('изменено: {n}', { n: changed })}` : count}
              to={`${HOME}?section=${section.code}`}
              current={section.code === current}
            />
          )
        })}
      </Rows>
    </DataCard>
  )
}

/** Правила одного раздела и его история: кто, когда, было → стало. */
function SectionRules({ data, code, phone = false }: { data: SchoolRulesScreen; code: string; phone?: boolean }) {
  const section = data.sections.find((row) => row.code === code)
  const history = data.history.filter((row) => row.section === code)
  if (!section) return null
  const own = data.rules.filter((rule) => rule.section === code)
  const single = own.filter((rule) => !rule.group)
  const groups = data.groups.filter((group) => group.section === code)
  return (
    <div className="rules__stack">
      {groups.map((group) => {
        const members = group.rules.flatMap((ruleCode) => own.filter((rule) => rule.code === ruleCode))
        // значения с сервера сменились (сохранили, сбросили) — поля берут их заново
        return <GroupCard key={`${group.code}-${members.map((rule) => rule.value).join('-')}`} group={group} rules={members} />
      })}
      {/* на телефоне название и пояснение раздела уже стоят в шапке экрана */}
      {single.length > 0 && (
        <DataCard title={phone ? t('Правила') : t(section.title)} note={phone ? undefined : t(section.note)}>
          {single.map((rule) => (
            // значение с сервера сменилось (сохранили, сбросили) — поле берёт его заново
            <RuleRow key={`${rule.code}-${rule.value}`} rule={rule} />
          ))}
        </DataCard>
      )}
      <DataCard title={t('История изменений')} count={history.length || undefined} empty={history.length === 0 && t('в этом разделе правила ещё не меняли')}>
        <Rows>
          {history.map((row) => (
            <Row key={row.id} title={t(row.title)} note={row.actor || t('система')} value={`${logged(row.old_value)} → ${logged(row.new_value)}`} when={whenAt(row.created_at)} />
          ))}
        </Rows>
      </DataCard>
    </div>
  )
}

export default function SchoolSettings() {
  const screen = useSchoolRules()
  const phone = usePhone()
  const [params] = useSearchParams()
  if (screen.isLoading) return <Loading kind="cards" />
  if (screen.isError) return <ErrorNote error={screen.error} />
  if (!screen.data) return null
  const data = screen.data
  const asked = data.sections.find((section) => section.code === params.get('section'))
  const subtitle = t('Пороги и окна, по которым платформа отмечает учеников. Новое значение действует сразу')

  if (phone) {
    // на телефоне раздел — отдельный экран: список правил длинный, двум колонкам места нет
    if (!asked)
      return (
        <div>
          <ScreenHead title={t('Настройки школы')} subtitle={subtitle} />
          <SectionList data={data} current={null} />
        </div>
      )
    return (
      <div>
        <ScreenHead title={t(asked.title)} subtitle={t(asked.note)} crumb={{ label: t('Настройки школы'), to: HOME }} />
        <SectionRules data={data} code={asked.code} phone />
      </div>
    )
  }

  const current = asked ?? data.sections[0]
  return (
    <div>
      <ScreenHead title={t('Настройки школы')} subtitle={subtitle} />
      <div className="rules__layout">
        <SectionList data={data} current={current.code} />
        <SectionRules data={data} code={current.code} />
      </div>
    </div>
  )
}
