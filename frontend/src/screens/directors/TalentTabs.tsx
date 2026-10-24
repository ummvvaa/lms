/** Вкладки раздела «Предметы и треки» директора талантов (макет меню, 24.10.2026): два экрана — один пункт. */
import { useLocation, useNavigate } from 'react-router'
import { ScreenTabs } from '../../components/ui'
import { t } from '../../i18n'

export default function TalentTabs() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  return (
    <ScreenTabs
      value={pathname === '/tracks' ? '/tracks' : '/subjects'}
      onChange={(next) => navigate(next)}
      items={[
        { value: '/subjects', label: t('Предметы') },
        { value: '/tracks', label: t('Треки') },
      ]}
    />
  )
}
