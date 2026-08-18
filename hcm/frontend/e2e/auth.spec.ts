import { expect, test } from '@playwright/test'
import { expectHeading, login, logout } from './helpers'

test.describe('authentication & route guards', () => {
  test('valid login lands on employees, sign out returns to login', async ({ page }) => {
    await login(page, 'hradmin')
    await expectHeading(page, 'Employees')
    await logout(page)
    await expect(page.getByRole('heading', { name: 'Sentech HCM' })).toBeVisible()
  })

  test('wrong password shows the server error, stays on /login', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Username').fill('hradmin')
    await page.getByLabel('Password').fill('nope')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.locator('.form-error')).toHaveText(/invalid credentials/i)
    expect(page.url()).toMatch(/\/login$/)
  })

  test('unauthenticated deep link redirects to login', async ({ page }) => {
    await page.goto('/pay-bands')
    await page.waitForURL(/\/login$/)
  })

  test('role guard: plain employee cannot open comp pages, nav hides them', async ({ page }) => {
    await login(page, 'employee')
    await expect(page.getByRole('link', { name: 'Pay Bands' })).toHaveCount(0)
    await page.goto('/pay-bands')
    await page.waitForURL(/\/employees$/)
    await expectHeading(page, 'Employees')
  })

  test('expired session bounces to login with a notice and returns the user afterwards (H1)', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/org-structure')
    await expectHeading(page, 'Org Structure')
    // The server-side session is gone (expired / revoked): the cookie is dropped
    // so the next API call is unauthenticated -> DRF 403 -> re-probe -> bounce.
    await page.context().clearCookies()
    await page.getByRole('link', { name: 'Employees' }).click()
    await page.waitForURL(/\/login$/)
    await expect(page.locator('.form-notice')).toHaveText(/session expired/i)
    await page.getByLabel('Username').fill('hradmin')
    await page.getByLabel('Password').fill('hradmin123')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await page.waitForURL(/\/employees$/)
  })
})
