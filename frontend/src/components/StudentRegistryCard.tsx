/**
 * Реестровая карточка ученика: кто это, класс, группа, почта, выпуск.
 *
 * Ведёт её администратор. Доменных полей здесь нет и быть не может —
 * их правят директора у себя (инвариант №1). До фазы 30 карточку можно
 * было только завести: исправить опечатку в фамилии было нечем вовсе.
 */
import { useState } from 'react'
import { useStudyGroups, useUpdateStudent, type StudentCard } from '../api/hooks'
import { DataCard, Metric, MetricRow } from './ui'
import { t } from '../i18n'
import { NativeSelect } from './ui/native-select'
import { Input } from './ui/input'

export default function StudentRegistryCard({ card, canEdit }: { card: StudentCard; canEdit: boolean }) {
  const groups = useStudyGroups()
  const update = useUpdateStudent()
  const [open, setOpen] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [form, setForm] = useState({
    last_name: card.last_name,
    first_name: card.first_name,
    middle_name: card.middle_name ?? '',
    email: card.email,
    grade: String(card.grade),
    group: card.group === null ? '' : String(card.group),
    graduation_year: String(card.graduation_year),
  })

  return (
    <DataCard
      title={t('Кто это')}
      note={t('Реестровая карточка школы')}
      hint={t(
        'Имя, класс, группа, почта и год выпуска. Доменные данные — баллы, посещаемость, портфолио — ведут директора у себя, здесь их нет.',
      )}
      right={
        canEdit ? (
          <button className="btn btn-ghost btn-sm" onClick={() => setOpen(!open)}>
            {open ? t('Закрыть') : t('Изменить')}
          </button>
        ) : undefined
      }
    >
      {!open && (
        <MetricRow>
          <Metric value={card.grade} label={t('Класс')} />
          <Metric value={card.group_code ?? '—'} label={t('Учебная группа')} />
          <Metric value={card.graduation_year} label={t('Год выпуска')} />
        </MetricRow>
      )}
      {!open && <p className="muted rows__empty">{card.email}</p>}

      {open && (
        <div className="rowform">
          {(
            [
              ['last_name', 'Фамилия'],
              ['first_name', 'Имя'],
              ['middle_name', 'Отчество'],
              ['email', 'Почта'],
            ] as const
          ).map(([name, label]) => (
            <label key={name} className="rowform__field">
              <span className="rowform__label">{t(label)}</span>
              <Input
                value={form[name]}
                onChange={(event) => setForm({ ...form, [name]: event.target.value })}
              />
            </label>
          ))}
          <label className="rowform__field">
            <span className="rowform__label">{t('Класс')}</span>
            <Input
              className="num"
              type="number"
              min={1}
              max={12}
              value={form.grade}
              onChange={(event) => setForm({ ...form, grade: event.target.value })}
            />
          </label>
          <label className="rowform__field">
            <span className="rowform__label">{t('Учебная группа')}</span>
            <NativeSelect
              value={form.group}
              onChange={(event) => setForm({ ...form, group: event.target.value })}
            >
              <option value="">{t('— без группы —')}</option>
              {(groups.data?.results ?? []).map((row) => (
                <option key={row.id} value={row.id}>
                  {row.code}
                </option>
              ))}
            </NativeSelect>
          </label>
          <label className="rowform__field">
            <span className="rowform__label">{t('Год выпуска')}</span>
            <Input
              className="num"
              type="number"
              value={form.graduation_year}
              onChange={(event) => setForm({ ...form, graduation_year: event.target.value })}
            />
          </label>

          {problem && <p className="chip chip-risk rowform__problem">{problem}</p>}

          <div className="rowform__actions">
            <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
              {t('Отмена')}
            </button>
            <button
              className="btn btn-primary btn-sm"
              disabled={update.isPending}
              onClick={() => {
                if (!form.last_name.trim() || !form.first_name.trim()) {
                  setProblem('Фамилия и имя обязательны — без них ученика не найти в списке')
                  return
                }
                setProblem(null)
                update.mutate(
                  {
                    id: card.id,
                    last_name: form.last_name.trim(),
                    first_name: form.first_name.trim(),
                    middle_name: form.middle_name.trim(),
                    email: form.email.trim().toLowerCase(),
                    grade: Number(form.grade),
                    group: form.group ? Number(form.group) : null,
                    graduation_year: Number(form.graduation_year),
                  },
                  {
                    onSuccess: () => setOpen(false),
                    onError: (error) =>
                      setProblem(error instanceof Error ? error.message : 'Не удалось сохранить'),
                  },
                )
              }}
            >
              {t('Сохранить')}
            </button>
          </div>
        </div>
      )}
    </DataCard>
  )
}
