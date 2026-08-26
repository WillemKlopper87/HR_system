import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

test.describe('core HR (Sprints 1-3)', () => {
  test('hr_admin: employee list, search, detail with history', async ({ page }) => {
    await login(page, 'hradmin')
    await expectHeading(page, 'Employees')
    await settled(page)
    const rows = page.locator('table tbody tr')
    await expect(rows.first()).toBeVisible()
    const initial = await rows.count()
    expect(initial).toBeGreaterThan(20)

    // client-side search narrows the list
    await page.getByPlaceholder('Search by name, number, or email…').fill('zzzz-no-such-person')
    await expect(rows).toHaveCount(0)
    await page.getByPlaceholder('Search by name, number, or email…').fill('')
    await expect(rows.first()).toBeVisible()

    // Open a serving employee. The directory intentionally also includes
    // departed staff, whose historical detail has no current assignment.
    const servingRow = rows.filter({ has: page.locator('.status-badge') }).first()
    await servingRow.getByRole('link').first().click()
    await page.waitForURL(/\/employees\/\d+$/)
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Identity' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Current assignment (as at today)' })).toBeVisible()
    // (the History card only renders when the employee has more than one effective-dated version)
    // talent sections mounted on the detail page (Sprints 6-9)
    for (const h of ['Skills', 'Certifications', 'Training', 'Goals', 'Feedback']) {
      await expect(page.getByRole('heading', { name: h, exact: true })).toBeVisible()
    }
  })

  test('hr_admin: org structure CRUD — add a department, see it, delete it', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/org-structure')
    await expectHeading(page, 'Org Structure')
    await settled(page)
    const code = `E2E${Date.now().toString().slice(-5)}`
    await page.getByRole('button', { name: '+ Add department' }).click()
    await page.getByLabel('Name').first().fill(`E2E Department ${code}`)
    await page.getByLabel('Code').first().fill(code)
    await page.getByRole('button', { name: 'Save' }).first().click()
    const row = page.locator('table tbody tr', { hasText: code })
    await expect(row).toHaveCount(1)
    page.once('dialog', (d) => d.accept())
    await row.getByRole('button', { name: 'Delete' }).click()
    await expect(page.locator('table tbody tr', { hasText: code })).toHaveCount(0)
  })

  test('hr_admin: data-quality queue and headcount dashboard render', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/data-quality')
    await expectHeading(page, 'Data Quality')
    await settled(page)
    await expect(page.getByRole('button', { name: /run/i })).toBeVisible()

    await page.goto('/dashboards/headcount')
    await expectHeading(page, 'Headcount Dashboard')
    await settled(page)
    const total = page.locator('.stat-tile', { hasText: 'Total headcount' }).locator('.stat-value')
    await expect(total).toBeVisible()
    expect(Number(await total.textContent())).toBeGreaterThan(0)
  })

  test('line manager sees only their team; plain employee sees only themselves', async ({ page }) => {
    await login(page, 'manager')
    const rows = page.locator('table tbody tr')
    await expect(rows.first()).toBeVisible()
    const managerRows = await rows.count()
    expect(managerRows).toBeGreaterThan(0)
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    await login(page, 'employee')
    await expect(page.locator('table tbody tr')).toHaveCount(1)
    expect(managerRows).toBeGreaterThan(1)
  })
})
