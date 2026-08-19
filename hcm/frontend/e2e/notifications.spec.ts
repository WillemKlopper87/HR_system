import { expect, test } from '@playwright/test'
import { expectHeading, login, logout, settled } from './helpers'

/** H3: the notification bell in the header, and the policy-publish
 * consumer end to end. Seed data already publishes three policies (see
 * `_seed_policies_demo_data`), so the demo `employee` login already has
 * unread notifications waiting from seeding alone -- this test reads one
 * of those first, then drives a *live* publish (the deliberately-left-in-
 * DRAFT "Remote Work Policy") to prove the whole notify() path works, not
 * just what seeding happened to produce.
 */
test.describe('notifications (H3)', () => {
  test('the bell shows unread notifications from seeding and marks them read on open', async ({ page }) => {
    await login(page, 'employee')
    await expectHeading(page, 'Employees')
    const bell = page.getByRole('button', { name: /Notifications/ })
    await expect(bell).toBeVisible()
    await expect(bell.locator('.notification-badge')).toBeVisible()
    const before = Number(await bell.locator('.notification-badge').textContent())
    expect(before).toBeGreaterThan(0)

    await bell.click()
    await expect(page.locator('.notification-dropdown')).toBeVisible()
    const firstItem = page.locator('.notification-item').first()
    await expect(firstItem).toBeVisible()
    await firstItem.click()

    // clicking an unread item marks it read and navigates to its link
    await expect(page.locator('.notification-dropdown')).toHaveCount(0)
    await bell.click()
    await expect(page.locator('.notification-dropdown')).toBeVisible()
    const after = Number((await bell.locator('.notification-badge').textContent()) ?? '0')
    expect(after).toBeLessThan(before)
  })

  test('hr_admin publishes a draft policy and every current employee is notified', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/policies')
    await expectHeading(page, 'Policy Library')
    await settled(page)
    const draftRow = page.locator('table tbody tr', { hasText: 'Remote Work Policy' })
    await expect(draftRow).toContainText('Draft')
    await draftRow.getByRole('button', { name: 'Publish' }).click()
    await expect(draftRow).toContainText('Published')
    await logout(page)

    await login(page, 'employee')
    const bell = page.getByRole('button', { name: /Notifications/ })
    await bell.click()
    await expect(page.locator('.notification-dropdown')).toBeVisible()
    await expect(page.getByText('New policy published: Remote Work Policy')).toBeVisible()
  })
})
