/**
 * Настройки школы — экран администратора.
 *
 * Правила, которые школа решает сама: пороги, окна, сроки. Каждое — одно
 * число: текущее значение, значение по умолчанию и границы приходят
 * с сервера (`core.school_rules`), здесь их не повторяем. Сохранили — число
 * действует со следующего запроса, без перезапуска; каждая правка и сброс —
 * строкой в истории внизу: кто, когда, было → стало.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useResetSchoolRule, useSchoolRules, useSetSchoolRule, type SchoolRule } from '../api/hooks'
import Field from '../components/Field'
import { Row, Rows } from '../components/patterns'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { SCHOOL_TIME_ZONE } from '../lib/dates'
import './academics/academics.css'
import './school-settings.css'

const whenAt = (value: string) =>
  new Date(value).toLocaleString('ru', { dateStyle: 'short', timeStyle: 'short', timeZone: SCHOOL_TIME_ZONE })

const withUnit = (value: number | string, unit: string) => (unit === '%' ? `${value} %` : unit ? `${value} ${t(unit)}` : String(value))

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
          {t('По умолчанию')} {withUnit(rule.default, rule.unit)} · {t('от')} {rule.minimum} {t('до')} {rule.maximum}
        </span>
      </div>
      <div className="rules__edit">
        <Field
          kind="number"
          name={rule.code}
          label={rule.unit ? `${t('Значение')}, ${t(rule.unit)}` : t('Значение')}
          value={draft}
          onChange={(value) => {
            setDraft(value)
            setError('')
          }}
          min={rule.minimum}
          max={rule.maximum}
          step={1}
          error={error || undefined}
        />
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

export default function SchoolSettings() {
  const screen = useSchoolRules()
  if (screen.isLoading) return <Loading kind="cards" />
  if (screen.isError) return <ErrorNote error={screen.error} />
  if (!screen.data) return null
  const { rules, history } = screen.data
  const groups = [...new Set(rules.map((rule) => rule.group))]

  return (
    <div>
      <ScreenHead title={t('Настройки школы')} subtitle={t('Пороги и окна, по которым платформа отмечает учеников. Новое значение действует сразу')} />
      <div className="acad__cols">
        <div className="acad__stack">
          {groups.map((group) => (
            <DataCard key={group} title={t(group)}>
              {rules
                .filter((rule) => rule.group === group)
                .map((rule) => (
                  // значение с сервера сменилось (сохранили, сбросили) — поле берёт его заново
                  <RuleRow key={`${rule.code}-${rule.value}`} rule={rule} />
                ))}
            </DataCard>
          ))}
        </div>
        <div className="acad__stack">
          <DataCard title={t('История изменений')} count={history.length || undefined} empty={history.length === 0 && t('правила ещё не меняли — действуют значения по умолчанию')}>
            <Rows>
              {history.map((row) => (
                <Row key={row.id} title={t(row.title)} note={row.actor || t('система')} value={`${row.old_value} → ${row.new_value}`} when={whenAt(row.created_at)} />
              ))}
            </Rows>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
