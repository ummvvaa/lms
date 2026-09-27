/**
 * Учебная часть в сценариях: уроки и журналы по API, подстановка `{lesson}`
 * и `{course}` в адреса обхода.
 *
 * Уроки заводит `seed_probe_academics` (структура), отметки ставит посев
 * через API как учитель. Адрес с плейсхолдером, для которого у роли нет
 * записи (пустая школа), обходчик пропускает — это не находка.
 */
import type { Page } from "@playwright/test";
import { probeEmail } from "./roles";

export interface LessonRow {
  id: number;
  course: number;
  date: string;
  slot: number;
  is_live?: boolean;
  actual_teacher?: { id: number; short: string } | null;
  subject: { id: number; title: string; short_title: string };
  cohort: { id: number; name: string; group: string; students?: number };
}

/** Дата «N дней назад» в виде YYYY-MM-DD. */
export const daysAgo = (n: number): string =>
  new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);

/** Уроки роли за период — то, что видит её экран расписания. */
export async function lessonsBetween(
  page: Page,
  from: string,
  to: string,
): Promise<LessonRow[]> {
  const response = await page.request.get(
    `/api/acad/lessons/?from=${from}&to=${to}`,
  );
  if (!response.ok()) return [];
  const body = (await response.json()) as { lessons?: LessonRow[] };
  return body.lessons ?? [];
}

/** Прошедший урок роли за последние три недели — для `/lessons/{lesson}`. */
export async function findLesson(page: Page): Promise<number> {
  const rows = await lessonsBetween(page, daysAgo(21), daysAgo(0));
  const past = rows.filter((row) => row.date <= daysAgo(0) && row.is_live !== false);
  return past[past.length - 1]?.id ?? rows[0]?.id ?? 0;
}

/** Журнал роли — для `/journals/{course}`: у учителя свой, у Кымбат любой. */
export async function findCourse(page: Page, role: string): Promise<number> {
  if (role === "teacher") {
    const response = await page.request.get("/api/acad/teacher/journals/");
    if (response.ok()) {
      const body = (await response.json()) as { rows?: { id: number }[] };
      if (body.rows?.[0]) return body.rows[0].id;
    }
  }
  const rows = await lessonsBetween(page, daysAgo(21), daysAgo(0));
  return rows[0]?.course ?? 0;
}

/** Ученик из состава урока — для `/students/{id}` у учителя. */
export async function findTaughtStudent(page: Page): Promise<number> {
  const lesson = await findLesson(page);
  if (!lesson) return 0;
  const detail = (await (
    await page.request.get(`/api/acad/lessons/${lesson}/`)
  ).json()) as { roster?: { id: number; email?: string }[] };
  const roster = detail.roster ?? [];
  return (
    roster.find((row) => row.email === probeEmail("student"))?.id ??
    roster[0]?.id ??
    0
  );
}

export interface RouteIds {
  id: number;
  lesson: number;
  course: number;
}

/** Собрать номера для плейсхолдеров адресов роли. */
export async function routeIds(
  page: Page,
  role: string,
  routes: string[],
  pupil: () => Promise<number>,
): Promise<RouteIds> {
  const needs = (mark: string) => routes.some((route) => route.includes(mark));
  const lesson = needs("{lesson}") ? await findLesson(page) : 0;
  const course = needs("{course}") ? await findCourse(page, role) : 0;
  const id = needs("{id}")
    ? role === "teacher"
      ? await findTaughtStudent(page)
      : await pupil()
    : 0;
  return { id, lesson, course };
}

/**
 * Адрес с подставленными номерами. `null` — у роли нет записи под
 * плейсхолдер (пустая школа без уроков): адрес пропускается.
 */
export function substitute(route: string, ids: RouteIds): string | null {
  let url = route;
  for (const [mark, value] of [
    ["{id}", ids.id],
    ["{lesson}", ids.lesson],
    ["{course}", ids.course],
  ] as const) {
    if (!url.includes(mark)) continue;
    if (!value) return null;
    url = url.replace(mark, String(value));
  }
  return url;
}

/** Отметить урок: список отметок или «все были». */
export async function markLesson(
  page: Page,
  lesson: number,
  rows: { student: number; mark: "present" | "absent" | "late" }[] | "all",
): Promise<void> {
  const csrf =
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? "";
  const response = await page.request.post(
    `/api/acad/lessons/${lesson}/attendance/`,
    {
      data: rows === "all" ? { all_present: true } : { rows },
      headers: { "X-CSRFToken": csrf },
    },
  );
  if (!response.ok())
    throw new Error(`отметка урока ${lesson}: HTTP ${response.status()}`);
}
