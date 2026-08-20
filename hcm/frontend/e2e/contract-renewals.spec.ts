import { expect, test } from '@playwright/test'
import { expectHeading, login, logout, settled } from './helpers'

// Fixtures: seed_demo_data.py seeds two of eng_head's ('manager' login)
// direct reports as fixed-term with a contract_end_date set --
// "Renewal Contractor" (recommend/decide RENEW below) and "Lapse
// Contractor" (hr_admin decides LET_LAPSE directly, no recommendation
// step). Both share a last name, so locators match on the full "First
// Last" text to keep the two rows unambiguous.

test.describe('Contract end-date tracking & renewal decisions (C1 part 2)', () => {
  test('manager recommends -> hr_admin decides RENEW -> resulting version reflects the extended date', async ({
    page,
  }) => {
    await login(page, 'manager')
    await page.goto('/contract-renewals')
    await expectHeading(page, 'Contract Renewals')
    await settled(page)

    const row = page.locator('tr', { hasText: 'Renewal Contractor' })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Recommend' }).click()
    await row.getByLabel('Action').selectOption('renew')
    await row.getByLabel('New end date').fill('2027-12-31')
    await row.getByRole('button', { name: 'Submit recommendation' }).click()
    await settled(page)
    await expect(row.locator('.status-badge')).toHaveText('recommended')

    await logout(page)
    await login(page, 'hradmin')
    await page.goto('/contract-renewals')
    await settled(page)

    const hrRow = page.locator('tr', { hasText: 'Renewal Contractor' })
    await hrRow.getByRole('button', { name: 'Decide' }).click()
    // Pre-filled from the manager's recommendation.
    await expect(hrRow.getByLabel('Action')).toHaveValue('renew')
    await expect(hrRow.getByLabel('New end date')).toHaveValue('2027-12-31')
    await hrRow.getByRole('button', { name: 'Submit decision' }).click()
    await settled(page)

    // decide_contract_action's RENEW path closes the decided-on version and
    // opens a brand-new current EmployeeVersion carrying the extended
    // contract_end_date -- that new version has no ContractRenewalDecision
    // of its own yet, so the row survives (still fixed-term + current) but
    // resets to "none" rather than showing "decided".
    const resultRow = page.locator('tr', { hasText: 'Renewal Contractor' })
    await expect(resultRow).toHaveCount(1)
    await expect(resultRow).toContainText('2027-12-31')
    await expect(resultRow.locator('.status-badge')).toHaveText('none')
  })

  test('hr_admin decides LET_LAPSE -> the employee drops off the current fixed-term list', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/contract-renewals')
    await expectHeading(page, 'Contract Renewals')
    await settled(page)

    const row = page.locator('tr', { hasText: 'Lapse Contractor' })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Decide' }).click()
    await row.getByLabel('Action').selectOption('let_lapse')
    await row.getByRole('button', { name: 'Submit decision' }).click()
    await settled(page)

    // LET_LAPSE closes the current version via a TERMINATION event and
    // opens no replacement -- the employee simply drops out of the
    // ?fixed_term=true&current=true list this page renders.
    await expect(page.locator('tr', { hasText: 'Lapse Contractor' })).toHaveCount(0)

    await logout(page)
  })
})
