/**
 * «Кружки» — адрес один, экран по роли: у администратора раздел кружков.
 */
import { useAuth } from '../../auth/AuthContext'
import Clubs from './Clubs'

export default function ClubsScreen() {
  const { me } = useAuth()
  if (me?.role === 'admin') return <Clubs />
  return null
}
