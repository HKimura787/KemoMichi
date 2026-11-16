import { expect, test } from "@playwright/test";
import { closeProject, freshProject, openByPath, settle, startScreen, total } from "./helpers";

test.beforeEach(async ({ page }) => {
  await startScreen(page);
});

test.afterEach(async ({ page }) => {
  await settle(page);
});

test("start screen: three ways in, no long explanations", async ({ page }) => {
  await expect(page.getByTestId("recent-empty")).toHaveText("まだ開いたプロジェクトはありません");
  await expect(page.getByRole("heading", { name: "データファイル（.ddb）を開く" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "新しいプロジェクトを作る" })).toBeVisible();
  await expect(page.getByRole("list", { name: "作成の手順" }).getByRole("listitem")).toHaveText(["1画像フォルダ", "2入力項目", "3確認"]);
  await expect(page.getByRole("button", { name: "サンプルデータで試す" })).toBeVisible();
  // Wording the redesign removed (regression): these were on the start screen before.
  for (const gone of ["プロジェクトの開き方", "既存のddbを開く・再開", "作業済みのデータファイル（.ddb）を開きます", "tdbから新規作成"]) {
    await expect(page.getByText(gone)).toHaveCount(0);
  }
  await expect(page.getByText("プロジェクトを開く", { exact: true })).toHaveCount(0);
});

test("open button needs a path (empty input)", async ({ page }) => {
  const open = page.getByRole("button", { name: "開く", exact: true });
  await expect(open).toBeDisabled();
  await page.getByRole("textbox", { name: "データファイル（.ddb）のパス" }).fill("   ");
  await expect(open).toBeDisabled();
});

test("a path that does not exist shows an error and stays on the start screen", async ({ page }) => {
  const missing = freshProject().replace("TimelapseTemplate.ddb", "nothing-here.ddb");
  await page.getByRole("textbox", { name: "データファイル（.ddb）のパス" }).fill(missing);
  await page.getByRole("button", { name: "開く", exact: true }).click();
  await expect(page.locator(".toast.error")).toBeVisible();
  await expect(page.getByRole("heading", { name: "続きから" })).toBeVisible();
  await expect(page.getByTestId("save-state")).toHaveCount(0);
  await expect(page.getByTestId("recent-empty")).toBeVisible(); // a failed open is not remembered
});

test("opening by path shows the demo's file count and the first file", async ({ page }) => {
  await openByPath(page, freshProject());
  await expect(page.getByTestId("position")).toHaveText(`1 / ${total()}`);
  await expect(page.getByTestId("save-state")).toHaveText("保存済み");
  await expect(page.locator(".ro-banner")).toHaveCount(0);
});

test("read-only open: no saving, banner shown, species buttons locked", async ({ page }) => {
  await openByPath(page, freshProject(), { readOnly: true });
  await expect(page.getByTestId("save-state")).toHaveText("読み取り専用");
  await expect(page.locator(".ro-banner")).toContainText("読み取り専用で開いています");
  await expect(page.locator(".spc button.nm", { hasText: "SpeciesA" })).toBeDisabled();
});

test("recent list: remembered after opening, survives reload, can be removed", async ({ page }) => {
  const ddb = freshProject();
  await openByPath(page, ddb);
  await page.getByRole("button", { name: "その他" }).click();
  await page.getByRole("menuitem", { name: "別のプロジェクトを開く" }).click();

  const recent = page.getByTestId("recent").getByRole("listitem");
  await expect(recent).toHaveCount(1);
  await expect(recent.locator(".pth")).toHaveText(ddb);
  await expect(recent.locator(".pr")).toHaveText(`${total()} 件`);

  // Back without choosing: the open project is still there.
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("match-count")).toHaveText(`${total()} 件`);

  // Kept in this browser across a reload.
  await closeProject(page);
  await page.reload();
  await expect(recent).toHaveCount(1);

  // Opening from the list works.
  await recent.locator("button").first().click();
  await expect(page.getByTestId("position")).toHaveText(`1 / ${total()}`);
  await page.getByRole("button", { name: "その他" }).click();
  await page.getByRole("menuitem", { name: "別のプロジェクトを開く" }).click();

  // × removes only the list entry.
  await page.getByRole("button", { name: `${await recent.locator(".nm").textContent()} を一覧から外す` }).click();
  await expect(page.getByTestId("recent-empty")).toBeVisible();
  await closeProject(page);
  await page.reload();
  await expect(page.getByTestId("recent-empty")).toBeVisible();
});

test("opening the same project twice keeps one list entry", async ({ page }) => {
  const ddb = freshProject();
  for (let i = 0; i < 2; i++) {
    await openByPath(page, ddb);
    await page.getByRole("button", { name: "その他" }).click();
    await page.getByRole("menuitem", { name: "別のプロジェクトを開く" }).click();
  }
  await expect(page.getByTestId("recent").getByRole("listitem")).toHaveCount(1);
});

test("broken stored list is ignored instead of breaking the screen", async ({ page }) => {
  await page.evaluate(() => localStorage.setItem("kemomichi.recent", "{not json"));
  await page.reload();
  await expect(page.getByTestId("recent-empty")).toBeVisible();
  await page.evaluate(() => localStorage.setItem("kemomichi.recent", JSON.stringify([
    { path: "", name: "empty", total: 1, at: 1 }, // only the path is wrong
    { path: "x.ddb", name: "x" }, // fields missing
  ])));
  await page.reload();
  await expect(page.getByTestId("recent-empty")).toBeVisible();
});

test("language toggle switches to English and back", async ({ page }) => {
  await page.getByRole("button", { name: "言語" }).click();
  await expect(page.getByRole("heading", { name: "Continue" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try with sample data" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Continue" })).toBeVisible(); // remembered
  await page.getByRole("button", { name: "Language" }).click();
  await expect(page.getByRole("heading", { name: "続きから" })).toBeVisible();
});
