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

const migratedSelectors = [
  { name: 'employment changes', user: 'hradmin', path: '/employment-changes', heading: 'Employment Changes', open: '+ Propose change', label: 'Employee' },
  { name: 'assessments', user: 'eemanager', path: '/assessments', heading: 'Employee Assessments', open: '+ Assign assessment', label: 'Employee' },
  { name: 'benefit elections', user: 'compmanager', path: '/benefits', heading: 'Benefits', open: '+ Record election', label: 'Employee' },
  { name: 'EE plan ownership', user: 'eemanager', path: '/ee-configuration', heading: 'EE Reporting Configuration', label: 'Responsible person' },
] as const

for (const scenario of migratedSelectors) {
  test(`${scenario.name} uses scoped minimal employee search`, async ({ page }) => {
    const employeeRequests: string[] = []
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (url.pathname.startsWith('/api/v1/employees')) employeeRequests.push(`${url.pathname}${url.search}`)
    })

    await login(page, scenario.user)
    await page.goto(scenario.path)
    await expectHeading(page, scenario.heading)
    if ('open' in scenario) await page.getByRole('button', { name: scenario.open }).click()

    const employee = page.getByRole('combobox', { name: scenario.label })
    const searchResponsePromise = page.waitForResponse((response) =>
      response.url().includes('/api/v1/employees/search-summary/?q=E0'),
    )
    await employee.fill('E0')
    const body = await (await searchResponsePromise).json()
    expect(body.results.length).toBeGreaterThan(0)
    expect(Object.keys(body.results[0]).sort()).toEqual(['display_name', 'employee_number', 'id'])
    expect(employeeRequests.some((path) => path === '/api/v1/employees/')).toBe(false)
  })
}

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
