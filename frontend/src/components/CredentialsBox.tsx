/**
 * Выданные временные пароли: показать один раз и дать скачать.
 *
 * Пока почта не настроена, раздавать пароли приходится руками. Файл
 * собирается сервером по запросу и нигде не хранится: список паролей
 * открытым текстом не должен лежать дольше, чем нужно, чтобы его скачать.
 *
 * После закрытия панели пароли не восстановить — в базе только хеши.
 * Об этом здесь сказано прямо, а не мелким шрифтом.
 */
import { download } from '../api/client'
import { t } from '../i18n'
import { Button } from './ui/button'
import DataTable from './DataTable'

export interface Credential {
  full_name: string
  email: string | null
  /** почта, а где её нет — логин: этим человек войдёт */
  login?: string
  password: string
}

type Issued = Credential

export default function CredentialsBox({ rows, onClose }: { rows: Credential[]; onClose: () => void }) {
  const save = () => download('/users/credentials/', { rows }, 'uchetnye-zapisi.csv')

  return (
    <section className="card card-pad users__link">
      <div className="row-between">
        <b>
          {t('Выданные пароли')} · {rows.length}
        </b>
        <Button variant="outline" size="sm" onClick={onClose}>
          {t('Скрыть')}
        </Button>
      </div>
      <p className="muted users__linktext">
        {t(
          'Пароли показываются один раз: в базе хранится только их отпечаток. Скачайте список, если письма не уходят, — потом восстановить их будет нельзя, только выпустить новые.',
        )}
      </p>

      <div className="users__wrap">
        <DataTable
          columns={[
            { key: 'name', title: t('ФИО'), width: '40%', cell: (row: Issued) => row.full_name || <span className="t-note">{t('без имени')}</span> },
            { key: 'email', title: t('Логин'), width: '35%', cell: (row: Issued) => row.login || row.email },
            { key: 'password', title: t('Временный пароль'), width: '25%', cell: (row: Issued) => <span className="users__password">{row.password}</span> },
          ]}
          rows={rows.slice(0, 30)}
          rowKey={(row) => row.login || row.email || row.full_name}
        />
        {rows.length > 30 && (
          <p className="muted">
            {t('и ещё {n} — они есть в файле', { n: rows.length - 30 })}
          </p>
        )}
      </div>

      <div className="toolbar mb-0 mt-3">
        <Button size="sm" onClick={save}>
          {t('Скачать списком')}
        </Button>
      </div>
    </section>
  )
}
