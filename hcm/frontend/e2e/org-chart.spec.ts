import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

test.describe('Organisation chart topology contract', () => {
  test('renders the chart without downloading detailed employee rows', async ({ page }) => {
    const detailedEmployeeRequests: string[] = []
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (url.pathname === '/api/v1/employees/') detailedEmployeeRequests.push(request.url())
    })

    await login(page, 'hradmin')
    await page.goto('/org-chart')
    await expectHeading(page, 'Org Chart')
    await settled(page)

    await expect(page.locator('.org-node-card').first()).toBeVisible()
    await expect(page.getByText(/people shown/)).toBeVisible()
    expect(detailedEmployeeRequests).toEqual([])

    const response = await page.request.get('/api/v1/employees/org-chart/')
    expect(response.ok()).toBeTruthy()
    const body = await response.json()
    expect(body.results.length).toBeGreaterThan(0)
    expect(Object.keys(body.results[0]).sort()).toEqual([
      'department', 'display_name', 'employee_id', 'employee_number', 'job_title', 'manager_id',
    ])
  })

  test('search remains keyboard accessible on compact topology data', async ({ page }) => {
    await login(page, 'manager')
    await page.goto('/org-chart')
    await settled(page)

    const firstCardText = await page.locator('.org-node-card').first().innerText()
    const employeeNumber = firstCardText.match(/#(\S+)/)?.[1]
    expect(employeeNumber).toBeTruthy()
    const search = page.getByPlaceholder('Search by name, title, or department…')
    await search.fill(employeeNumber!)
    await expect(page.locator('.org-node-match').first()).toBeVisible()
  })
})
