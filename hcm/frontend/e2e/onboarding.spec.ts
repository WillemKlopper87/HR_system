// hcm/frontend/e2e/onboarding.spec.ts
import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

test.describe('Onboarding / offboarding checklists (C1 part 3 slice 3)', () => {
  test('hr_admin creates a draft template, adds a task, and publishes it', async ({ page }) => {
    // Timestamp-suffixed like establishment.spec.ts's positionTitle -- the
    // backend persists across retries within one run, so a static name
    // risks a duplicate surviving a retry and breaking a strict-mode
    // locator below.
    const templateName = `E2E Onboarding Template ${Date.now().toString().slice(-5)}`
    await login(page, 'hradmin')
    await page.goto('/checklist-templates')
    await expectHeading(page, 'Checklist Templates')
    await settled(page)

    await page.getByRole('button', { name: '+ New template' }).click()
    await page.getByLabel('Name').fill(templateName)
    await page.getByRole('button', { name: 'Create draft' }).click()
    await settled(page)

    const card = page.locator('.detail-card', { hasText: templateName })
    await expect(card).toBeVisible()
    await expect(card).toContainText('draft')

    // A freshly created template has no tasks, so it can't be published yet.
    await expect(card.getByRole('button', { name: 'Publish' })).toHaveCount(0)

    await card.getByLabel('Task').fill('Issue laptop')
    await card.getByLabel('Description').fill('Provision a laptop and access card.')
    await card.getByRole('button', { name: '+ Add task' }).click()
    await settled(page)
    await expect(card.getByText('Issue laptop')).toBeVisible()

    await card.getByRole('button', { name: 'Publish' }).click()
    await settled(page)
    await expect(card).toContainText('published')
    // Once published, the task list is frozen -- no more "+ Add task" form.
    await expect(card.getByRole('button', { name: '+ Add task' })).toHaveCount(0)
  })

  test('a plain employee cannot reach the templates page', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/checklist-templates')
    await page.waitForURL(/\/employees$/)
  })

  test('the seeded onboarding checklist shows a mix of done/not-done, and the line manager can complete their task', async ({ page }) => {
    // `manager` (eng_head) directly manages dozens of seeded employees, not
    // just `staff` -- every one of them has an onboarding checklist
    // containing the same "Introduce to line manager and team" row, so a
    // bare text locator on /checklists as `manager` matches many rows (a
    // strict-mode violation). Find `staff`'s own display name first (as
    // `employee`, who sees only their own single checklist) and scope the
    // manager's view to the one card for that person.
    await login(page, 'employee')
    await page.goto('/checklists')
    await expectHeading(page, 'Checklists')
    await settled(page)
    const staffName = await page.locator('.detail-card h3').first().innerText()

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'manager')
    await page.goto('/checklists')
    await settled(page)

    const staffCard = page.locator('.detail-card', { hasText: staffName })
    await expect(staffCard).toBeVisible()

    // seed_demo_data ticks off two of `staff`'s onboarding tasks and leaves
    // the line_manager-owned one ("Introduce to line manager and team")
    // pending -- `manager` is `staff`'s manager, so it should show up here.
    const managerTask = staffCard.locator('tr', { hasText: 'Introduce to line manager and team' })
    await expect(managerTask).toBeVisible()
    await expect(managerTask).toContainText('Pending')

    await managerTask.getByRole('button', { name: 'Complete' }).click()
    await settled(page)
    await expect(managerTask).toContainText('Done')

    // Reopening is available (the undo path for a mis-click).
    await managerTask.getByRole('button', { name: 'Reopen' }).click()
    await settled(page)
    await expect(managerTask).toContainText('Pending')
  })

  test('the checklist subject can see their own checklist but never completes a task themselves', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/checklists')
    await expectHeading(page, 'Checklists')
    await settled(page)

    await expect(page.getByText('Issue laptop and access card')).toBeVisible()
    // No Complete/Reopen button anywhere on the page for the checklist's
    // own subject (design spec §3, decision 1).
    await expect(page.getByRole('button', { name: 'Complete' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Reopen' })).toHaveCount(0)
  })

  test('the demo resignation created a real offboarding checklist', async ({ page }) => {
    // Scoped to the "Departing Demo" card specifically -- when the full
    // suite runs, contract-renewals.spec.ts's `let_lapse` action creates a
    // SECOND real offboarding checklist (a lapsed contract routes through
    // the same execute_employment_change path, spec §6.2), so a bare
    // page-wide text search for a task label common to every offboarding
    // checklist matches more than one row.
    await login(page, 'hradmin')
    await page.goto('/checklists')
    await settled(page)
    await page.getByRole('button', { name: 'Offboarding' }).click()
    await settled(page)
    const departingCard = page.locator('.detail-card', { hasText: 'Departing Demo' })
    await expect(departingCard).toBeVisible()
    await expect(departingCard.getByText('Collect laptop, access card and other assets')).toBeVisible()
  })
})
