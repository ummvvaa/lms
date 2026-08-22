/** Готовит сессии всех ролей до прогона сценариев. */
import { prepareStates } from './helpers/auth-state'

export default async function globalSetup() {
  await prepareStates(process.env.E2E_BASE_URL ?? 'http://localhost:5173')
}
