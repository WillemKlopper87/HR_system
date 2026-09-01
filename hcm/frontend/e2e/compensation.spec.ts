import { expect, test } from '@playwright/test'
import { expectHeading, login, settled, totp } from './helpers'

test.describe('compensation (Sprint 10-11) + step-up MFA (ADR-009)', () => {
  test('comp_manager: pay bands are gated by a real TOTP enrol → confirm → challenge flow, then reused', async ({ page }) => {
    await login(page, 'compmanager')
    await page.goto('/pay-bands')
    // The whole page (heading included) sits behind the gate: no data, no h1, only the challenge
    await expect(page.getByRole('heading', { name: 'Step-up authentication required' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(0)
    await expect(page.locator('table')).toHaveCount(0)

    // enrol
    await page.getByLabel('Current password').fill('compmanager123')
    await page.getByRole('button', { name: 'Set up authenticator' }).click()
    const secret = await page.getByLabel('Manual entry key').inputValue()
    expect(secret.length).toBeGreaterThan(10)

    // a wrong confirmation code is rejected
    await page.getByLabel('6-digit code').fill('000000')
    await page.getByRole('button', { name: 'Confirm and activate' }).click()
    await expect(page.locator('.form-error')).toBeVisible()

    // the correct one activates the device (computed exactly like an authenticator app would)
    await page.getByLabel('6-digit code').fill(totp(secret))
    await page.getByRole('button', { name: 'Confirm and activate' }).click()
    await expect(page.getByLabel('6-digit authenticator code')).toBeVisible()

    // challenge: code + mandatory business reason
    await page.getByLabel('6-digit authenticator code').fill(totp(secret))
    await page.getByLabel('Reason for access').selectOption('payroll_processing')
    await page.getByRole('button', { name: 'Verify and continue' }).click()
    await expectHeading(page, 'Pay Bands')
    await settled(page)
    await expect(page.locator('table thead')).toContainText('Job grade')
    await expect(page.locator('table tbody tr').first()).toBeVisible()

    // grant is reused on the other payroll page — no second challenge
    await page.goto('/comp-proposals')
    await expectHeading(page, 'Compensation Proposals')
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Step-up authentication required' })).toHaveCount(0)
    await expect(page.locator('table thead')).toContainText('Amount')

    // benefits are not payroll-restricted
    await page.goto('/benefits')
    await expectHeading(page, 'Benefits')
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Benefits catalog' })).toBeVisible()
  })

  test('hr_admin is challenged independently (no cross-user grant leakage)', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/pay-bands')
    await expect(page.getByRole('heading', { name: 'Step-up authentication required' })).toBeVisible()
  })

  test('line manager: comp module hidden and blocked', async ({ page }) => {
    await login(page, 'manager')
    await expect(page.getByRole('link', { name: 'Comp Proposals' })).toHaveCount(0)
    await page.goto('/comp-proposals')
    await page.waitForURL(/\/employees$/)
  })
})
