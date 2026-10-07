import { t } from '../i18n'
import { Button } from './ui/button'
import { Input } from './ui/input'

export default function ImportFile({
  file,
  accept = '.csv,.xlsx,.xlsm',
  disabled,
  onSelect,
}: {
  file: File | null
  accept?: string
  disabled?: boolean
  onSelect: (file: File) => void
}) {
  return (
    <label className="filepick">
      <Input
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={(event) => {
          const selected = event.target.files?.[0]
          if (selected) onSelect(selected)
        }}
      />
      <Button size="sm" nativeButton={false} render={<span />}>
        {t('Выбрать файл')}
      </Button>
      <span className="muted filepick__name">{file ? file.name : t('Файл не выбран')}</span>
    </label>
  )
}
