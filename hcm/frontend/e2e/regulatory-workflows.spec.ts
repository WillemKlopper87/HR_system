import { expect, test, type Page } from "@playwright/test"
import { expectHeading, login, logout } from "./helpers"

async function browserFetch(page: Page, method: string, path: string, data?: unknown) {
  return page.evaluate(
    async ({ method, path, data }) => {
      const csrf = document.cookie
        .split("; ")
        .find((part) => part.startsWith("csrftoken="))
        ?.split("=")[1]
      const response = await fetch(`/api/v1${path}`, {
        method,
        credentials: "same-origin",
        headers: {
          ...(data ? { "Content-Type": "application/json" } : {}),
          ...(csrf ? { "X-CSRFToken": decodeURIComponent(csrf) } : {}),
        },
        body: data ? JSON.stringify(data) : undefined,
      })
      let body: unknown = null
      try {
        body = await response.json()
      } catch {
        body = null
      }
      return { status: response.status, body }
    },
    { method, path, data },
  )
}

test("training evidence download is authenticated and row-scoped", async ({ page }) => {
  test.setTimeout(90_000)

  await login(page, "employee")
  const me = await page.evaluate(async () => (await fetch("/api/v1/auth/me/")).json())

  await page.goto("/my-learning")
  await expectHeading(page, "My Learning")
  await page.getByRole("button", { name: "+ Request enrollment" }).click()
  await page.getByLabel("Course/training title").fill("Cloud Security Fundamentals")
  const created = page.waitForResponse(
    (response) => response.url().endsWith("/api/v1/training-records/") && response.request().method() === "POST",
  )
  await page.getByRole("button", { name: "Request enrollment" }).click()
  const record = await (await created).json()

  await page
    .locator("tr", { hasText: "Cloud Security Fundamentals" })
    .getByText("Upload")
    .locator("input[type=file]")
    .setInputFiles({ name: "invoice.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7\ninvoice") })
  await expect(page.locator("tr", { hasText: "Cloud Security Fundamentals" }).getByText("Download")).toBeVisible()

  const ownDownload = await browserFetch(page, "GET", `/training-records/${record.id}/download_evidence/`)
  expect(ownDownload.status).toBe(200)

  // HR uploads evidence for a DIFFERENT employee directly (no UI exists yet
  // for HR to browse another employee's learning record) so this session
  // can attempt to reach it -- the row-scope refusal is the point, not how
  // the fixture is built.
  await logout(page)
  await login(page, "hradmin")
  const otherSearch = await page.evaluate(async () =>
    (await fetch("/api/v1/employees/search-summary/?q=E00002")).json(),
  )
  const otherEmployeeId = otherSearch.results[0].id
  const otherRecord = await browserFetch(page, "POST", "/training-records/", {
    employee: otherEmployeeId, title: "Unrelated employee training", status: "completed",
  })
  expect(otherRecord.status).toBe(201)
  await logout(page)

  await login(page, "employee")
  const refused = await browserFetch(
    page, "GET", `/training-records/${(otherRecord.body as { id: number }).id}/download_evidence/`,
  )
  expect(refused.status).toBe(403)
  expect(me.employee_id).not.toBe(otherEmployeeId)
})

test("equity dashboard suppresses small cells for a non-privileged viewer without leaking the value", async ({ page }) => {
  test.setTimeout(90_000)

  await login(page, "hradmin")
  const hrView = await browserFetch(page, "GET", "/dashboards/equity/")
  expect(hrView.status).toBe(200)
  const hrBody = hrView.body as {
    small_cell_suppression_applied: boolean
    workforce_profile: Record<string, Record<string, number>>
  }
  expect(hrBody.small_cell_suppression_applied).toBe(false)
  await logout(page)

  // accounting_officer, not manager: the frontend route restricts
  // /dashboards/equity to hr_admin/ee_manager/accounting_officer/auditor,
  // and accounting_officer is the one of those four with no standing
  // Sensitive-tier grant (RBAC-Roles.md: "no standing access to S/R
  // business data outside that one [EEA2/EEA4 sign-off] action") -- the
  // role that can reach this page and still sees it suppressed.
  await login(page, "accountingofficer")
  await page.goto("/dashboards/equity")
  await expectHeading(page, "Equity Dashboard")
  await expect(page.getByText(/Small cells \(n < 5\) are suppressed for your role/).first()).toBeVisible()

  const managerView = await browserFetch(page, "GET", "/dashboards/equity/")
  expect(managerView.status).toBe(200)
  const managerBody = managerView.body as {
    small_cell_suppression_applied: boolean
    workforce_profile: Record<string, Record<string, number | string>>
  }
  expect(managerBody.small_cell_suppression_applied).toBe(true)

  // Every cell HR sees as a genuine small cell (1-4, the definition
  // rbac_audit/aggregates.py suppresses) must not appear as that same raw
  // number to the manager -- it is either the "<5" marker or, for a
  // complementary sibling in the same row, the string "Suppressed".
  let sawASmallCell = false
  for (const [level, row] of Object.entries(hrBody.workforce_profile)) {
    for (const [column, value] of Object.entries(row)) {
      if (typeof value === "number" && value > 0 && value < 5) {
        sawASmallCell = true
        const managerValue = managerBody.workforce_profile[level]?.[column]
        expect(managerValue).not.toBe(value)
        expect(typeof managerValue === "string").toBe(true)
      }
    }
  }
  expect(sawASmallCell).toBe(true)
})
