/**
 * Кнопка удаления с человеческим подтверждением.
 *
 * Текст диалога приходит с сервера: он считает настоящие связи и говорит
 * «У неё 4 вуза, 12 задач и 3 эссе — они тоже уйдут в архив», а не
 * «Вы уверены?». Слово для набора сервер тоже назначает сам — там, где
 * удаление тянет за собой чужую работу.
 *
 * Кнопка покрашена в цвет риска и стоит отдельно от сохранения.
 */
import { useState } from 'react'
import { useDeletePreview, useDeleteRecord, type DeletePreview } from '../api/hooks'
import ConfirmDialog from './ConfirmDialog'
import { Button } from './ui/button'

export default function DeleteButton({
  model,
  id,
  path,
  invalidate,
  label = 'Удалить',
  compact = true,
  /** внутри меню строки: текст пункта, а не кнопка */
  inMenu = false,
  onDeleted,
}: {
  /** метка модели, `app_label.ModelName` — по ней сервер считает последствия */
  model: string
  id: number
  /** путь списка в API: `/students/`, `/attempts/` и так далее */
  path: string
  /** какие запросы обновить после удаления */
  invalidate: string[][]
  label?: string
  compact?: boolean
  inMenu?: boolean
  onDeleted?: (detail: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const info = useDeletePreview(model, open ? id : null)
  const remove = useDeleteRecord(path, invalidate)

  const preview: DeletePreview | undefined = info.data
  const busy = remove.isPending || info.isLoading

  return (
    <>
      {inMenu ? (
        <button
          type="button"
          className="rowmenu__action"
          onClick={() => {
            setError(null)
            setOpen(true)
          }}
        >
          {label}
        </button>
      ) : (
        <Button
          size={compact ? 'sm' : undefined}
          variant="destructive"
          onClick={() => {
            setError(null)
            setOpen(true)
          }}
        >
          {label}
        </Button>
      )}

      <ConfirmDialog
        open={open}
        title={preview?.what ?? 'Удалить запись?'}
        what={
          preview
            ? preview.summary
              ? `${preview.kind}. Вместе с записью уйдёт связанное: ${preview.summary}.`
              : `${preview.kind}. Связанных записей у неё нет.`
            : 'Считаем, что уйдёт вместе с записью…'
        }
        consequences={preview?.consequences ?? []}
        confirmWord={preview?.confirm_word ?? ''}
        confirmLabel={preview?.soft === false ? 'Удалить насовсем' : 'Удалить'}
        busy={busy}
        error={error ?? (info.isError ? 'Не удалось посчитать последствия' : null)}
        onCancel={() => setOpen(false)}
        onConfirm={() => {
          if (preview?.blocked) {
            setError('Удалить нельзя, пока на запись ссылаются другие')
            return
          }
          remove.mutate(id, {
            onSuccess: (result) => {
              setOpen(false)
              onDeleted?.(result.detail)
            },
            onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось удалить'),
          })
        }}
      />
    </>
  )
}
