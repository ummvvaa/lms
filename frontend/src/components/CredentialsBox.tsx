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

export interface Credential {
  full_name: string
  email: string
  password: string
}

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
        <table className="history users__table">
          <thead>
            <tr>
              <th>{t('ФИО')}</th>
              <th>{t('Логин')}</th>
              <th>{t('Временный пароль')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 30).map((row) => (
              <tr key={row.email}>
                <td>{row.full_name || '—'}</td>
                <td>{row.email}</td>
                <td className="users__password">{row.password}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length > 30 && (
          <p className="muted">
            {t('и ещё')} {rows.length - 30} — {t('они есть в файле')}
          </p>
        )}
      </div>

      <div className="toolbar" style={{ marginBottom: 0, marginTop: 12 }}>
        <Button size="sm" onClick={save}>
          {t('Скачать списком')}
        </Button>
      </div>
    </section>
  )
}
