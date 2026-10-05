/**
 * «Импорт»: мастер импорта и загрузки списков.
 *
 * Мастер один на все домены: колонки файла он узнаёт по реестру соответствий
 * сервера — таблица поступления (лист — группа, ученик по ФИО) и список
 * учеников с почтой или логином (поля профилей любого домена). Неузнанную
 * колонку человек назначает сам. Открыт администратору и академическому
 * директору; какие домены человек вправе писать, решает сервер.
 *
 * Вторая вкладка администратора — файлы, которые заводят строки: контакты
 * родителей, выступления, требования вузов, стипендии, банк заданий.
 *
 * Директор на том же адресе видит историю загрузок по своему домену —
 * что загружено и что можно отменить — и подсказку, что данные вносятся
 * руками или вставкой текста.
 */
import { useState, type ReactNode } from 'react'
import { useDomainMeta } from '../api/hooks'
import { type Domain } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import RowsImport, { type ImportedRow } from '../components/RowsImport'
import RequirementsImport from '../components/RequirementsImport'
import QuestionsImport from '../components/QuestionsImport'
import ScholarshipsImport from '../components/ScholarshipsImport'
import ImportWizard from '../components/ImportWizard'
import ImportHistory from '../components/ImportHistory'
import ManualEntryNote from '../components/ManualEntryNote'
import { ErrorNote, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { t, tk } from '../i18n'

/** Загрузки домена, которые заводят строки, а не правят поля: контакты, выступления,
 *  требования вузов и стипендии (фаза 44), банк заданий. Поля профилей грузит мастер. */
function listsOf(code: string): { key: string; tab: string; body: ReactNode }[] {
  if (code === 'behavior') {
    return [
      {
        key: 'contacts',
        tab: tk('Контакты родителей'),
        body: (
          <RowsImport
            title={t('Файл со списком контактов')}
            note={t('XLSX или CSV, ученик ищется по почте')}
            hint={t(
              'Колонки распознаются по заголовку первой строки: почта ученика, ФИО родителя, кем приходится, телефон, почта, способ связи, примечание, основной. Обязательны первые две.',
            )}
            previewPath="/contacts/import/preview/"
            applyPath="/contacts/import/apply/"
            applyLabel={t('Завести контакты')}
            invalidate={[['contacts']]}
            columns={[
              { key: 'full_name', title: t('ФИО'), cell: (row: ImportedRow) => String(row.full_name || '—') },
              {
                key: 'student',
                title: t('Ученик'),
                cell: (row: ImportedRow) => String(row.student_name || row.student_email || '—'),
              },
              {
                key: 'contact',
                title: t('Связь'),
                cell: (row: ImportedRow) => String(row.phone || row.email || '—'),
              },
            ]}
          />
        ),
      },
    ]
  }
  if (code === 'sport') {
    return [
      {
        key: 'competitions',
        tab: tk('Соревнования'),
        body: (
          <RowsImport
            title={t('Файл со списком выступлений')}
            note={t('XLSX или CSV, ученик ищется по почте')}
            hint={t(
              'Колонки распознаются по заголовку первой строки: почта ученика, название соревнования, вид спорта, уровень, дата, результат, сертификат, ссылка. Обязательны первые две.',
            )}
            previewPath="/competitions/import/preview/"
            applyPath="/competitions/import/apply/"
            applyLabel={t('Завести выступления')}
            invalidate={[['competitions'], ['dashboard']]}
            columns={[
              { key: 'name', title: t('Соревнование'), cell: (row: ImportedRow) => String(row.name || '—') },
              {
                key: 'student',
                title: t('Участник'),
                cell: (row: ImportedRow) => String(row.student_name || row.student_email || '—'),
              },
              { key: 'result', title: t('Результат'), cell: (row: ImportedRow) => String(row.result || '—') },
            ]}
          />
        ),
      },
    ]
  }
  if (code === 'admission') {
    return [
      { key: 'requirements', tab: tk('Требования вузов'), body: <RequirementsImport /> },
      { key: 'scholarships', tab: tk('Стипендии'), body: <ScholarshipsImport /> },
    ]
  }
  if (code === 'exam') return [{ key: 'questions', tab: tk('Банк заданий'), body: <QuestionsImport /> }]
  return []
}

/** Загрузки списков и справочников одним рядом вкладок — в порядке доменов. */
const allLists = () => ['behavior', 'sport', 'admission', 'exam'].flatMap((code) => listsOf(code))

/** Администратор: мастер импорта и загрузки списков. */
function AdminImport() {
  // поля профилей всех доменов грузит мастер по реестру соответствий (05.10.2026):
  // вкладки «Поля по CSV» с ручным сопоставлением колонок больше нет. Вторая
  // вкладка — файлы, которые заводят строки: контакты, выступления, требования
  // вузов, стипендии, банк заданий — у каждого свой разбор
  const [mode, setMode] = useState<'wizard' | 'lists'>('wizard')
  const lists = allLists()
  const [what, setWhat] = useState('contacts')
  const list = lists.find((row) => row.key === what)

  return (
    <div>
      <ScreenHead
        title={t('Импорт')}
      />
      <ScreenTabs
        value={mode}
        onChange={(value) => setMode(value as 'wizard' | 'lists')}
        items={[
          { value: 'wizard', label: t('Мастер импорта') },
          { value: 'lists', label: t('Списки и справочники') },
        ]}
      />

      {mode === 'wizard' && <ImportWizard />}

      {mode === 'lists' && <ScreenTabs value={what} onChange={setWhat} items={lists.map((row) => ({ value: row.key, label: t(row.tab) }))} />}
      {mode === 'lists' && list && <div key={list.key}>{list.body}</div>}

      <ImportHistory />
    </div>
  )
}

/** Директор: история загрузок по своему домену и подсказка, куда идти с данными.
 *
 *  У директора по поступлению здесь же мастер таблицы поступления (фаза 65):
 *  таблицу ведёт он сам, и просить администратора залить её было бы лишним
 *  звеном — файл с паролями учеников не должен ходить по рукам. */
function UploadsForDirector({ mine, curator = false }: { mine?: Domain; curator?: boolean }) {
  // владелец домена — тот же мастер, что у администратора (фаза 72):
  // чужие колонки он видит помеченными «домен не ваш, будет пропущен»
  return (
    <div>
      <ScreenHead
        title={t('Импорт')}
        subtitle={
          curator
            ? t(
                'Файл → что заполняем → проверка → готово. Пишутся только ваши группы: лист чужой группы — ошибка листа.',
              )
            : mine
              ? t('Файл → что заполняем → проверка → готово. Пишется только домен «{domain}».', { domain: mine.title })
              : t('Файл → что заполняем → проверка строк → готово.')
        }
      />
      <ImportWizard />
      {/* подсказка «файлы загружает администратор» — для директоров; куратор
          вносит данные своих групп сам, и руками, и файлом */}
      {!curator && <ManualEntryNote history={false} />}
      <ImportHistory />
    </div>
  )
}

export default function ImportScreen() {
  const { me } = useAuth()
  const meta = useDomainMeta()

  if (meta.isLoading) return <Loading />
  if (meta.error) return <ErrorNote error={meta.error} />
  if (me?.role === 'admin') return <AdminImport />
  return (
    <UploadsForDirector mine={meta.data?.domains.find((d) => d.is_mine)} curator={me?.role === 'curator'} />
  )
}
