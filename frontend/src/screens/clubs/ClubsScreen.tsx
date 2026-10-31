/**
 * «Кружки» — адрес один, экран по роли: у администратора раздел кружков, у ученика — свои кружки.
 */
import { useAuth } from '../../auth/AuthContext'
import Clubs from './Clubs'
import StudentClubs from './StudentClubs'

export default function ClubsScreen() {
  const { me } = useAuth()
  return me?.role === 'admin' ? <Clubs /> : <StudentClubs />
}
