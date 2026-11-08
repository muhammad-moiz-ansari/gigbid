import { test, expect, Page } from "@playwright/test";
import path from "node:path";

async function register(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "New here? Create an account" }).click();
  await page.getByLabel("Email", { exact: true }).fill(`phase6-${Date.now()}-${Math.random().toString(16).slice(2)}@example.test`);
  await page.getByLabel("Password", { exact: true }).fill("browser-test-password-123");
  await page.getByRole("button", { name: "Create account →", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your freelance profile" })).toBeVisible();
}

async function review(page: Page) {
  await register(page);
  await page.getByRole("link", { name: "Job inbox", exact: false }).click();
  await page.getByRole("button", { name: /Load synthetic examples/ }).click();
  const card = page.locator(".job-card").filter({ hasText: "Build a secure task API" }).first();
  await card.getByRole("button", { name: /Analyse fit/ }).click();
  await expect(page.getByRole("button", { name: "Approve exact action →" })).toBeEnabled();
  const all = await (await page.request.get("/api/runs")).json();
  return all.find((run: { subject: string }) => run.subject === page.url().split("/").pop());
}

test("onboarding saves rates, filters and upload metadata across refresh", async ({ page }) => {
  await register(page);
  await page.getByLabel("Display name").fill("Taylor Dev");
  await page.getByRole("combobox", { name: "Persona", exact: true }).selectOption("data-analyst");
  await page.getByLabel("Hourly rate (USD)").fill("65");
  await page.getByLabel("Weekly Connects budget").fill("24");
  await page.getByLabel("Minimum job budget (USD)").fill("300");
  await page.getByLabel("Maximum Connects per job").fill("9");
  await page.getByLabel("Required skills (comma separated)", { exact: true }).fill("Python");
  await expect(page.getByRole("combobox", { name: "Marketplace", exact: true }).locator('option[value="upwork"]')).toHaveJSProperty("disabled", true);
  await page.getByRole("button", { name: "Save profile", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Profile and inbox filters saved." })).toBeVisible();
  await page.getByRole("combobox", { name: "Upload format", exact: true }).selectOption("file");
  await page.getByLabel("Source name").fill("reporting.md");
  await page.getByLabel("Project", { exact: true }).fill("Reporting checks");
  await page.getByLabel("Evidence skills (comma separated)", { exact: true }).fill("Python, SQL");
  await page.getByLabel("Industry", { exact: true }).fill("Retail");
  await page.getByLabel("Evidence date").fill("2026-10-01");
  await page.getByLabel("Portfolio file").setInputFiles({ name: "reporting.md", mimeType: "text/markdown",
    buffer: Buffer.from("# Reporting checks\nBuilt Python reporting checks with SQL reconciliation.") });
  await page.getByRole("button", { name: "Save portfolio evidence" }).click();
  await expect(page.getByText("reporting.md", { exact: true })).toBeVisible();
  const evidence = await (await page.request.get("/api/evidence")).json();
  expect(evidence[0]).toMatchObject({ project: "Reporting checks", persona: "data-analyst", industry: "Retail", date: "2026-10-01" });
  await page.reload();
  await expect(page.getByLabel("Hourly rate (USD)")).toHaveValue("65");
  await expect(page.getByLabel("Maximum Connects per job")).toHaveValue("9");
  await expect(page.getByText("reporting.md", { exact: true })).toBeVisible();
});

test("inbox to approval preserves review on refresh and spends once", async ({ page }) => {
  const run = await review(page);
  expect((await (await page.request.get("/api/analytics")).json()).connects.spent).toBe(0);
  const citation = page.locator(".proposal-preview .citation a").first();
  await citation.focus();
  await expect(page.locator(".proposal-preview [role=tooltip]").first()).toBeVisible();
  await page.screenshot({ path: path.resolve(__dirname, "../../../.cache/phase6-studio-desktop.png"), fullPage: true });
  await page.reload();
  await expect(page.getByRole("button", { name: "Approve exact action →" })).toBeEnabled();
  const restored = await (await page.request.get(`/api/runs/${run.id}`)).json();
  expect(restored.state.approval_id).toBe(run.state.approval_id);
  await page.getByRole("button", { name: "Reconnect and reload history" }).click();
  await expect(page.getByLabel("Run activity").getByText("Live", { exact: true })).toBeVisible();
  const ids = await page.locator("[data-event-id]").evaluateAll(elements => elements.map(item => item.getAttribute("data-event-id")));
  expect(ids.length).toBeGreaterThan(5);
  expect(new Set(ids).size).toBe(ids.length);
  await page.getByRole("button", { name: "Approve exact action →" }).click();
  await expect(page.getByText("Approved action completed.", { exact: false })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Approved action completed.", { exact: false })).toBeVisible();
  expect((await (await page.request.get("/api/analytics")).json()).connects.spent).toBe(8);
});

test("edits require new verification and a rejection reason", async ({ page }) => {
  const run = await review(page);
  await page.getByRole("button", { name: "Edit cover letter", exact: true }).click();
  await page.getByLabel("Your cover letter").fill("Proposed approach: I would test authorization.");
  await expect(page.getByRole("button", { name: "Approve exact action →" })).toBeDisabled();
  await page.getByRole("button", { name: "Save edit & recheck", exact: true }).click();
  await expect(page.getByText("v2", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve exact action →" })).toBeEnabled();
  expect((await (await page.request.get(`/api/runs/${run.id}`)).json()).state.approval_id).not.toBe(run.state.approval_id);
  await expect(page.getByRole("button", { name: "Reject proposal" })).toBeDisabled();
  await page.getByLabel("Rejection reason").fill("Scope needs more clarification.");
  await page.getByRole("button", { name: "Reject proposal" }).click();
  await expect(page.locator(".detail-heading .badge")).toHaveText("rejected");
  expect((await (await page.request.get("/api/analytics")).json()).connects.spent).toBe(0);
});

test("paragraph regeneration preserves evidence and repeats all validation", async ({ page }) => {
  const run = await review(page);
  await page.getByRole("combobox", { name: "Paragraph to regenerate", exact: true }).selectOption("1");
  await page.getByRole("button", { name: "Regenerate selected paragraph" }).click();
  await expect(page.getByText("v2", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve exact action →" })).toBeEnabled();
  const result = await (await page.request.get(`/api/runs/${run.id}`)).json();
  expect(result.draft_paragraphs[0]).toBe(run.draft_paragraphs[0]);
  expect(result.draft_paragraphs[1]).toBe("Proposed approach: I would test authorization.");
  expect(result.state.approval_id).not.toBe(run.state.approval_id);
  const history = await (await page.request.get(`/api/runs/${run.id}/history?limit=500`)).json();
  for (const node of ["verifier", "critic", "compliance"]) {
    expect(history.events.filter((event: {name: string}) => event.name === `node:${node}`)).toHaveLength(2);
  }
  expect((await (await page.request.get("/api/analytics")).json()).connects.spent).toBe(0);
});

test("mobile navigation, empty filters and outage recovery remain usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await register(page);
  await page.getByRole("link", { name: "Job inbox", exact: false }).click();
  await page.getByRole("button", { name: /Load synthetic examples/ }).click();
  await page.getByRole("textbox", { name: "Filter opportunities" }).fill("unmatched-search-phrase");
  await expect(page.getByText("No opportunities match your filters.")).toBeVisible();
  await page.getByRole("textbox", { name: "Filter opportunities" }).fill("");
  await page.getByRole("link", { name: "Settings", exact: false }).click();
  await page.getByRole("combobox", { name: "Simulate marketplace condition", exact: true }).selectOption("outage");
  await expect(page.getByRole("alert").filter({ hasText: "Marketplace unavailable." })).toBeVisible();
  await page.getByRole("combobox", { name: "Simulate marketplace condition", exact: true }).selectOption("none");
  await expect(page.getByRole("alert").filter({ hasText: "Marketplace unavailable." })).toHaveCount(0);
  await page.getByRole("link", { name: "Job inbox", exact: false }).click();
  await expect(page.locator(".job-card").first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: path.resolve(__dirname, "../../../.cache/phase6-inbox-mobile.png"), fullPage: true });
  await page.keyboard.press("Control+Home");
  await page.keyboard.press("Tab");
  await page.getByRole("link", { name: "Skip to main content" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
});

test("invalidated reviews and account switching clear stale workspace data", async ({ page }) => {
  const run = await review(page);
  const source = run.state.fit.evidence[0].source;
  await page.getByRole("link", { name: "Settings", exact: false }).click();
  await page.getByRole("button", { name: "Delete source " + source, exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Source deleted." })).toBeVisible();
  await page.goto(`/studio/${run.id}`);
  await expect(page.getByText("This review is no longer active.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve exact action →" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Recheck and renew approval" })).toBeEnabled();
  await page.getByRole("button", { name: "Sign out ↗" }).click();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await page.getByRole("button", { name: "New here? Create an account" }).click();
  await page.getByLabel("Email", { exact: true }).fill(`next-user-${Date.now()}@example.test`);
  await page.getByLabel("Password", { exact: true }).fill("browser-test-password-123");
  await page.getByRole("button", { name: "Create account →", exact: true }).click();
  await expect(page.getByText("0 portfolio passages available.")).toBeVisible();
  await expect(page.getByText("No evidence uploaded yet. Start with a case study or CV above.")).toBeVisible();
  await page.getByRole("link", { name: "Job inbox", exact: false }).click();
  await expect(page.getByText("Your opportunity feed is empty.")).toBeVisible();
});

test("client reply becomes an approved reply with offered interview slots", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Job inbox", exact: false }).click();
  await page.getByRole("button", { name: /Load synthetic examples/ }).click();
  await page.getByRole("link", { name: "Messages", exact: false }).click();
  await page.getByLabel("Client message").fill("Could we schedule an interview this week?");
  await page.getByRole("button", { name: "Add synthetic reply" }).click();
  await page.getByRole("link", { name: "Review reply ↗" }).click();
  await expect(page.getByRole("heading", { name: "Offered interview slots" })).toBeVisible();
  await page.getByRole("button", { name: "Approve exact action →" }).click();
  await expect(page.getByText("Approved action completed.", { exact: false })).toBeVisible();
  const messages = await (await page.request.get("/api/messages")).json();
  expect(messages.map((m: { direction: string }) => m.direction)).toEqual(["inbound", "outbound"]);
});

test("memory viewer shows a learned rule and forgetting it removes it", async ({ page }) => {
  await register(page);
  expect((await page.request.get("/api/test/memory/seed")).ok()).toBe(true);
  await expect(page.getByText('Avoid this repeatedly removed word: "passionate"')).toBeVisible();
  await page.getByRole("button", { name: "Forget this" }).click();
  await expect(page.getByText("Nothing promoted yet.", { exact: false })).toBeVisible();
  expect(await (await page.request.get("/api/memory")).json()).toEqual([]);
});

test("inbox skip hides a job and keeps it under the Skipped filter", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Job inbox", exact: false }).click();
  await page.getByRole("button", { name: /Load synthetic examples/ }).click();
  const card = page.locator(".job-card").filter({ hasText: "Native iOS development" });
  await card.getByText("Skip…").click();
  await card.getByLabel("Reason for skipping Native iOS development").fill("Not my stack");
  await card.getByRole("button", { name: "Skip job" }).click();
  await expect(page.locator(".job-card").filter({ hasText: "Native iOS development" })).toHaveCount(0);
  await page.getByRole("combobox", { name: "Decision filter" }).selectOption("skipped");
  await expect(page.getByText("Skipped: Not my stack")).toBeVisible();
});
