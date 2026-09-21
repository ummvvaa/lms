/**
 * Обход всех экранов всех ролей (фаза 81) — инструмент, а не разовый скрипт.
 *
 * Ходит по контрольному списку адресов (`helpers/routes.ts`) под каждой ролью
 * на двух ширинах, снимает каждый экран, нажимает всё, что можно нажать,
 * и пишет манифест: элементы, что открылось от нажатия, ошибки консоли,
 * коды ответов, пустые блоки, ряды плиток, переполнение по ширине.
 *
 * В обычный прогон не входит (`testIgnore` в конфигурации) — запускается руками
 * и в двух состояниях данных:
 *
 *   # пустая школа: заведён один ученик, больше ничего
 *   SCREEN_WALK=1 WALK_STATE=empty ./run.sh --project=screen-walk tests/screen-walk.spec.ts
 *   # наполненная школа: обычный посев
 *   SCREEN_WALK=1 WALK_STATE=filled ./run.sh --project=seed --project=screen-walk \
 *     tests/seed.spec.ts tests/screen-walk.spec.ts
 *
 * Снимки и манифест ложатся в `shots/walk/<состояние>/`. Реестр находок
 * собирает `build_screen_review.py` — он читает манифест, а не снимки.
 *
 * Пустое состояние обходчик заводит сам: обнуляет базу и создаёт одного
 * ученика с группой и куратором — ровно то, что школа увидит первого сентября.
 * Management-командой ученики не сеются (правило проекта): всё через API
 * под администратором, как это делал бы человек.
 */
import { mkdirSync } from "node:fs";
import { test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { resetAll } from "../helpers/manage";
import { probeEmail } from "../helpers/roles";
import { apiPost } from "../helpers/session";
import { ROUTES } from "../helpers/routes";
import {
  LAPTOP,
  PHONE,
  openAs,
  saveManifest,
  walkDir,
  walkScreen,
  type WalkScreen,
} from "../helpers/walk";

test.describe.configure({ mode: "serial", timeout: 1_800_000 });

const STATE = process.env.WALK_STATE === "filled" ? "filled" : "empty";
const DIR = walkDir(STATE);
const PUPIL = probeEmail("walk-pupil");

const screens: WalkScreen[] = [];
let counter = 0;
/** Кнопки, открывшие окно на ноутбуке: только их нажимаем на телефоне. */
const dialogOpeners = new Set<string>();

test.beforeAll(() => {
  mkdirSync(DIR, { recursive: true });
});

test.afterAll(() => {
  saveManifest(DIR, screens);
});

/** Куратор без групп видит пустой кабинет: обход мерил бы не то (фаза 81). */
async function assignCurator(page: Page, groupId?: number): Promise<void> {
  const mine = (await (await page.request.get("/api/curators/")).json()) as {
    results: { id: number; email: string; groups: { code: string }[] }[];
  };
  const curator = mine.results.find(
    (row) => row.email === probeEmail("curator"),
  );
  if (!curator || curator.groups.length > 0) return;
  const groups = (await (
    await page.request.get("/api/groups/?page_size=100")
  ).json()) as {
    results: { id: number }[];
  };
  const target = groupId ?? groups.results[0]?.id;
  if (!target) return;
  await apiPost(page, "/api/curator-assignments/", {
    group: target,
    curator: curator.id,
    since: "2026-09-01",
  });
}

test("состояние школы для обхода", async ({ browser }) => {
  if (STATE === "filled") {
    // посев назначает куратора сам, но его учётная запись живёт один прогон:
    // при повторном обходе по той же базе назначение остаётся за прежней записью
    const context = await browser.newContext({
      storageState: statePath("admin"),
    });
    const page = await context.newPage();
    await page.goto("/dashboard");
    await assignCurator(page);
    await context.close();
    return;
  }

  resetAll();
  const context = await browser.newContext({
    storageState: statePath("admin"),
  });
  const page = await context.newPage();
  await page.goto("/dashboard");

  const group = await apiPost<{ id: number }>(page, "/api/groups/", {
    code: "11A",
    grade: 11,
  });
  await apiPost(page, "/api/students/", {
    last_name: "Первый",
    first_name: "Ученик",
    email: PUPIL,
    group: group.id,
    graduation_year: 2027,
  });
  // карточка ученика прогона связывается с его учётной записью по почте (фаза 16)
  await apiPost(page, "/api/students/", {
    last_name: "Прогон",
    first_name: "Айгерим",
    email: probeEmail("student"),
    group: group.id,
    graduation_year: 2027,
  });
  const users = (await (
    await page.request.get(`/api/users/?search=${probeEmail("curator")}`)
  ).json()) as {
    results: { id: number; email: string }[];
  };
  const curator = users.results.find((u) => u.email === probeEmail("curator"))!;
  await apiPost(page, "/api/curator-assignments/", {
    group: group.id,
    curator: curator.id,
    since: "2026-09-01",
  });
  await context.close();
});

/** Карточка ученика: у куратора — своей группы, у остальных — любого. */
async function pupilId(page: Page, role: string): Promise<number> {
  const path =
    role === "curator"
      ? "/api/curator/students/"
      : "/api/students/?page_size=500";
  const body = (await (await page.request.get(path)).json()) as {
    results?: { id: number; email?: string }[];
  };
  const rows = body.results ?? [];
  return (
    rows.find((r) => r.email === probeEmail("student"))?.id ?? rows[0]?.id ?? 0
  );
}

for (const [role, routes] of Object.entries(ROUTES)) {
  test(`обход: ${role}`, async ({ browser }) => {
    for (const viewport of [LAPTOP, PHONE]) {
      const page = await openAs(browser, role, viewport);
      const id = routes.some((r) => r.includes("{id}"))
        ? await pupilId(page, role)
        : 0;
      for (const route of routes) {
        counter += 1;
        const url = route.replace("{id}", String(id));
        screens.push(
          await walkScreen(page, {
            role,
            url,
            width: viewport.width,
            state: STATE,
            dir: DIR,
            counter,
            // на телефоне нажимаем только то, что на ноутбуке открыло окно:
            // смотрим ширину окна, а не повторяем весь обход вдвое
            clickable:
              viewport.width <= 640
                ? (name) => dialogOpeners.has(name)
                : undefined,
            onDialog: (name) => dialogOpeners.add(name),
          }),
        );
        // манифест пишется по ходу: обход длинный, и прерванный должен оставить
        // то, что успел собрать
        saveManifest(DIR, screens);
      }
      await page.context().close();
    }
  });
}
