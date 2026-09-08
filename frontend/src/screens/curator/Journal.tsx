/**
 * Журнал куратора (фаза 62): действия по его группам — свои, Кымбат, Асем,
 * Салтанат. Читается из общего журнала правок по снимку группы (фаза 60):
 * ученик, переведённый в другую группу, не уносит с собой чужую историю.
 * Не редактируется; выгружается тем же кодом XLSX.
 */
import { toast } from 'sonner'
import { downloadFile } from '../../api/client'
import { useCuratorJournal } from '../../api/hooks'
import { ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import GroupSwitch from './GroupSwitch'
import { useGroup } from './state'
import './curator.css'

export default function CuratorJournal() {
  const [group, setGroup] = useGroup()
  const { data, isLoading, error } = useCuratorJournal(group)

  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const download = () =>
    void downloadFile(
      `/curator/journal/export/${group !== 'all' ? `?group=${encodeURIComponent(group)}` : ''}`,
      'journal.xlsx',
    ).catch(() => toast.error(t('Не удалось собрать файл')))

  return (
    <div>
      <ScreenHead
        title={t('Журнал')}
        subtitle={t('Здесь всё, что делали вы и владельцы доменов по вашим группам. Записи не удаляются.')}
        actions={
          <Button variant="outline" onClick={download}>
            {t('Выгрузить')}
          </Button>
        }
      />
      <GroupSwitch groups={data.groups} value={group} onChange={setGroup} />

      <div className="card card-pad">
        {data.results.length === 0 && <p className="muted">{t('Пока ничего не менялось')}</p>}
        <div className="tblwrap">
          <table className="tbl">
            <colgroup>
              <col style={{ width: '14%' }} />
              <col style={{ width: '16%' }} />
              <col style={{ width: '20%' }} />
              <col style={{ width: '22%' }} />
              <col style={{ width: '28%' }} />
            </colgroup>
            <thead>
              <tr>
                <th>{t('Когда')}</th>
                <th>{t('Кто')}</th>
                <th>{t('Ученик')}</th>
                <th>{t('Что')}</th>
                <th>{t('Стало')}</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((row) => (
                <tr key={row.id}>
                  <td data-head="" className="squeue__when">
                    {new Date(row.at).toLocaleString('ru')}
                  </td>
                  <td data-label={t('Кто')}>
                    {row.who}
                    {row.role && <span className="muted"> · {row.role}</span>}
                  </td>
                  <td data-label={t('Ученик')}>
                    {row.student_id ? <a href={`/students/${row.student_id}`}>{row.student}</a> : row.student}
                    {row.group && <span className="muted"> · {row.group}</span>}
                  </td>
                  <td data-label={t('Что')}>{row.what}</td>
                  <td data-label={t('Стало')}>
                    {row.was && <span className="muted">{row.was} → </span>}
                    {row.now}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
