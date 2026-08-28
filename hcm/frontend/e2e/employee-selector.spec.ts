import { expect, test } from '@playwright/test'
import { expectHeading, login } from './helpers'

test('probation uses the scoped minimal employee search', async ({ page }) => {
  const employeeRequests: string[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/v1/employees')) employeeRequests.push(`${url.pathname}${url.search}`)
  })

  await login(page, 'hradmin')
  await page.goto('/probation')
  await expectHeading(page, 'Probation')

  const employee = page.getByRole('combobox', { name: 'Employee' })
  const searchResponsePromise = page.waitForResponse((response) =>
    response.url().includes('/api/v1/employees/search-summary/?q=E0'),
  )
  await employee.fill('E0')
  const searchResponse = await searchResponsePromise
  const body = await searchResponse.json()
  expect(body.results.length).toBeGreaterThan(0)
  expect(Object.keys(body.results[0]).sort()).toEqual(['display_name', 'employee_number', 'id'])

  await expect(page.getByRole('option').first()).toBeVisible()
  await page.getByRole('option').first().click()
  await expect(employee).toHaveValue(/E\d+ — .+/)
  expect(employeeRequests.some((path) => path === '/api/v1/employees/')).toBe(false)
})

test('exit interview employee selector is keyboard operable', async ({ page }) => {
  await login(page, 'hradmin')
  await page.goto('/exit-interviews')
  await expectHeading(page, 'Exit Interviews')

  const employee = page.getByRole('combobox', { name: 'Employee' })
  await employee.fill('E0')
  await expect(page.getByRole('option').first()).toBeVisible()
  await employee.press('ArrowDown')
  await employee.press('Enter')
  await expect(employee).toHaveValue(/E\d+ — .+/)
})
