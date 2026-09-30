/**
 * Блокировки входа — раздел экрана «Пользователи» (фаза 36, D2).
 *
 * Список считает сервер тем же кодом, что и отказ на форме входа: кто
 * заперт (учётная запись или адрес), сколько неудач, когда откроется.
 * Администратор снимает блокировку кнопкой; попытки остаются в журнале.
 * Рядом — доверенные сети и пороги, чтобы было понятно, почему школьный
 * адрес не запирается.
 */
import { useLoginLocks, useUnlockLogin, type LoginLock } from '../api/hooks'
import { Chip, DataCard, ErrorNote, Loading } from './ui'
import { t, tn } from '../i18n'
import { Button } from './ui/button'

function opensIn(seconds: number): string {
  const minutes = Math.max(1, Math.ceil(seconds / 60))
  if (minutes < 60) return t('через {minutes} мин', { minutes })
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? t('через {hours} ч {minutes} мин', { hours, minutes: rest }) : t('через {hours} ч', { hours })
}

function Row({ lock }: { lock: LoginLock }) {
  const unlock = useUnlockLogin()
  return (
    <li className="rows__item locks__row">
      <div className="rows__body">
        <div className="locks__who">
          <Chip tone={lock.scope === 'address' ? 'warn' : 'neutral'}>
            {lock.scope === 'address' ? t('адрес') : t('учётная запись')}
          </Chip>
          <b>{lock.value}</b>
        </div>
        <p className="muted rows__sub">
          {tn(
            lock.failures,
            '{n} неудача подряд · вход откроется {when}|{n} неудачи подряд · вход откроется {when}|{n} неудач подряд · вход откроется {when}',
            { when: opensIn(lock.seconds) },
          )}
        </p>
      </div>
      <Button
        size="sm"
        disabled={unlock.isPending}
        onClick={() => unlock.mutate({ scope: lock.scope, value: lock.value })}
      >
        {t('Снять блокировку')}
      </Button>
    </li>
  )
}

export default function LoginLocks() {
  const locks = useLoginLocks()
  const data = locks.data

  return (
    <DataCard
      title={t('Блокировки входа')}
      note={
        data
          ? t('По записи — после {account} неудач, по адресу — после {address} за {minutes} мин', {
              account: data.account_threshold,
              address: data.address_threshold,
              minutes: data.window_minutes,
            })
          : t('Кто заперт после неудачных попыток и когда откроется')
      }
      hint={t(
        'Снятая блокировка не стирает журнал попыток. Порог по адресу и доверенные сети задаются в настройках контура: LOGIN_IP_FAILURES и LOGIN_TRUSTED_NETWORKS. Порог по учётной записи не меняется.',
      )}
      count={data?.locks.length}
    >
      {locks.isLoading && <Loading kind="table" />}
      {locks.isError && <ErrorNote error={locks.error} />}
      {data && (
        <>
          <p className="muted locks__trusted">
            {data.trusted_networks.length > 0
              ? t('Доверенные сети (по адресу не запираются): {networks}', { networks: data.trusted_networks.join(', ') })
              : t(
                  'Доверенных сетей нет — впишите адрес школы в LOGIN_TRUSTED_NETWORKS, иначе один ученик может запереть всех.',
                )}
          </p>
          {data.locks.length === 0 ? (
            <p className="muted rows__empty">{t('Сейчас никто не заблокирован.')}</p>
          ) : (
            <ul className="rows__list">
              {data.locks.map((lock) => (
                <Row key={`${lock.scope}:${lock.value}`} lock={lock} />
              ))}
            </ul>
          )}
        </>
      )}
    </DataCard>
  )
}
