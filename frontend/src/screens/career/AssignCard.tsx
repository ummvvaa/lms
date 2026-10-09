/**
 * Кому открыт тест: группы из составов учителя — целиком или отмеченные ученики.
 * Администратору — любые группы.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareerAssign, useCareerGroups, type CareerGroup, type CareerTestDetail } from '../../api/career'
import Modal from '../../components/Modal'
import Field from '../../components/Field'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Chip, EmptyNote, ErrorNote, Loading } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'

type Choice = { on: boolean; whole: boolean; students: Set<number> }

function initial(test: CareerTestDetail, groups: CareerGroup[]): Record<number, Choice> {
  const out: Record<number, Choice> = {}
  for (const group of groups) {
    const row = test.groups.find((g) => g.group === group.id)
    out[group.id] = { on: Boolean(row), whole: row ? row.whole : true, students: new Set(row?.students ?? []) }
  }
  return out
}

export default function AssignCard({ test, onClose }: { test: CareerTestDetail; onClose: () => void }) {
  const groups = useCareerGroups()
  const assign = useCareerAssign()
  const [state, setState] = useState<Record<number, Choice> | null>(null)
  if (groups.isLoading) return <Loading />
  if (groups.error) return <ErrorNote error={groups.error} />
  const rows = (groups.data?.groups ?? []).filter((g) => g.assignable)
  const choice = state ?? initial(test, rows)
  const update = (id: number, patch: Partial<Choice>) => setState({ ...choice, [id]: { ...choice[id], ...patch } })

  const save = () =>
    assign.mutate(
      {
        id: test.id,
        groups: rows
          .filter((g) => choice[g.id]?.on)
          .map((g) => ({ group: g.id, students: choice[g.id].whole ? null : [...choice[g.id].students] })),
      },
      { onSuccess: onClose, onError: (error) => toast.error(error.message) },
    )

  return (
    <Modal title={t('Кому открыт тест')} note={test.title} onClose={onClose}>
      {rows.length === 0 ? (
        <EmptyNote what={tk('у вас нет журнала профориентации — назначать некому')} />
      ) : (
        <Rows>
          {rows.map((group) => {
            const row = choice[group.id]
            return (
              <div key={group.id}>
                <Field kind="checkbox" name={`group-${group.id}`} label={`${group.code} · ${tn(group.students.length, '{n} ученик|{n} ученика|{n} учеников')}`} checked={row.on} onChange={(on) => update(group.id, { on })} />
                {row.on && (
                  <>
                    <Field
                      kind="select"
                      name={`whole-${group.id}`}
                      label={t('Кому в группе')}
                      value={row.whole ? 'whole' : 'picked'}
                      onChange={(value) => update(group.id, { whole: value === 'whole' })}
                      options={[
                        { value: 'whole', title: t('всей группе') },
                        { value: 'picked', title: t('отмеченным ученикам') },
                      ]}
                    />
                    {!row.whole && (
                      <Rows>
                        <ShowAll limit={30}>
                          {group.students.map((student) => (
                            <Row
                              key={student.id}
                              avatar={student.full_name}
                              title={student.full_name}
                              right={
                                <Field
                                  kind="checkbox"
                                  name={`student-${student.id}`}
                                  label={t('открыт')}
                                  checked={row.students.has(student.id)}
                                  onChange={(on) => {
                                    const next = new Set(row.students)
                                    if (on) next.add(student.id)
                                    else next.delete(student.id)
                                    update(group.id, { students: next })
                                  }}
                                />
                              }
                            />
                          ))}
                        </ShowAll>
                      </Rows>
                    )}
                    {!row.whole && row.students.size === 0 && <Chip tone="warn" size="sm">{t('никто не отмечен — тест никому не откроется')}</Chip>}
                  </>
                )}
              </div>
            )
          })}
        </Rows>
      )}
      <div className="toolbar ctest__foot">
        <Button disabled={assign.isPending} onClick={save}>
          {assign.isPending ? t('Сохраняется…') : t('Сохранить')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}
