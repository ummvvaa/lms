/**
 * Язык учётной записи прогона — русский.
 *
 * Сценарии ждут русские подписи, а язык вошедшего живёт на сервере
 * (`User.language`) и переживает контекст браузера: одна кнопка «Қазақша»,
 * нажатая обходом на «Профиле», перевела девять учётных записей и всё, что
 * шло после (полный прогон 12.10.2026). Поэтому перед работой под ролью язык
 * возвращается на русский — одним запросом, и только когда он не русский.
 */
import type { APIRequestContext, Cookie } from "@playwright/test";

const PREFERENCES = "/api/auth/me/preferences/";

/** Поставить русский язык записи, под которой открыт `request`. */
export async function russianOnServer(
  request: APIRequestContext,
  cookies: Cookie[],
): Promise<void> {
  const csrf = cookies.find((c) => c.name === "csrftoken")?.value ?? "";
  const response = await request.patch(PREFERENCES, {
    data: { language: "ru" },
    headers: { "X-CSRFToken": csrf },
  });
  if (!response.ok())
    throw new Error(`Не удалось вернуть русский язык: HTTP ${response.status()}`);
}
