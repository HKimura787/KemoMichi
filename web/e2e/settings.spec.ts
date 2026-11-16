import { cpSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { settle, startScreen } from "./helpers";

// A project whose template has only the standard fields: no species, nothing for stays.
// Settings must be enough to get from there to a working palette and stay columns.
const TMP = resolve(dirname(fileURLToPath(import.meta.url)), ".tmp");
const PRISTINE = join(TMP, "pristine");
const FILES = ["IMG_0001.JPG", "IMG_0002.JPG", "IMG_0003.JPG"];
let runs = 0;

async function bareProject(page: Page): Promise<string> {
  const dir = join(TMP, "runs", `bare-${Date.now()}-${process.pid}-${runs++}`);
  mkdirSync(join(dir, "CamA"), { recursive: true });
  for (const f of FILES) cpSync(join(PRISTINE, "CamA", "2026-04", f), join(dir, "CamA", f));
  const template = join(PRISTINE, "TimelapseTemplate.tdb");
  const preview = await (await page.request.get("/api/template", { params: { path: template, folder: dir } })).json();
  const draft = { name: "Bare", revision: preview.revision,
    controls: preview.controls.filter((c: { standard: boolean }) => c.standard)
      .map(({ standard: _s, ...c }: { standard: boolean }) => c) };
  const job = await (await page.request.post("/api/project/create", { data: { folder: dir, template, draft } })).json();
  await expect.poll(async () => (await (await page.request.get(`/api/jobs/${job.id}`)).json()).status).toBe("done");
  return join(dir, "Bare.ddb");
}

const dialog = (page: Page) => page.getByRole("dialog", { name: "設定" });
async function openSettings(page: Page) {
  await page.getByRole("button", { name: "その他" }).click();
  await page.getByRole("menuitem", { name: "設定" }).click();
  await expect(dialog(page)).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await startScreen(page);
  await bareProject(page);
  await page.goto("/");
  await expect(page.getByTestId("match-count")).toHaveText(`${FILES.length} 件`);
});

test.afterEach(async ({ page }) => {
  await settle(page);
});

test("a project with no species: add them in settings, then use them with the number keys", async ({ page }) => {
  await expect(page.getByText("種がまだありません。設定で追加できます。")).toBeVisible();
  await openSettings(page);
  const d = dialog(page);
  await expect(d.getByText("種がまだありません。下で名前を入れて追加します。")).toBeVisible();
  const add = d.getByRole("button", { name: "種を追加" });
  await expect(add).toBeDisabled(); // nothing typed (empty)
  const name = d.getByRole("textbox", { name: "新しい種の名前" });
  await name.fill("   ");
  await expect(add).toBeDisabled(); // blanks only

  await name.fill("タヌキ");
  await name.press("Enter");
  await expect(d.getByRole("row", { name: /タヌキ/ })).toContainText("(Species1)");
  await expect(name).toHaveValue("");
  await name.fill("Deer");
  await d.getByRole("checkbox", { name: "個数の項目も作る" }).uncheck();
  await add.click();
  const deer = d.getByRole("row", { name: /Deer/ });
  await expect(deer).toContainText("(Deer)");
  await expect(deer.getByRole("combobox", { name: "個数の項目" })).toHaveValue("");
  await expect(d.getByRole("row", { name: /タヌキ/ }).getByRole("combobox", { name: "個数の項目" })).toHaveValue("Species1Count");
  await expect(deer.getByRole("combobox", { name: "キー" })).toHaveValue("2");

  // The same name again is refused and the table keeps two species.
  await name.fill("タヌキ");
  await add.click();
  await expect(page.getByText("同じ名前の項目がすでにあります: タヌキ")).toBeVisible();
  await expect(d.locator("tbody tr")).toHaveCount(2);

  await d.getByRole("button", { name: "保存" }).click();
  await expect(d).toBeHidden();
  const palette = page.locator(".pal");
  await expect(palette.getByRole("button", { name: /タヌキ/ }).first()).toBeVisible();
  await expect(palette.getByRole("button", { name: /Deer/ }).first()).toBeVisible();
  const saved = page.waitForResponse((r) => r.url().endsWith("/api/files") && r.request().method() === "PATCH" && r.ok());
  await page.locator("body").click({ position: { x: 1, y: 1 } });
  await page.keyboard.press("1");
  await saved;
  const rows = await (await page.request.get("/api/files?limit=1")).json();
  expect(rows.rows[0].values.Species1).toBe("true");
  expect(rows.rows[0].values.Deer).toBe("false");
});

test("a project with no stay fields: one button creates and selects all eight", async ({ page }) => {
  await openSettings(page);
  const d = dialog(page);
  const create = d.getByRole("button", { name: "未設定の書き込み先を作成 (8)" });
  for (const id of ["speciesName", "individual", "startInside", "entry", "duration", "exitFile", "exit", "endInside"])
    await expect(d.locator(`#ev-${id}`)).toHaveValue("");
  await create.click();
  const expected: Record<string, string> = { speciesName: "SpeciesName", individual: "Individual", startInside: "InsideAtStart",
    entry: "EntrySec", duration: "StayDuration", exitFile: "ExitFile", exit: "ExitSec", endInside: "InsideAtEnd" };
  for (const [id, column] of Object.entries(expected)) await expect(d.locator(`#ev-${id}`)).toHaveValue(column);
  await expect(d.getByRole("button", { name: /未設定の書き込み先を作成/ })).toHaveCount(0); // nothing left to create
  // The two new Flags are stay columns, not species.
  await expect(d.getByText("種がまだありません。下で名前を入れて追加します。")).toBeVisible();
  await expect(d.locator("#ev-entry option:checked")).toHaveText("侵入（秒） (EntrySec)");

  await d.getByRole("button", { name: "保存" }).click();
  await expect(d).toBeHidden();
  const project = await (await page.request.get("/api/project")).json();
  expect(Object.fromEntries(Object.keys(expected).map((k) => [k, project.eventColumns[k]]))).toEqual(expected);
  await expect(page.getByText("書き込む項目が未設定です（設定 → 滞在イベント）")).toHaveCount(0);
  // Opened again: the choices are still there, and the two new Flags are still not offered as species.
  await openSettings(page);
  await expect(d.locator("#ev-startInside")).toHaveValue("InsideAtStart");
  await expect(d.getByText("種がまだありません。下で名前を入れて追加します。")).toBeVisible();
  await expect(d.locator("tbody tr")).toHaveCount(1);
});

test("what is created follows the screen, not what was saved last", async ({ page }) => {
  await openSettings(page);
  const d = dialog(page);
  await d.getByRole("button", { name: "未設定の書き込み先を作成 (8)" }).click();
  await expect(d.locator("#ev-entry")).toHaveValue("EntrySec");
  // Cleared on screen only: this one, and nothing else, is created again.
  await d.locator("#ev-entry").selectOption("");
  await d.getByRole("button", { name: "未設定の書き込み先を作成 (1)" }).click();
  await expect(d.locator("#ev-entry")).toHaveValue("EntrySec2");
  await expect(d.locator("#ev-exit")).toHaveValue("ExitSec");
  const project = await (await page.request.get("/api/project")).json();
  const labels = project.controls.map((c: { dataLabel: string }) => c.dataLabel);
  expect(labels.filter((l: string) => /^(EntrySec|ExitSec|StayDuration)/.test(l)).sort())
    .toEqual(["EntrySec", "EntrySec2", "ExitSec", "StayDuration"]);

  // A key changed on screen is taken into account when the next species gets its key.
  const name = d.getByRole("textbox", { name: "新しい種の名前" });
  await name.fill("タヌキ");
  await name.press("Enter");
  const first = d.getByRole("row", { name: /タヌキ/ }).getByRole("combobox", { name: "キー" });
  await expect(first).toHaveValue("1");
  await first.selectOption("2");
  await name.fill("Deer");
  await name.press("Enter");
  await expect(d.getByRole("row", { name: /Deer/ }).getByRole("combobox", { name: "キー" })).toHaveValue("1");
  await name.fill("Boar");
  await name.press("Enter");
  await expect(d.getByRole("row", { name: /Boar/ }).getByRole("combobox", { name: "キー" })).toHaveValue("3");
});
