import { t } from '../i18n'
import MappedImport from './MappedImport'

export default function RequirementsImport() {
  return (
    <MappedImport
      path="/requirements/import/"
      title={t('Файл с требованиями вузов')}
      note={t('XLSX или CSV, ключ строки — вуз и программа')}
      hint={t(
        'Колонки сопоставляются с полями требований: вуз, программа, уровень, пороги IELTS/TOEFL/SAT/ACT/GPA, предметы, портфолио, примечания, ссылка. Обязательны вуз и программа. Записи придут с плашкой «не подтверждено» — снимет её директор по поступлению, сверив с сайтом.',
      )}
      missing={t('Назначьте колонки «Название вуза» и «Название программы».')}
      required={['university', 'program']}
      invalidate={[['directory']]}
      resultText={(report) =>
        t('Заведено требований: {created}, обновлено: {updated}, без изменений: {unchanged}', {
          created: report.created,
          updated: report.updated,
          unchanged: report.unchanged,
        })
      }
    />
  )
}
