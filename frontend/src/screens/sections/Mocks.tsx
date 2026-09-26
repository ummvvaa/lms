/**
 * Пробные — экран академического директора.
 *
 * До фазы 31 здесь был один блок «Мок упал — нужно вмешаться»: ни внести
 * результат, ни собрать пробный, ни завести задание было нельзя. Право
 * на всё это у Кымбат было, а войти в него можно было только через
 * админку Django.
 *
 * Разделы: результаты, цели, теория, пробные экзамены, банк заданий
 * и открытые ответы учеников (Writing, Speaking), которые проверяются руками.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../../api/hooks'
import ExamGoals from '../../components/ExamGoals'
import TheoryManager from '../../components/TheoryManager'
import ExamResults from '../../components/ExamResults'
import OpenAnswers from '../../components/OpenAnswers'
import PlatformMocks from '../../components/PlatformMocks'
import { BankSummary, MockExams, QuestionBank } from '../../components/QuestionBank'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import { Chip, ErrorNote, ListPanel, Loading, ScreenHead, ScreenTabs } from '../../components/ui'
import { t } from '../../i18n'
import type { ExamData } from './data'

type Section = 'results' | 'goals' | 'mocks' | 'bank' | 'theory' | 'open'

export default function Mocks() {
  const navigate = useNavigate()
  const [section, setSection] = useState<Section>('results')
  const { data, isLoading, error } = useDashboard<ExamData>('exam')
  const schoolIsEmpty = useSchoolIsEmpty()

  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  // банк заданий наполняют и до появления учеников: пробный собирают
  // заранее, а не в день экзамена
  if (schoolIsEmpty && section === 'results')
    return (
      <div>
        <Tabs section={section} onPick={setSection} />
        <EmptyDashboard
          title={t('Пробные')}
          hint={t('Здесь появятся результаты и просадки')}
          what={t('Результаты вносятся, когда есть кому их вносить.')}
          detail={t('Падение балла относительно прошлой попытки система находит сама.')}
        />
      </div>
    )

  return (
    <div>
      <ScreenHead
        title={t('Пробные')}
        subtitle={t('Результаты, сами пробные и банк заданий, из которого они собираются.')}
      />

      <Tabs section={section} onPick={setSection} />

      {section === 'results' && (
        <>
          <ExamResults />
          <PlatformMocks />
          <ListPanel
            title={t('Мок упал — нужно вмешаться')}
            rows={data.mock_drops}
            limit={30}
            onOpen={(id) => navigate(`/students/${id}`)}
            right={(row) => (
              <Chip tone="risk" className="num">
                {row.exam_type} {row.delta}
              </Chip>
            )}
          />
        </>
      )}

      {section === 'mocks' && (
        <>
          <BankSummary />
          <MockExams />
        </>
      )}

      {section === 'goals' && <ExamGoals />}

      {section === 'theory' && <TheoryManager />}

      {section === 'bank' && <QuestionBank />}

      {section === 'open' && <OpenAnswers />}
    </div>
  )
}

function Tabs({ section, onPick }: { section: Section; onPick: (value: Section) => void }) {
  const tabs: { key: Section; title: string }[] = [
    { key: 'results', title: 'Результаты' },
    { key: 'goals', title: 'Цели по экзаменам' },
    { key: 'theory', title: 'Теория' },
    { key: 'mocks', title: 'Пробные экзамены' },
    { key: 'bank', title: 'Банк заданий' },
    // Writing и Speaking проверяет человек: ответы учеников ждут здесь
    { key: 'open', title: 'Открытые ответы' },
  ]
  return (
    <ScreenTabs
      value={section}
      onChange={onPick}
      items={tabs.map((tab) => ({ value: tab.key, label: t(tab.title) }))}
    />
  )
}
