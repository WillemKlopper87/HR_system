import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

test.describe('EE reporting (Sprint 13-14)', () => {
  test('ee_manager: configuration sections, reports list, equity dashboard', async ({ page }) => {
    await login(page, 'eemanager')
    await page.goto('/ee-configuration')
    await expectHeading(page, 'EE Reporting Configuration')
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Employer Configuration (Section A)' })).toBeVisible()
    await expect(page.getByRole('heading', { name: /EE Questionnaire/ })).toBeVisible()
    // Raw remuneration is Restricted payroll data — not shown to ee_manager at all
    // (RBAC-Roles.md: "no pay access"); hr_admin sees it behind the step-up gate.
    await expect(page.getByRole('heading', { name: 'Remuneration Records' })).toHaveCount(0)

    await page.goto('/ee-reports')
    await expectHeading(page, 'EEA2 / EEA4 Reports')
    await settled(page)
    await expect(page.locator('table thead')).toContainText('Form')

    await page.goto('/dashboards/equity')
    await expectHeading(page, 'Equity Dashboard')
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Workforce profile' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Target vs. actual (percentage-point gap)' })).toBeVisible()
  })

  test('hr_admin sees the Remuneration Records section behind the step-up gate', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/ee-configuration')
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Remuneration Records' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Step-up authentication required' })).toBeVisible()
  })

  test('accounting officer reaches reports (sign-off role); line manager does not', async ({ page }) => {
    await login(page, 'accountingofficer')
    await page.goto('/ee-reports')
    await expectHeading(page, 'EEA2 / EEA4 Reports')
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'manager')
    await page.goto('/ee-reports')
    await page.waitForURL(/\/employees$/)
  })
})

test.describe('workforce integrity (Sprint 12c)', () => {
  test('biometric capture is gated by explicit informed consent', async ({ page }) => {
    await login(page, 'employee')
    let consentPostBody: unknown = null
    await page.route('**/api/v1/liveness-checks/consent/**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ active: false }) })
        return
      }
      consentPostBody = route.request().postDataJSON()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ detail: 'Consent recorded.' }) })
    })

    await page.goto('/my-verification')
    await expectHeading(page, 'My Identity Verification')
    await settled(page)

    await expect(page.getByRole('button', { name: /Verify now|Enroll now/ })).toHaveCount(0)
    const recordConsent = page.getByRole('button', { name: 'Record consent' })
    await expect(recordConsent).toBeDisabled()
    await page.getByLabel(/I have read this notice and consent/).check()
    await recordConsent.click()
    await expect.poll(() => consentPostBody).toEqual({
      employee: expect.any(Number), lawful_basis: 'consent', text_version: 'biometric-v1',
    })
    await expect(page.getByRole('button', { name: 'Start camera' })).toBeVisible()
  })

  test('hr_admin review queue + attendance; employee self-service check-in page', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/workforce-integrity')
    await expectHeading(page, 'Workforce Integrity')
    await settled(page)
    await expect(page.getByRole('heading', { name: /Flagged for review/ })).toBeVisible()
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    await login(page, 'employee')
    await page.goto('/my-verification')
    await expectHeading(page, 'My Identity Verification')
    await settled(page)
    await expect(page.getByRole('heading', { name: "This week's office attendance" })).toBeVisible()
    // the HR queue is not reachable for a plain employee
    await page.goto('/workforce-integrity')
    await page.waitForURL(/\/employees$/)
  })
})
