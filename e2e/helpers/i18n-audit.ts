/**
 * Проверка перевода на снимке каталога (`CATALOG_LANG=kk|en`).
 *
 * На экране и в открытом окне собирается весь видимый текст и подписи
 * (`placeholder`, `aria-label`, `title`, `alt`) и сверяется с русскими
 * исходниками, у которых перевод есть (`shots/i18n-keys.json`, собирает
 * `build_i18n_keys.py` из словарей фронта и каталога сервера). Совпало —
 * значит, на экране русский там, где должен быть перевод. В английском
 * отдельно копится любая кириллица: данные людей (ФИО, названия групп)
 * там законны, остальное — на разбор глазами. На обеих ширинах — кнопки,
 * ссылки и плашки, вылезшие за край своей карточки или окна; на телефоне
 * ещё обрезанный без многоточия текст и горизонтальная прокрутка страницы.
 */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";

export const LANG = (process.env.CATALOG_LANG ?? "") as "" | "kk" | "en";

export interface I18nFinding {
  file: string;
  untranslated: string[];
  cyrillic: string[];
  clipped: string[];
  escaped: string[];
  overflow: boolean;
}

type Keys = { exact: Set<string>; patterns: RegExp[] };
let cache: Keys | null = null;

function keys(): Keys {
  if (cache) return cache;
  const file = path.join(__dirname, "..", "shots", "i18n-keys.json");
  const all = existsSync(file)
    ? (JSON.parse(readFileSync(file, "utf8")) as Record<string, string[]>)
    : {};
  const list = all[LANG] ?? [];
  const exact = new Set<string>();
  const patterns: RegExp[] = [];
  for (const key of list) {
    const forms = key.split("|");
    for (const form of forms) {
      if (/\{\w+\}/.test(form)) {
        const source = form
          .split(/\{\w+\}/)
          .map((piece) => piece.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
          .join(".+?");
        // подстановки почти без слов («{a} — {b}, {c}») совпали бы с любой фразой:
        // шаблон берётся, только если вне подстановок есть хотя бы четыре буквы
        const letters = form.replace(/\{\w+\}/g, "").match(/\p{L}/gu) ?? [];
        if (letters.length >= 4) patterns.push(new RegExp(`^${source}$`, "s"));
      } else exact.add(form.trim());
    }
  }
  cache = { exact, patterns };
  return cache;
}

const CYRILLIC = /[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]/;

/** Весь видимый текст и подписи — на странице или только в открытом окне. */
async function visibleTexts(page: Page, scope: "page" | "dialog"): Promise<string[]> {
  return page.evaluate((scope) => {
    const root =
      scope === "dialog"
        ? (document.querySelector('[role="dialog"], [role="alertdialog"]') ?? document.body)
        : document.body;
    const out = new Set<string>();
    const visible = (el: Element) => {
      const rects = el.getClientRects();
      if (!rects.length) return false;
      const style = getComputedStyle(el);
      return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0;
    };
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = (node.textContent ?? "").replace(/\s+/g, " ").trim();
      const parent = node.parentElement;
      if (!text || !parent || !visible(parent)) continue;
      if (parent.closest("script, style, [aria-hidden='true']")) continue;
      out.add(text);
      // текст, разбитый на узлы внутри одного элемента, — ещё и целиком
      const whole = (parent.textContent ?? "").replace(/\s+/g, " ").trim();
      if (whole && whole.length < 300) out.add(whole);
    }
    for (const el of Array.from(root.querySelectorAll("[placeholder], [aria-label], [title], img[alt]"))) {
      if (!visible(el)) continue;
      for (const name of ["placeholder", "aria-label", "title", "alt"]) {
        const value = el.getAttribute(name)?.trim();
        if (value) out.add(value);
      }
    }
    return [...out];
  }, scope);
}

/** Обрезанный без многоточия текст и прокрутка вбок — признаки сломанной вёрстки на телефоне. */
async function layout(page: Page): Promise<{ clipped: string[]; overflow: boolean }> {
  return page.evaluate(() => {
    const clipped: string[] = [];
    const selector = "button, a, th, td, label, [data-slot='badge'], h1, h2, h3, .t-caps, .eyebrow";
    for (const el of Array.from(document.querySelectorAll<HTMLElement>(selector))) {
      if (!el.getClientRects().length || !el.textContent?.trim()) continue;
      const style = getComputedStyle(el);
      if (style.textOverflow === "ellipsis") continue;
      if (el.scrollWidth > el.clientWidth + 2 && (style.overflow === "hidden" || style.overflowX === "hidden"))
        clipped.push(el.textContent.replace(/\s+/g, " ").trim().slice(0, 80));
    }
    // под эмуляцией телефона ширина окна растёт вместе с содержимым — сравниваем с экраном
    const overflow = document.documentElement.scrollWidth > screen.width + 1;
    return { clipped: [...new Set(clipped)].slice(0, 12), overflow };
  });
}

/** Кнопки, ссылки и плашки, вылезшие за край карточки или окна: длинная надпись не переносится. */
async function escaped(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    const selector = "button, a, [data-slot='badge'], .chip";
    for (const el of Array.from(document.querySelectorAll<HTMLElement>(selector))) {
      if (!el.getClientRects().length || !el.textContent?.trim()) continue;
      const box = el.closest<HTMLElement>(".card, [role='dialog'], [role='alertdialog']");
      if (!box || box === el) continue;
      // внутри прокручиваемой полосы (таблица, вкладки) выход за край законен
      let scrolls = false;
      for (let node = el.parentElement; node && node !== box; node = node.parentElement) {
        const x = getComputedStyle(node).overflowX;
        if (x === "auto" || x === "scroll" || x === "hidden" || x === "clip") scrolls = true;
      }
      if (scrolls) continue;
      const inner = el.getBoundingClientRect();
      const outer = box.getBoundingClientRect();
      if (inner.right > outer.right + 1 || inner.left < outer.left - 1)
        out.push(el.textContent.replace(/\s+/g, " ").trim().slice(0, 80));
    }
    return [...new Set(out)].slice(0, 12);
  });
}

export async function audit(page: Page, file: string, scope: "page" | "dialog", phone: boolean): Promise<I18nFinding | null> {
  if (!LANG) return null;
  const { exact, patterns } = keys();
  const texts = await visibleTexts(page, scope);
  const untranslated = texts.filter((text) => exact.has(text) || patterns.some((re) => re.test(text)));
  const cyrillic = LANG === "en" ? texts.filter((text) => CYRILLIC.test(text)).slice(0, 40) : [];
  const shape = phone ? await layout(page) : { clipped: [], overflow: false };
  const out = await escaped(page);
  if (!untranslated.length && !cyrillic.length && !shape.clipped.length && !out.length && !shape.overflow) return null;
  return { file, untranslated: untranslated.slice(0, 40), cyrillic, clipped: shape.clipped, escaped: out, overflow: shape.overflow };
}
