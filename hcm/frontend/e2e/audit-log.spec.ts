import { expect, test } from '@playwright/test'
import { expectHeading, login, logout } from './helpers'

/** H3: the audit-log viewer. Every login already writes a LOGIN
 * AuditLogEntry (rbac_audit/views.py::login_view), so there's always
 * something real to find without seeding anything special for this test.
 */
test.describe('audit log (H3)', () => {
  test('hr_admin searches, filters, and can download a CSV', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/audit-log')
    await expectHeading(page, 'Audit Log')
    await page.getByRole('button', { name: 'Search' }).click()
    await expect(page.locator('table tbody tr').first()).toBeVisible()

    await page.getByLabel('Action').selectOption('login')
    await page.getByRole('button', { name: 'Search' }).click()
    await expect(page.locator('table tbody tr').first()).toContainText('Login')

    const csvLink = page.getByRole('link', { name: 'Download CSV' })
    const href = await csvLink.getAttribute('href')
    const csv = await page.request.get(href!)
    expect(csv.status()).toBe(200)
    expect(csv.headers()['content-type']).toContain('text/csv')
    expect(await csv.text()).toContain('timestamp,actor_employee_number')
  })

  test('auditor can reach the log; a plain employee cannot', async ({ page }) => {
    await login(page, 'auditor')
    await page.goto('/audit-log')
    await expectHeading(page, 'Audit Log')
    await expect(page.getByRole('link', { name: 'Audit Log' })).toBeVisible()
    await logout(page)

    await login(page, 'employee')
    await expect(page.getByRole('link', { name: 'Audit Log' })).toHaveCount(0)
    await page.goto('/audit-log')
    await page.waitForURL(/\/employees$/)
  })
})
