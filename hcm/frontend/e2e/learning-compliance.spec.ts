// hcm/frontend/e2e/learning-compliance.spec.ts
import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

test.describe('Mandatory-training compliance (C6)', () => {
  test('hr_admin: catalogue shows seeded courses, can add a new mandatory course and requirement', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/course-catalogue')
    await expectHeading(page, 'Course Catalogue')
    await settled(page)

    // Two tables on this page (courses, then requirements) -- a seeded
    // requirement's "Course" column also contains the course name, so an
    // unscoped `table tbody tr` matches rows in both. Scope to the first
    // table (courses) here.
    const coursesTable = page.locator('table').first()
    await expect(coursesTable.locator('tbody tr', { hasText: 'POPIA Awareness Refresher' })).toBeVisible()
    await expect(coursesTable.locator('tbody tr', { hasText: 'Workplace Safety Induction' })).toBeVisible()

    const courseName = `E2E Compliance Course ${Date.now().toString().slice(-5)}`
    await page.getByRole('button', { name: '+ New course' }).click()
    await page.getByLabel('Course name').fill(courseName)
    await page.getByLabel('Mandatory / compliance course').check()
    await page.getByRole('button', { name: 'Create course' }).click()
    await settled(page)
    await expect(coursesTable.locator('tbody tr', { hasText: courseName })).toBeVisible()

    await page.getByRole('button', { name: '+ New requirement' }).click()
    await page.getByLabel('Course (mandatory only)').selectOption({ label: courseName })
    await page.getByLabel('Effective from').fill('2026-01-01')
    await page.getByLabel('Due within (days)').fill('90')
    await page.getByRole('button', { name: 'Create requirement' }).click()
    await settled(page)
    const requirementsTable = page.locator('table').nth(1)
    await expect(requirementsTable.locator('tbody tr', { hasText: courseName })).toContainText('Org-wide')
  })

  test('hr_admin: training compliance dashboard shows completion-rate rollup', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/dashboards/training-compliance')
    await expectHeading(page, 'Training Compliance')
    await settled(page)

    const popiaSection = page.locator('section', { has: page.getByRole('heading', { name: 'POPIA Awareness Refresher' }) })
    await expect(popiaSection).toBeVisible()
    await expect(popiaSection).toContainText('compliant')
    await expect(popiaSection.getByText('By department')).toBeVisible()
    await expect(popiaSection.getByText('By occupational level')).toBeVisible()
  })

  test('a non-hr_admin cannot reach the catalogue or the compliance dashboard', async ({ page }) => {
    await login(page, 'manager')
    await page.goto('/course-catalogue')
    await page.waitForURL(/\/employees$/)
    await page.goto('/dashboards/training-compliance')
    await page.waitForURL(/\/employees$/)
  })

  test('manager: team development shows the row-scoped overdue mandatory training list', async ({ page }) => {
    await login(page, 'manager')
    await page.goto('/team-development')
    await expectHeading(page, 'Team Development')
    await settled(page)

    await expect(page.getByRole('heading', { name: 'Overdue mandatory training' })).toBeVisible()
    // Seeded: Workplace Safety Induction is required org-wide across
    // Engineering (department-scoped, effective long in the past, nobody
    // in the seed data has a completed record for it), so the whole
    // Engineering reporting chain under "manager" shows up here, not just
    // one row -- assert at least one row exists rather than exactly one.
    // See seed_demo_data.py::_seed_learning_demo_data.
    const overdueRows = page.locator('table tbody tr', { hasText: 'Workplace Safety Induction' })
    await expect(overdueRows.first()).toBeVisible()
  })

  test('employee: my learning enrollment form can reference a catalogue course', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/my-learning')
    await expectHeading(page, 'My Learning')
    await settled(page)

    await page.getByRole('button', { name: '+ Request enrollment' }).click()
    // Option label is the exact rendered text -- MyLearningPage appends
    // " (mandatory)" for a mandatory catalogue course (selectOption's
    // `label` must be an exact string match, not a pattern).
    await page.getByLabel('From the catalogue (optional)').selectOption({ label: 'Workplace Safety Induction (mandatory)' })
    await expect(page.getByLabel('Course/training title')).toHaveValue('Workplace Safety Induction')
    await page.getByRole('button', { name: 'Request enrollment' }).click()
    await settled(page)
    await expect(page.locator('table tbody tr', { hasText: 'Workplace Safety Induction' }).first()).toBeVisible()
  })
})
