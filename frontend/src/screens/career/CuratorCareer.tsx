/**
 * Профтест у куратора (решение владельца, 19.10.2026): только результаты своих
 * групп. Вкладки — группы; по группе — ученики со статусом по каждому открытому
 * тесту «сдан / не сдан», у сдавшего — результат на чтение. Создавать, менять
 * и удалять тесты куратор не может — ни кнопками, ни через API.
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { useCareerGroups, useCareerResults, type CareerResults } from '../../api/career'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { formatDate } from '../../lib/format'
import StudentResultsCard from './StudentResultsCard'

type StudentRow = CareerResults['students'][number]

function GroupResults({ group }: { group: number }) {
  const results = useCareerResults(group)
  const [opened, setOpened] = useState<{ student: number; attempt: number | null } | null>(null)
  if (results.isLoading) return <Loading kind="table" />
  if (results.error) return <ErrorNote error={results.error} />
  const data = results.data
  if (!data || data.tests.length === 0) return <DataCard title={t('Результаты')} empty={t('группе ещё не открыт ни один тест')} />
  const doneCell = (row: StudentRow, test: number) => {
    const cell = row.cells[String(test)]
    return cell?.status === 'done' && cell.attempt ? cell : null
  }
  const passedAll = (row: StudentRow) => data.tests.every((test) => doneCell(row, test.id) !== null)
  const firstDone = (row: StudentRow) => data.tests.map((test) => doneCell(row, test.id)).find((cell) => cell !== null)
  const words = (row: StudentRow) =>
    data.tests
      .map((test) => {
        const cell = doneCell(row, test.id)
        return `${test.title}: ${cell ? t('сдан {date}', { date: cell.finished_at ? formatDate(cell.finished_at) : '' }).trim() : t('не сдан')}`
      })
      .join(' · ')
  const passed = data.students.filter(passedAll).length
  return (
    <>
      <DataCard
        title={t('Результаты')}
        note={t('Сдали все открытые тесты: {done} из {total}', { done: passed, total: data.students.length })}
        count={data.students.length}
        empty={data.students.length === 0 && t('в группе нет учеников')}
      >
        <Rows>
          {data.students.map((row) => {
            const done = firstDone(row)
            return (
              <Row
                key={row.id}
                avatar={row.full_name}
                title={row.full_name}
                note={words(row)}
                right={<Chip size="sm" tone={passedAll(row) ? 'good' : 'neutral'}>{passedAll(row) ? t('сдал') : t('не сдал')}</Chip>}
                acts={
                  done ? (
                    <Button variant="outline" size="sm" onClick={() => setOpened({ student: row.id, attempt: done.attempt })}>
                      {t('Открыть')}
                    </Button>
                  ) : undefined
                }
              />
            )
          })}
        </Rows>
      </DataCard>
      {opened !== null && <StudentResultsCard student={opened.student} attempt={opened.attempt} manage={false} onClose={() => setOpened(null)} />}
    </>
  )
}

export default function CuratorCareer() {
  const [params, setParams] = useSearchParams()
  const groups = useCareerGroups()
  if (groups.isLoading) return <Loading kind="cards" />
  if (groups.error) return <ErrorNote error={groups.error} />
  const list = groups.data?.groups ?? []
  const wanted = params.get('group') ?? ''
  const code = list.some((g) => g.code === wanted) ? wanted : (list[0]?.code ?? '')
  const picked = list.find((g) => g.code === code) ?? null
  const pick = (next: string) => {
    const copy = new URLSearchParams(params)
    copy.set('group', next)
    setParams(copy, { replace: true })
  }
  return (
    <div>
      <ScreenHead title={t('Профтест')} subtitle={t('Результаты тестов профориентации по вашим группам')} />
      {list.length === 0 ? (
        <DataCard title={t('Вам не назначены группы')} empty={t('Обратитесь к администратору: группы куратору назначает он.')} />
      ) : (
        <>
          <ScreenTabs value={code} onChange={pick} items={list.map((group) => ({ value: group.code, label: group.code }))} />
          {picked && <GroupResults group={picked.id} />}
        </>
      )}
    </div>
  )
}
