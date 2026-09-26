/**
 * Блок профиля учителя: учётная запись, предметы, кабинет, что он видит.
 * Напоминаний в профиле нет — только колокольчик (решение владельца).
 */
import { useTeacherProfile } from '../../api/academics'
import { Row, Rows } from '../../components/patterns'
import { counted, DataCard, ErrorNote, Loading } from '../../components/ui'
import { t } from '../../i18n'
import { NoteCard } from './shared'

export default function TeacherProfile() {
  const { data, isLoading, error } = useTeacherProfile()
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  return (
    <div className="acad__cols">
      <div className="acad__stack">
        <DataCard title={t('Учётная запись')}>
          <Rows>
            <Row title={t('Имя')} value={data.teacher.full_name} />
            <Row title={t('Почта')} value={data.teacher.email} />
            <Row title={t('Роль')} value={t('Учитель')} />
            <Row title={t('Предметы')} value={data.teacher.subject_titles || null} none={t('не назначены')} />
            <Row title={t('Кабинет')} value={data.teacher.room || null} none={t('не закреплён')} />
            <Row title={t('Нагрузка')} value={data.hours || null} none={t('уроков нет')} note={`${counted(data.journals, ['журнал', 'журнала', 'журналов'])}`} />
          </Rows>
        </DataCard>
      </div>
      <div className="acad__stack">
        <NoteCard title={t('Что вы видите')}>{t('Только свои уроки и учеников своих составов: оценки и пропуски по вашим предметам, группу и куратора. Заметки кураторов, документы и поступление вам не видны.')}</NoteCard>
        <NoteCard title={t('Кто видит ваши оценки')}>{t('Ученик — свои. Куратор группы, Кымбат и администратор — все. Родители — в отчёте раз в месяц.')}</NoteCard>
      </div>
    </div>
  )
}
