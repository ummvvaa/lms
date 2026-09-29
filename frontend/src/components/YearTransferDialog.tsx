/**
 * «Перевести на следующий год» — у администратора на вкладке групп.
 *
 * Сначала предпросмотр: какая группа куда переходит и сколько учеников,
 * кто выпускается в архив. Потом подтверждение набранным числом — как
 * у раздачи паролей: одна кнопка стоила бы школе года. Второй раз в том
 * же учебном году перевод не запускается — окно так и говорит.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useYearTransfer, useYearTransferPlan } from '../api/hooks'
import { t } from '../i18n'
import Modal from './Modal'
import { Row, Rows } from './patterns'
import { Chip, ErrorNote, Loading } from './ui'
import { Button } from './ui/button'
import { Input } from './ui/input'

export default function YearTransferDialog({ onClose }: { onClose: () => void }) {
  const plan = useYearTransferPlan(true)
  const transfer = useYearTransfer()
  const [typed, setTyped] = useState('')

  return (
    <Modal title={t('Перевести на следующий год')} onClose={onClose}>
      {plan.isLoading && <Loading />}
      {plan.error && <ErrorNote error={plan.error} />}
      {plan.data && (
        <>
          <p className="t-note">{plan.data.detail}</p>
          {plan.data.done ? (
            <Chip tone="warn">{plan.data.done.detail}</Chip>
          ) : (
            <>
              <Rows>
                {plan.data.moves.map((move) => (
                  <Row
                    key={move.group_id}
                    title={move.group}
                    note={move.to === null ? t('выпуск: в архив, вход закрыт') : `${move.from} → ${move.to}`}
                    right={<span className="num">{move.students}</span>}
                  />
                ))}
              </Rows>
              <p className="t-note">
                {t('Наберите число затронутых учеников, чтобы подтвердить:')} <b className="num">{plan.data.confirm}</b>
              </p>
              <div className="acad__actions">
                <Input
                  inputMode="numeric"
                  aria-label={t('Число учеников')}
                  value={typed}
                  onChange={(event) => setTyped(event.target.value)}
                />
                <Button
                  disabled={transfer.isPending || typed.trim() !== plan.data.confirm}
                  onClick={() =>
                    transfer.mutate(typed.trim(), {
                      onSuccess: (result) => {
                        toast.success(result.detail)
                        onClose()
                      },
                      onError: (error) => toast.error(error.message),
                    })
                  }
                >
                  {t('Перевести')}
                </Button>
              </div>
            </>
          )}
        </>
      )}
    </Modal>
  )
}
