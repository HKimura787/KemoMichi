import { cpSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, type Page } from "@playwright/test";

// Layer 0 (docs/test-data.md): kemocore.demo writes this, so the expected values below are
// taken from demo.py, not from what the app shows.
const TMP = resolve(dirname(fileURLToPath(import.meta.url)), ".tmp");
const PRISTINE = join(TMP, "pristine");

export const IMAGES_CAM_A = 13; // IMG_0001–0012 + NOEXIF_0001
export const IMAGES_CAM_B = 12; // IMG_0001–0012
/**
 * demo.py makes one video per camera only when ffmpeg can encode it (CI installs ffmpeg).
 * Read when a test runs: the server writes the demo after the test files are collected.
 */
export const videosA = () => (existsSync(join(PRISTINE, "CamA", "2026-04", "VID_0001.MP4")) ? 1 : 0);
export const videosB = () => (existsSync(join(PRISTINE, "CamB", "2026-04", "VID_0002.AVI")) ? 1 : 0);
export const hasVideos = () => videosA() === 1;
export const total = () => IMAGES_CAM_A + IMAGES_CAM_B + videosA() + videosB();

let runs = 0;
/** A private copy of the demo project, so no test sees another test's edits. */
export function freshProject(): string {
  const dir = join(TMP, "runs", `${Date.now()}-${process.pid}-${runs++}`);
  cpSync(PRISTINE, dir, { recursive: true });
  return join(dir, "TimelapseTemplate.ddb");
}

/** Opens a project from the start screen by typing its path. */
export async function openByPath(page: Page, ddb: string, { readOnly = false } = {}) {
  await page.getByRole("textbox", { name: "データファイル（.ddb）のパス" }).fill(ddb);
  if (readOnly) await page.getByRole("checkbox", { name: "読み取り専用" }).check();
  await page.getByRole("button", { name: "開く", exact: true }).click();
  await expect(page.getByTestId("match-count")).toHaveText(`${total()} 件`);
}

/** Start screen with nothing remembered (fresh browser storage, Japanese UI). */
export async function startScreen(page: Page) {
  // The server keeps the last project open; close it so the start screen shows.
  expect((await page.request.post("/api/project/close")).ok()).toBe(true);
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("e2e.init")) {
      localStorage.clear();
      localStorage.setItem("kemomichi.lang", "ja");
      sessionStorage.setItem("e2e.init", "1");
    }
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "続きから" })).toBeVisible();
}

/**
 * Let the page's media requests finish before the next test closes the project.
 * Closing while thumbnails are still being read crashes the server today (exit 139,
 * shared SQLite connection closed mid-read): a server issue tracked separately.
 */
export async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
}

/** Settle, then close the project on the server (so a reload shows the start screen). */
export async function closeProject(page: Page) {
  await settle(page);
  expect((await page.request.post("/api/project/close")).ok()).toBe(true);
}
