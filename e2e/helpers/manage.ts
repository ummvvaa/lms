/**
 * Management-команды контура из браузерных сценариев.
 *
 * Нужны там, где шаг сценария и в жизни делается из терминала: очистка
 * базы, выдача одноразовой ссылки. Заводить ради этого ручки в API нельзя —
 * лишняя дверь в системе опаснее неудобства в тестах.
 */
import { execFileSync } from "node:child_process";
import path from "node:path";

const ROOT = path.join(__dirname, "..", "..");

export function manage(
  args: string[],
  env: Record<string, string> = {},
): string {
  const passEnv = Object.entries(env).flatMap(([name, value]) => [
    "-e",
    `${name}=${value}`,
  ]);
  return execFileSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      ...passEnv,
      "backend",
      "python",
      "manage.py",
      ...args,
    ],
    { cwd: ROOT, encoding: "utf8" },
  ).trim();
}

/**
 * Одноразовые записи прогона: девять ролей на `probe.local`.
 * Пароль уходит команде переменной окружения — из `e2e/.env`, других мест нет.
 */
export function createProbeUsers(): string {
  return manage(["create_probe_users"], {
    PROBE_PASSWORD: process.env.PROBE_PASSWORD ?? "",
  });
}

/** Убрать записи прогона насовсем — вместе с сессиями. Работает в любом режиме. */
export function purgeProbeUsers(): string {
  return manage(["purge_probe_users"]);
}

/** Полная очистка данных — шаг «очистить базу» сквозного сценария. */
export function resetAll(): void {
  manage(["reset_data", "--all", "--confirm", "УДАЛИТЬ ДАННЫЕ"]);
}

/**
 * Дождаться, что API отвечает через прокси разработки.
 *
 * Под нагрузкой полного прогона первые запросы после обнуления базы изредка
 * висели, и кнопка оставалась выключенной до таймаута сценария. Любой ответ
 * сервера, кроме 5xx, значит «дошёл»: 401 без входа — тоже ответ.
 */
export async function waitForApi(
  baseURL: string,
  limitMs = 30_000,
): Promise<void> {
  const until = Date.now() + limitMs;
  let last = "";
  while (Date.now() < until) {
    try {
      const response = await fetch(new URL("/api/auth/me/", baseURL), {
        signal: AbortSignal.timeout(5_000),
      });
      if (response.status < 500) return;
      last = `ответ ${response.status}`;
    } catch (error) {
      last = String(error);
    }
    await new Promise((done) => setTimeout(done, 500));
  }
  throw new Error(`API не ответил за ${limitMs / 1000} с: ${last}`);
}

/** Хвост лога службы контура — к упавшему сценарию, пока он свежий. */
export function serviceLog(service: string, lines = 200): string {
  try {
    return execFileSync(
      "docker",
      ["compose", "logs", "--no-color", "--tail", String(lines), service],
      { cwd: ROOT, encoding: "utf8" },
    );
  } catch (error) {
    return `лог ${service} не снялся: ${String(error).slice(0, 200)}`;
  }
}

/**
 * Убрать учётные записи, заведённые сценарием: он должен начинаться с нуля.
 *
 * Только под доменом прогона: физически удалять настоящие записи нельзя
 * (инвариант №13), а по одному префиксу однажды ушли две архивные записи
 * `journey.*@lms.local`, которые владелец просил оставить в архиве.
 */
export function dropUsers(prefix: string): void {
  manage([
    "shell",
    "-c",
    `from accounts.probe import probe_users; probe_users().filter(email__startswith="${prefix}").delete()`,
  ]);
}

/**
 * Пометить карточки, заведённые прогоном, вымышленными (фаза 64).
 * Признак явный, по домену одноразовых записей: посев ставит его сам,
 * чтобы `preflight` видел остатки, а `purge_fictional` их вычищал.
 */
export function markFictional(): void {
  manage(["mark_fictional", "--domain", "probe.local", "--yes"]);
}

/**
 * Учебная часть для прогона: учебный год, предметы, составы групп и недельное
 * расписание с учителем прогона. Учеников команда не заводит — их сеет
 * `seed.spec.ts` через API; отметки уроков тоже ставит сценарий.
 */
export function seedProbeAcademics(): string {
  return manage(["seed_probe_academics"]);
}
