import { t } from '../i18n'
import MappedImport from './MappedImport'

export default function ScholarshipsImport() {
  return (
    <MappedImport
      path="/scholarships-import/"
      title={t('Файл со списком стипендий')}
      note={t('XLSX или CSV, ключ строки — название и организатор')}
      hint={t(
        'Колонки сопоставляются с полями стипендии: название, организатор, страна, уровень, тип финансирования, сумма, валюта, основания, дедлайн, ссылка, требования, описание. Обязательно название. Записи придут с плашкой «не подтверждено» — снимет её директор по поступлению, сверив со страницей стипендии.',
      )}
      missing={t('Назначьте колонку «Название стипендии» — без неё строку не найти.')}
      required={['name']}
      invalidate={[['scholarships'], ['scholarship-overview']]}
      resultText={(report) =>
        t('Заведено стипендий: {created}, обновлено: {updated}, без изменений: {unchanged}', {
          created: report.created,
          updated: report.updated,
          unchanged: report.unchanged,
        })
      }
    />
  )
}
