import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { freshProject, hasVideos, IMAGES_CAM_A, IMAGES_CAM_B, openByPath, settle, startScreen, total, videosA, videosB } from "./helpers";

let ddb = "";
test.beforeEach(async ({ page }) => {
  await startScreen(page);
  ddb = freshProject();
  await openByPath(page, ddb);
});

test.afterEach(async ({ page }) => {
  await settle(page);
});

const species = (page: Page, name: string) => page.locator(".spc button.nm", { hasText: name });
const position = (page: Page) => page.getByTestId("position");

/**
 * ArrowRight to file 2 and wait until its data has loaded. Until then S/E/species do nothing
 * (see the regression test below), so a test must wait before pressing them.
 */
async function nextFileLoaded(page: Page) {
  const loaded = page.waitForResponse((r) => /\/api\/files\/\d+$/.test(r.url()) && r.ok());
  await page.keyboard.press("ArrowRight");
  await expect(position(page)).toHaveText(`2 / ${total()}`);
  await loaded;
}

test("first and last file: the arrows stop at the ends (boundary)", async ({ page }) => {
  const prev = page.locator(".cbar").getByRole("button", { name: "前のファイル" });
  const next = page.locator(".cbar").getByRole("button", { name: "次のファイル" });
  await expect(position(page)).toHaveText(`1 / ${total()}`);
  await expect(prev).toBeDisabled();
  await next.click();
  await expect(position(page)).toHaveText(`2 / ${total()}`);
  await expect(prev).toBeEnabled();

  await page.locator("body").click({ position: { x: 1, y: 1 } });
  for (let i = 2; i < total(); i++) await page.keyboard.press("ArrowRight");
  await expect(position(page)).toHaveText(`${total()} / ${total()}`);
  await expect(next).toBeDisabled();
  await page.keyboard.press("ArrowRight"); // past the end: stays
  await expect(position(page)).toHaveText(`${total()} / ${total()}`);
  await page.keyboard.press("ArrowLeft");
  await expect(position(page)).toHaveText(`${total() - 1} / ${total()}`);
});

const tree = (page: Page) => page.getByRole("tree", { name: "ファイル" });
const treeItem = (page: Page, name: string | RegExp) => tree(page).getByRole("treeitem", { name });
const currentInTree = (page: Page) => tree(page).locator('[aria-current="true"]');

test("file tree: the file on screen is marked, and the mark follows the arrows", async ({ page }) => {
  // The first file is in CamA: only the folders above it start open (CamB stays closed).
  await expect(currentInTree(page)).toHaveCount(1);
  await expect(currentInTree(page)).toHaveAccessibleName(/^IMG_0001\.JPG/);
  await expect(treeItem(page, "CamA")).toHaveAttribute("aria-expanded", "true");
  await expect(treeItem(page, "CamB")).toHaveAttribute("aria-expanded", "false");
  await expect(tree(page).locator(".trow.file")).toHaveCount(IMAGES_CAM_A + videosA());
  await nextFileLoaded(page);
  await expect(currentInTree(page)).toHaveAccessibleName(/^IMG_0002\.JPG/);
  await expect(currentInTree(page)).toHaveCount(1);
});

test("file tree: a click on a file shows it; a folder folds and unfolds", async ({ page }) => {
  await treeItem(page, /^IMG_0005\.JPG/).click();
  await expect(position(page)).toHaveText(`5 / ${total()}`);
  await expect(page.getByTestId("file-name")).toContainText("IMG_0005.JPG");
  await expect(currentInTree(page)).toHaveAccessibleName(/^IMG_0005\.JPG/);

  await treeItem(page, "CamA").click(); // fold: its files leave the tree, the folder keeps a mark
  await expect(tree(page).locator(".trow.file")).toHaveCount(0);
  await expect(treeItem(page, "CamA")).toHaveClass(/has-current/);
  await expect(position(page)).toHaveText(`5 / ${total()}`); // folding does not move
  await treeItem(page, "CamA").click();
  await expect(treeItem(page, /^IMG_0005\.JPG/)).toBeVisible();

  // A file of the other camera: open its folders, pick it; the list position is past CamA's files.
  await treeItem(page, "CamB").click();
  await treeItem(page, "2026-04").last().click();
  await tree(page).getByRole("treeitem", { name: /^IMG_0001\.JPG/ }).last().click();
  await expect(position(page)).toHaveText(`${IMAGES_CAM_A + videosA() + 1} / ${total()}`);
});

test("file tree: entering a species fills the file's mark and the folder's count", async ({ page }) => {
  const filesA = IMAGES_CAM_A + videosA();
  await expect(treeItem(page, "CamA").locator(".n")).toHaveText(`0/${filesA}`);
  await expect(currentInTree(page)).toHaveAccessibleName(/未入力/);
  await expect(species(page, "SpeciesA")).toBeEnabled(); // the file's record has loaded: keys are taken from here on
  const saved = page.waitForResponse((r) => r.url().endsWith("/api/files") && r.request().method() === "PATCH" && r.ok());
  await page.keyboard.press("1");
  await saved;
  await expect(currentInTree(page)).toHaveAccessibleName(/入力済み/);
  await expect(treeItem(page, "CamA").locator(".n")).toHaveText(`1/${filesA}`);
  await expect(treeItem(page, "CamB").locator(".n")).toHaveText(`0/${IMAGES_CAM_B + videosB()}`);
});

test("file tree: 'only this folder' narrows the files; the chip restores them", async ({ page }) => {
  await treeItem(page, "CamB").hover();
  await page.getByRole("button", { name: "CamB だけを表示" }).click();
  await expect(page.getByTestId("match-count")).toHaveText(`${IMAGES_CAM_B + videosB()} 件`);
  await expect(position(page)).toHaveText(`1 / ${IMAGES_CAM_B + videosB()}`);
  await expect(treeItem(page, "CamA")).toHaveCount(0);
  await page.getByRole("button", { name: "フォルダ: CamB ×" }).click();
  await expect(page.getByTestId("match-count")).toHaveText(`${total()} 件`);
  await expect(treeItem(page, "CamA")).toHaveCount(1);
});

test("file tree: arrow keys inside the tree move its cursor, not the file; Enter opens", async ({ page }) => {
  await treeItem(page, /^IMG_0003\.JPG/).click();
  await expect(position(page)).toHaveText(`3 / ${total()}`);
  await tree(page).focus();
  await page.keyboard.press("ArrowLeft"); // cursor to the folder; outside the tree this key is "previous file"
  await expect(tree(page)).toHaveAttribute("aria-activedescendant", "tree-d:CamA\\2026-04");
  await expect(position(page)).toHaveText(`3 / ${total()}`); // (negative) the viewer did not move
  await page.keyboard.press("ArrowDown"); // first file of the folder
  await page.keyboard.press("ArrowDown");
  await expect(position(page)).toHaveText(`3 / ${total()}`);
  await page.keyboard.press("Enter");
  await expect(position(page)).toHaveText(`2 / ${total()}`);
});

test("left pane: sections fold, and the whole pane hides with Ctrl+B", async ({ page }) => {
  const left = page.locator(".pane.left");
  await left.getByRole("button", { name: "絞り込み" }).click();
  await expect(page.getByRole("textbox", { name: "検索（ファイル名・メモ）" })).toHaveCount(0);
  await left.getByRole("button", { name: "絞り込み" }).click();
  await expect(page.getByRole("textbox", { name: "検索（ファイル名・メモ）" })).toBeVisible();
  await left.getByRole("button", { name: "ファイル", exact: true }).click();
  await expect(tree(page)).toHaveCount(0);
  await left.getByRole("button", { name: "ファイル", exact: true }).click();
  await expect(tree(page)).toBeVisible();

  await page.locator("body").click({ position: { x: 1, y: 1 } });
  await page.keyboard.press("Control+b");
  await expect(tree(page)).toHaveCount(0);
  expect((await left.boundingBox())!.width).toBeLessThan(60);
  await page.getByRole("button", { name: /左の欄をひらく/ }).click();
  await expect(tree(page)).toBeVisible();
});

test("table: a wide table scrolls inside itself, the page does not (regression)", async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 700 });
  await page.locator(".cbar").getByRole("button", { name: "入力データ", exact: true }).click();
  const box = page.locator(".spreadsheet-container");
  await expect(box).toBeVisible();
  const sizes = await box.evaluate((el) => ({
    inner: el.scrollWidth, shown: el.clientWidth,
    page: document.documentElement.scrollWidth, view: document.documentElement.clientWidth,
    right: document.querySelector(".pane.right")!.getBoundingClientRect().right,
  }));
  expect(sizes.inner).toBeGreaterThan(sizes.shown); // the demo's fields do not fit: there is something to scroll
  expect(sizes.page).toBeLessThanOrEqual(sizes.view);
  expect(sizes.right).toBeLessThanOrEqual(sizes.view); // the entry pane is still on screen

  // Scrolled sideways for real: the table's content moves, the panes and the bar above stay put.
  const places = () => page.evaluate(() => [".pane.left", ".pane.right", ".cbar"].map((s) => {
    const r = document.querySelector(s)!.getBoundingClientRect();
    return [Math.round(r.left), Math.round(r.right)];
  }));
  const before = await places();
  await box.hover();
  await page.mouse.wheel(300, 0);
  await expect.poll(() => box.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
  expect(await places()).toEqual(before);
  expect(await page.evaluate(() => [window.scrollX, document.documentElement.scrollLeft, document.body.scrollLeft])).toEqual([0, 0, 0]);
});

test("file tree: Shift+Enter on a folder narrows the list to it, and again restores it", async ({ page }) => {
  const filesA = IMAGES_CAM_A + videosA();
  await treeItem(page, /^IMG_0003\.JPG/).click();
  await tree(page).focus();
  await page.keyboard.press("ArrowLeft"); // to the folder above
  await page.keyboard.press("Shift+Enter");
  await expect(page.getByTestId("match-count")).toHaveText(`${filesA} 件`);
  await expect(treeItem(page, "CamB")).toHaveCount(0);
  await tree(page).focus();
  await page.keyboard.press("Shift+Enter");
  await expect(page.getByTestId("match-count")).toHaveText(`${total()} 件`);
  await expect(treeItem(page, "CamB")).toHaveCount(1);
});

test("file tree: what was unfolded and folded is kept over a reload", async ({ page }) => {
  await treeItem(page, "CamB").click();
  await expect(treeItem(page, "CamB")).toHaveAttribute("aria-expanded", "true");
  await page.locator(".pane.left").getByRole("button", { name: "絞り込み" }).click();
  await expect(page.getByRole("textbox", { name: "検索（ファイル名・メモ）" })).toHaveCount(0);
  await page.reload();
  await expect(treeItem(page, "CamB")).toHaveAttribute("aria-expanded", "true");
  await expect(treeItem(page, "CamA")).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("textbox", { name: "検索（ファイル名・メモ）" })).toHaveCount(0);
});

test("file tree: walking far brings the current file's row into the tree's view, unfolding its folder", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 420 }); // a short tree: the last file is far below
  await page.locator("body").click({ position: { x: 1, y: 1 } });
  for (let i = 1; i < total(); i++) await page.keyboard.press("ArrowRight"); // into CamB, which started folded
  await expect(position(page)).toHaveText(`${total()} / ${total()}`);
  await expect(currentInTree(page)).toBeInViewport();
  await expect(treeItem(page, "CamB")).toHaveAttribute("aria-expanded", "true");
});

test("a search that matches nothing shows zero files", async ({ page }) => {
  const search = page.getByRole("textbox", { name: "検索（ファイル名・メモ）" });
  await search.fill("no-such-file-zzz");
  await search.press("Enter");
  await expect(page.getByTestId("match-count")).toHaveText("0 件");
  await expect(position(page)).toHaveText("0 / 0");
});

test("species button: toggles, saves, and is still on after moving away and back", async ({ page }) => {
  const a = species(page, "SpeciesA");
  await expect(a).toHaveAttribute("aria-pressed", "false");
  await a.click();
  await expect(a).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("save-state")).toHaveText("保存済み");

  await page.locator(".cbar").getByRole("button", { name: "次のファイル" }).click();
  await expect(position(page)).toHaveText(`2 / ${total()}`);
  await expect(species(page, "SpeciesA")).toHaveAttribute("aria-pressed", "false"); // other file untouched
  await page.locator(".cbar").getByRole("button", { name: "前のファイル" }).click();
  await expect(species(page, "SpeciesA")).toHaveAttribute("aria-pressed", "true");

  // Written to the data file: still on after the page is reloaded.
  await page.reload();
  await expect(species(page, "SpeciesA")).toHaveAttribute("aria-pressed", "true");

  await species(page, "SpeciesA").click();
  await expect(species(page, "SpeciesA")).toHaveAttribute("aria-pressed", "false");
});

test("moving on: until the new file has loaded, nothing is written to the previous one (regression)", async ({ page }) => {
  await expect(species(page, "SpeciesA")).toBeEnabled(); // file 1 loaded
  let release!: () => void;
  const held = new Promise<void>((r) => { release = r; });
  await page.route(/\/api\/files\/\d+$/, async (route) => {
    if (route.request().method() === "GET" && !route.request().url().endsWith("/files/1")) await held;
    await route.continue();
  });
  const patched: number[][] = [];
  page.on("request", (r) => {
    if (r.method() === "PATCH" && r.url().endsWith("/api/files")) patched.push(JSON.parse(r.postData() ?? "{}").ids);
  });

  try {
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await page.keyboard.press("ArrowRight");
    await expect(position(page)).toHaveText(`2 / ${total()}`);
    // File 2's data is held back. File 1's record must not stay on screen as the one to edit:
    // the palette buttons are disabled and the palette key does nothing (before the fix both
    // wrote to file 1).
    await expect(species(page, "SpeciesA")).toBeDisabled();
    await page.keyboard.press("1");
    await page.waitForTimeout(300);
    expect(patched).toEqual([]);
  } finally {
    release();
  }
  await expect(species(page, "SpeciesA")).toBeEnabled();
  await page.keyboard.press("1");
  await expect(species(page, "SpeciesA")).toHaveAttribute("aria-pressed", "true");
  expect(patched).toEqual([[2]]);
  await page.unroute(/\/api\/files\/\d+$/);

  await page.keyboard.press("ArrowLeft");
  await expect(position(page)).toHaveText(`1 / ${total()}`);
  await expect(species(page, "SpeciesA")).toHaveAttribute("aria-pressed", "false"); // file 1 untouched
});

test("all records: moving between two records of one file writes nothing to the previous one until it has loaded (regression)", async ({ page }) => {
  // A second record of file 1 sits next to it in the all-records (table) list.
  const added = page.waitForResponse((r) => /\/api\/files\/\d+\/duplicate$/.test(r.url()) && r.ok());
  await page.getByRole("button", { name: "この動画に記録を追加" }).click();
  const sibling: number = (await (await added).json()).id;
  await page.getByRole("group", { name: "表示" }).getByRole("button", { name: "入力データ" }).click();
  await expect(page.getByTestId("match-count")).toHaveText(`${total() + 1} 件`);
  // The new record is current (position 2); file 1's own row is position 1.
  await expect(position(page)).toHaveText(`2 / ${total() + 1}`);
  await expect(species(page, "SpeciesA")).toBeEnabled();

  let release!: () => void;
  const held = new Promise<void>((r) => { release = r; });
  await page.route(/\/api\/files\/1$/, async (route) => {
    if (route.request().method() === "GET") await held;
    await route.continue();
  });
  const patched: number[][] = [];
  page.on("request", (r) => {
    if (r.method() === "PATCH" && r.url().endsWith("/api/files")) patched.push(JSON.parse(r.postData() ?? "{}").ids);
  });
  try {
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await page.keyboard.press("ArrowLeft");
    await expect(position(page)).toHaveText(`1 / ${total() + 1}`);
    // Before the fix, the new record (same file) still counted as current and took the write.
    await expect(species(page, "SpeciesA")).toBeDisabled();
    await page.keyboard.press("1");
    await page.waitForTimeout(300);
    expect(patched).toEqual([]);
  } finally {
    release();
  }
  await expect(species(page, "SpeciesA")).toBeEnabled();
  await page.keyboard.press("1");
  await expect(species(page, "SpeciesA")).toHaveAttribute("aria-pressed", "true");
  expect(patched).toEqual([[1]]);
  expect(sibling).not.toBe(1);
  await page.unroute(/\/api\/files\/1$/);
});

test("number key 2 toggles the second species (palette shortcut)", async ({ page }) => {
  await expect(species(page, "SpeciesB")).toBeEnabled(); // the file's data has loaded
  await page.locator("body").click({ position: { x: 1, y: 1 } });
  await page.keyboard.press("2");
  await expect(species(page, "SpeciesB")).toHaveAttribute("aria-pressed", "true");
  await expect(species(page, "SpeciesA")).toHaveAttribute("aria-pressed", "false");
  await page.keyboard.press("Control+z");
  await expect(species(page, "SpeciesB")).toHaveAttribute("aria-pressed", "false");
});

test("view switch: viewer, grid and table", async ({ page }) => {
  const view = page.getByRole("group", { name: "表示" });
  await view.getByRole("button", { name: "一覧" }).click();
  await expect(view.getByRole("button", { name: "一覧" })).toHaveAttribute("aria-pressed", "true");
  await view.getByRole("button", { name: "入力データ" }).click();
  await expect(view.getByRole("button", { name: "入力データ" })).toHaveAttribute("aria-pressed", "true");
  await view.getByRole("button", { name: "1 枚表示" }).click();
  await expect(page.getByRole("toolbar", { name: "表示ツール" })).toBeVisible();
});

test("video: S and E keys make one event with a stay length", async ({ page }) => {
  test.skip(!hasVideos(), "demo videos need ffmpeg");
  await page.getByRole("textbox", { name: "検索（ファイル名・メモ）" }).fill("VID_0001");
  await page.getByRole("textbox", { name: "検索（ファイル名・メモ）" }).press("Enter");
  await expect(page.getByTestId("match-count")).toHaveText("1 件");
  await expect(page.getByTestId("file-name")).toContainText("VID_0001.MP4");
  await species(page, "SpeciesA").click();
  await expect(species(page, "SpeciesA")).toHaveAttribute("aria-pressed", "true");
  await page.locator("body").click({ position: { x: 1, y: 1 } });
  await page.keyboard.press("s");
  await page.keyboard.press("Shift+.");
  await page.keyboard.press("e");
  await expect(page.locator("[data-testid^='event-']")).toHaveCount(1);
});

test("image: S, next file, E closes one event that ends on the second file", async ({ page }) => {
  await species(page, "SpeciesA").click();
  await expect(species(page, "SpeciesA")).toHaveAttribute("aria-pressed", "true");
  await page.locator("body").click({ position: { x: 1, y: 1 } });
  await page.keyboard.press("s");
  const events = page.locator("[data-testid^='event-']");
  await expect(events).toHaveCount(1);
  await expect(events).toContainText("継続中"); // still open
  await nextFileLoaded(page);
  const ended = page.waitForResponse((r) => /\/api\/events\/\d+\/end$/.test(r.url()) && r.ok());
  await page.keyboard.press("e");
  await ended;
  await page.locator(".cbar").getByRole("button", { name: "前のファイル" }).click();
  await expect(position(page)).toHaveText(`1 / ${total()}`);
  await expect(events).toHaveCount(1);
  await expect(events).not.toContainText("継続中"); // closed
});

test("E with no open event only tells the user (negative)", async ({ page }) => {
  await expect(species(page, "SpeciesA")).toBeEnabled();
  await page.locator("body").click({ position: { x: 1, y: 1 } });
  await page.keyboard.press("e");
  await expect(page.locator(".toasts")).toContainText("継続中のイベントがありません");
  await expect(page.locator("[data-testid^='event-']")).toHaveCount(0);
});

/** Exports from the top bar and returns the written file's data rows (header dropped). */
async function exportRows(page: Page, item: string): Promise<string[]> {
  await page.getByRole("button", { name: /^書き出す/ }).click();
  const done = page.locator(".toasts").getByText(/CSV を書き出しました: /);
  const before = await done.count();
  await page.getByRole("menuitem", { name: item }).click();
  await expect(done).toHaveCount(before + 1);
  const path = (await done.last().textContent())!.replace(/^.*CSV を書き出しました: /, "").trim();
  const lines = readFileSync(path, "utf-8").replace(/^﻿/, "").split("\r\n").filter((l) => l !== "");
  return lines.slice(1);
}

test("export CSV: one row per file of the demo (independent count from demo.py)", async ({ page }) => {
  const rows = await exportRows(page, "CSV を書き出す");
  expect(rows).toHaveLength(total());
  expect(rows.filter((r) => r.includes("CamA")).length).toBe(IMAGES_CAM_A + videosA());
  expect(rows.filter((r) => r.includes("CamB")).length).toBe(IMAGES_CAM_B + videosB());
});

test("export stay events: empty project has only a header; one S–E stay gives one row", async ({ page }) => {
  expect(await exportRows(page, "滞在イベントを CSV に書き出す")).toHaveLength(0);
  await species(page, "SpeciesA").click();
  await expect(species(page, "SpeciesA")).toHaveAttribute("aria-pressed", "true");
  await page.locator("body").click({ position: { x: 1, y: 1 } });
  await page.keyboard.press("s");
  await expect(page.locator("[data-testid^='event-']")).toHaveCount(1);
  await nextFileLoaded(page);
  const ended = page.waitForResponse((r) => /\/api\/events\/\d+\/end$/.test(r.url()) && r.ok());
  await page.keyboard.press("e");
  await ended;
  const rows = await exportRows(page, "滞在イベントを CSV に書き出す");
  expect(rows).toHaveLength(1);
  // demo.py: CamA and CamB both start at 2026-04-01 05:30, so file 2 is either camera's first image.
  const [, , , , startFile, , , , , endFile] = rows[0].split(",");
  expect(startFile).toBe("IMG_0001.JPG");
  expect(endFile).toBe((await page.getByTestId("file-name").textContent())!.split(" · ")[0]);
  expect(rows[0].split(",")[13]).toBe("false"); // Open = false
});

test("record tabs: + adds a second record for the same file, tabs switch, export has one more row", async ({ page }) => {
  const tabs = page.getByRole("tablist", { name: "記録" }).getByRole("tab");
  await expect(tabs).toHaveText(["記録 1"]);
  await page.getByRole("button", { name: "この動画に記録を追加" }).click();
  await expect(tabs).toHaveText(["記録 1", "記録 2"]);
  await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
  await species(page, "SpeciesC").click(); // only on record 2
  await expect(species(page, "SpeciesC")).toHaveAttribute("aria-pressed", "true");
  await tabs.nth(0).click();
  await expect(tabs.nth(0)).toHaveAttribute("aria-selected", "true");
  await expect(species(page, "SpeciesC")).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("match-count")).toHaveText(`${total() + 1} 件`);
  expect(await exportRows(page, "CSV を書き出す")).toHaveLength(total() + 1);
});

test("colour and guide panels open from the view tools and close (Esc, second click)", async ({ page }) => {
  const tools = page.getByRole("toolbar", { name: "表示ツール" });
  await tools.getByRole("button", { name: "色味" }).click();
  await expect(page.getByRole("dialog", { name: "色味・明るさ" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "色味・明るさ" })).toHaveCount(0);
  await tools.getByRole("button", { name: "補助線" }).click();
  await expect(page.getByRole("dialog", { name: "補助線（このカメラ）" })).toBeVisible();
  await tools.getByRole("button", { name: "補助線" }).click();
  await expect(page.getByRole("dialog", { name: "補助線（このカメラ）" })).toHaveCount(0);
});

test("work screen: the long hints the redesign removed stay gone (regression)", async ({ page }) => {
  await expect(species(page, "SpeciesA")).toBeEnabled();
  for (const gone of ["数字キーで ON/OFF", "有効範囲での滞在（イベント）", "この画像で侵入", "この画像で退出", "前のファイルの値をコピー"]) {
    await expect(page.getByText(gone)).toHaveCount(0);
  }
});
