import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

test.describe('recruitment (Sprint 4-5)', () => {
  test('recruiter: requisitions list, create one, applicants and dashboard', async ({ page }) => {
    // Requisition.positions must match headcount 1:1 (C1 establishment
    // control) -- propose and fully approve a position first so the
    // requisition form's picker has an approved, vacant candidate to
    // select (same department/occupational level the form picks below).
    const positionTitle = `E2E Talent Post ${Date.now().toString().slice(-5)}`
    await login(page, 'hradmin')
    await page.goto('/positions')
    await settled(page)
    await page.getByRole('button', { name: '+ Propose position' }).click()
    await page.getByLabel('Title').fill(positionTitle)
    await page.getByLabel('Department').selectOption({ index: 1 })
    await page.getByLabel('Occupational level').selectOption({ index: 1 })
    await page.getByLabel('Location').selectOption({ index: 1 })
    await page.getByRole('button', { name: 'Propose position' }).click()
    await settled(page)
    await page.locator('tr', { hasText: positionTitle }).getByRole('button', { name: 'Submit' }).click()
    await settled(page)
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    await login(page, 'compmanager')
    await page.goto('/positions')
    await settled(page)
    await page.locator('tr', { hasText: positionTitle }).getByRole('button', { name: 'Approve' }).click()
    await settled(page)
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    await login(page, 'accountingofficer')
    await page.goto('/positions')
    await settled(page)
    await page.locator('tr', { hasText: positionTitle }).getByRole('button', { name: 'Approve' }).click()
    await settled(page)
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    await login(page, 'recruiter')
    await page.goto('/requisitions')
    await expectHeading(page, 'Requisitions')
    await settled(page)
    const before = await page.locator('table tbody tr').count()

    await page.getByRole('button', { name: '+ New requisition' }).click()
    const title = `E2E Engineer ${Date.now().toString().slice(-5)}`
    await page.getByLabel('Title').fill(title)
    await page.getByLabel('Department').selectOption({ index: 1 })
    await page.getByLabel('Occupational level').selectOption({ index: 1 })
    await page.getByLabel('Location').selectOption({ index: 1 })
    await page.getByLabel(positionTitle, { exact: false }).check()
    await page.getByRole('button', { name: 'Create requisition' }).click()
    await expect(page.locator('table tbody tr', { hasText: title })).toHaveCount(1)
    expect(await page.locator('table tbody tr').count()).toBe(before + 1)

    await page.goto('/applicants')
    await expectHeading(page, 'Applicants')
    await settled(page)
    await expect(page.locator('table tbody tr').first()).toBeVisible()
    await page.locator('table tbody tr').first().getByRole('link').first().click()
    await page.waitForURL(/\/applicants\/\d+$/)
    await settled(page)
    for (const h of ['Application', 'Demographics', 'Assessments', 'Pipeline history']) {
      await expect(page.getByRole('heading', { name: h, exact: true })).toBeVisible()
    }

    await page.goto('/dashboards/recruitment')
    await expectHeading(page, 'Recruitment Dashboard')
    await settled(page)
    await expect(page.locator('.stat-tile', { hasText: 'Open requisitions' })).toBeVisible()
  })

  test('recruiter is kept out of the performance and comp modules', async ({ page }) => {
    await login(page, 'recruiter')
    await page.goto('/review-cycles')
    await page.waitForURL(/\/employees$/)
    await page.goto('/comp-proposals')
    await page.waitForURL(/\/employees$/)
  })
})

test.describe('performance (Sprint 6-7)', () => {
  test('hr_admin sees cycles; manager sees team reviews and can open one', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/review-cycles')
    await expectHeading(page, 'Review Cycles')
    await settled(page)
    await expect(page.getByRole('heading', { level: 2 }).first()).toBeVisible()
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    await login(page, 'manager')
    await page.goto('/reviews')
    await expectHeading(page, 'Reviews')
    await settled(page)
    const first = page.locator('table tbody tr').first()
    await expect(first).toBeVisible()
    await first.getByRole('link').first().click()
    await page.waitForURL(/\/reviews\/\d+$/)
    await settled(page)
    await expectHeading(page, 'Review')
  })
})

test.describe('learning (Sprint 8-9)', () => {
  test('manager: team development table; hr_admin: skills inventory', async ({ page }) => {
    await login(page, 'manager')
    await page.goto('/team-development')
    await expectHeading(page, 'Team Development')
    await settled(page)
    await expect(page.locator('table thead')).toContainText('Training completed')
    await expect(page.locator('table tbody tr').first()).toBeVisible()
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    await login(page, 'hradmin')
    await page.goto('/skills-inventory')
    await expectHeading(page, 'Skills Inventory')
    await settled(page)
    await expect(page.getByRole('heading', { level: 2 }).first()).toBeVisible()
  })
})

test.describe('assessments (Sprint 12)', () => {
  test('ee_manager sees the employee-assessment workflow page; employee is redirected', async ({ page }) => {
    await login(page, 'eemanager')
    await page.goto('/assessments')
    await expectHeading(page, 'Employee Assessments')
    await settled(page)
    await expect(page.locator('table tbody tr').first()).toBeVisible()
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    await login(page, 'employee')
    await page.goto('/assessments')
    await page.waitForURL(/\/employees$/)
  })
})
