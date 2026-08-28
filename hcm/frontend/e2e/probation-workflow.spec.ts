import { expect, test, type Page } from '@playwright/test'
import { expectHeading, login, logout } from './helpers'

async function browserPost(page: Page, path: string, data: unknown) {
  return page.evaluate(async ({ path, data }) => {
    const csrf = document.cookie
      .split('; ')
      .find((part) => part.startsWith('csrftoken='))
      ?.split('=')[1]
    const response = await fetch(`/api/v1${path}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        ...(csrf ? { 'X-CSRFToken': decodeURIComponent(csrf) } : {}),
      },
      body: JSON.stringify(data),
    })
    return { status: response.status, body: await response.json() }
  }, { path, data })
}

async function selectEmployee(page: Page, employeeNumber: string) {
  const selector = page.getByRole('combobox', { name: 'Employee' })
  await selector.fill(employeeNumber)
  await page.getByRole('option', { name: new RegExp(`^${employeeNumber}`) }).click()
}

test('probation lifecycle enforces dates, manager scope and employee-only signature', async ({ page }) => {
  test.setTimeout(90_000)
  // Discover the seeded employee identity through their own row-scoped API.
  await login(page, 'employee')
  const me = await page.evaluate(async () => (await fetch('/api/v1/auth/me/')).json())
  const employee = await page.evaluate(async (id) => (await fetch(`/api/v1/employees/${id}/`)).json(), me.employee_id)
  await logout(page)

  // HR sees validation failures in the real form, then opens a valid period.
  await login(page, 'hradmin')
  await page.goto('/probation')
  await expectHeading(page, 'Probation')
  await selectEmployee(page, employee.employee_number)
  await page.getByLabel('Start date').fill('2026-09-30')
  await page.getByLabel('End date').fill('2026-09-01')
  const invalidResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/probation-periods/') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Open probation period' }).click()
  expect((await invalidResponse).status()).toBe(400)
  await expect(page.getByText('Request failed (400)')).toBeVisible()

  await page.getByLabel('Start date').fill('2026-09-01')
  await page.getByLabel('End date').fill('2026-11-30')
  const createdResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/probation-periods/') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Open probation period' }).click()
  const created = await createdResponse
  expect(created.status()).toBe(201)
  const period = await created.json()
  await expect(page.getByRole('heading', { level: 3, name: new RegExp(employee.employee_number) })).toBeVisible()

  await selectEmployee(page, employee.employee_number)
  await page.getByLabel('Start date').fill('2026-10-01')
  await page.getByLabel('End date').fill('2026-12-31')
  const overlapResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/probation-periods/') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Open probation period' }).click()
  expect((await overlapResponse).status()).toBe(400)
  await expect(page.getByText('Request failed (400)')).toBeVisible()

  // Create a period outside the seeded manager's reporting scope for the
  // negative authorization check. It is deliberately created over the API:
  // row scoping correctly prevents the manager from seeing a form for it.
  const departingSearch = await page.evaluate(async () =>
    (await fetch('/api/v1/employees/search-summary/?q=E90001')).json(),
  )
  const unrelatedEmployee = departingSearch.results[0]
  const unrelatedPeriod = await browserPost(page, '/probation-periods/', {
    employee: unrelatedEmployee.id,
    start_date: '2026-01-01',
    end_date: '2026-03-31',
  })
  expect(unrelatedPeriod.status).toBe(201)
  await logout(page)

  // The correct line manager can review their direct report.
  await login(page, 'manager')
  await page.goto('/probation')
  const periodCard = page.locator('div.detail-card').filter({
    has: page.getByRole('heading', { level: 3, name: new RegExp(employee.employee_number) }),
  })
  await expect(periodCard).toBeVisible()
  const reviewForm = periodCard.getByRole('form', { name: 'Add probation review' })
  await reviewForm.getByLabel('Review date').fill('2026-10-01')
  await reviewForm.getByLabel('Comments').fill('Progress reviewed with employee')
  const reviewResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/probation-reviews/') && response.request().method() === 'POST',
  )
  await reviewForm.getByRole('button', { name: 'Add review' }).click()
  const reviewCreated = await reviewResponse
  expect(reviewCreated.status()).toBe(201)
  const review = await reviewCreated.json()
  await expect(periodCard.getByText('Awaiting employee')).toBeVisible()
  await expect(periodCard.getByRole('button', { name: 'Countersign' })).toHaveCount(0)

  const unrelatedReview = await browserPost(page, '/probation-reviews/', {
    probation_period: unrelatedPeriod.body.id,
    review_date: '2026-02-01',
    recommendation: 'continue',
    comments: 'Must be rejected outside reporting scope',
  })
  expect(unrelatedReview.status).toBe(403)
  const managerSign = await browserPost(page, `/probation-reviews/${review.id}/sign/`, { password: 'manager123' })
  expect(managerSign.status).toBe(403)
  await logout(page)

  // HR can administer the workflow but cannot impersonate the employee's signature.
  await login(page, 'hradmin')
  await page.goto('/probation')
  const hrCard = page.locator('div.detail-card').filter({
    has: page.getByRole('heading', { level: 3, name: new RegExp(employee.employee_number) }),
  })
  await expect(hrCard.getByRole('button', { name: 'Countersign' })).toHaveCount(0)
  const hrSign = await browserPost(page, `/probation-reviews/${review.id}/sign/`, { password: 'hradmin123' })
  expect(hrSign.status).toBe(403)
  await logout(page)

  // Only the employee sees the action and can countersign using current-password reauthentication.
  await login(page, 'employee')
  await page.getByRole('link', { name: 'Probation' }).click()
  await expectHeading(page, 'Probation')
  const employeeCard = page.locator('div.detail-card').filter({
    has: page.getByRole('heading', { level: 3, name: new RegExp(employee.employee_number) }),
  })
  page.once('dialog', (dialog) => dialog.accept('employee123'))
  await employeeCard.getByRole('button', { name: 'Countersign' }).click()
  await expect(employeeCard.getByText(/^Signed /)).toBeVisible()

  // Keep the created period identity anchored in the end-to-end assertion.
  expect(period.employee).toBe(employee.id)
})
