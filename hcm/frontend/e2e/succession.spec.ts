// hcm/frontend/e2e/succession.spec.ts
import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

test.describe('Succession planning / talent pools (C6)', () => {
  test('hr_admin: flag a post critical, nominate a successor, see it everywhere it should appear, withdraw', async ({ page }) => {
    // Propose + fully approve a fresh, uniquely-titled (and therefore
    // vacant) position first -- same setup establishment.spec.ts/
    // talent.spec.ts use -- so flagging it critical never collides with an
    // existing occupant, and the nominate picker's "not the current
    // occupant" filter can never accidentally exclude the employee we pick.
    const positionTitle = `E2E Succession Post ${Date.now().toString().slice(-5)}`
    await login(page, 'hradmin')
    await page.goto('/positions')
    await expectHeading(page, 'Positions')
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

    await login(page, 'hradmin')

    // Positions page: not critical yet.
    await page.goto('/positions')
    await settled(page)
    const positionRow = page.locator('tr', { hasText: positionTitle })
    await expect(positionRow).toBeVisible()
    await expect(positionRow.getByText('Critical', { exact: true })).toHaveCount(0)

    // Flag it critical on the Talent Pools page.
    await page.goto('/talent-pools')
    await expectHeading(page, 'Talent Pools')
    await settled(page)
    await page.getByRole('button', { name: '+ Flag a critical post' }).click()
    // selectOption({ label }) requires an exact string match, and the full
    // option label includes a server-assigned post number and department
    // name this test doesn't know in advance -- find the option by its
    // (known) title substring instead, and select by its actual value.
    const positionSelect = page.getByLabel('Position (approved posts only)')
    const positionOptionValue = await positionSelect.locator('option', { hasText: positionTitle }).getAttribute('value')
    expect(positionOptionValue).toBeTruthy()
    await positionSelect.selectOption(positionOptionValue!)
    await page.getByLabel('Why this post is succession-critical').fill('E2E: sole SME, no backup today.')
    await page.getByRole('button', { name: 'Flag as critical' }).click()
    await settled(page)

    const criticalCard = page.locator('.detail-card', { hasText: positionTitle })
    await expect(criticalCard).toBeVisible()
    await expect(criticalCard).toContainText('Vacant')

    // Nominate a successor -- the vacant post's "not the current occupant"
    // filter excludes nobody, and nothing else has been nominated yet, so
    // any real option would normally be safe... except index 1 could land
    // on hradmin's OWN employee record, and the backend's get_queryset
    // self-exclusion (spec §5.2) means hradmin can never see a row about
    // themself again through this same endpoint -- exactly the "no self-
    // scope carve-out anywhere" rule working as designed, but it silently
    // breaks a test that assumes whichever row it just created is visible
    // to the actor that created it. Exclude hradmin's own id explicitly.
    const me = await (await page.request.get('/api/v1/auth/me/')).json()
    const ownId = Number(me.employee_id)
    const employeeSearch = await (await page.request.get('/api/v1/employees/search-summary/?q=E0')).json()
    const candidate = employeeSearch.results.find((employee: { id: number }) => employee.id !== ownId)
    expect(candidate).toBeTruthy()
    await criticalCard.getByRole('button', { name: '+ Nominate' }).click()
    const employeeSelect = criticalCard.getByRole('combobox', { name: 'Employee' })
    await employeeSelect.fill(candidate.employee_number)
    const candidateOption = criticalCard.getByRole('option', {
      name: `${candidate.employee_number} — ${candidate.display_name}`,
    })
    await expect(candidateOption).toBeVisible()
    await candidateOption.click()
    const candidateId = String(candidate.id)
    const candidateLabel = `${candidate.employee_number} — ${candidate.display_name}`
    await criticalCard.getByLabel('Readiness').selectOption('ready_now')
    await criticalCard.getByLabel('Notes').fill('E2E: strong technical depth, ready today.')
    await criticalCard.getByRole('button', { name: 'Nominate' }).click()
    await settled(page)

    const candidateRow = criticalCard.locator('tr', { hasText: candidateLabel })
    await expect(candidateRow).toBeVisible()
    await expect(candidateRow.locator('select')).toHaveValue('ready_now')

    // Positions page now shows the Critical badge.
    await page.goto('/positions')
    await settled(page)
    await expect(page.locator('tr', { hasText: positionTitle }).getByText('Critical', { exact: true })).toBeVisible()

    // The candidate's own Employee Detail page shows the read-only
    // Succession section (hr_admin is viewing SOMEONE ELSE's record here).
    await page.goto(`/employees/${candidateId}`)
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Succession' })).toBeVisible()
    await expect(page.getByText(positionTitle, { exact: false })).toBeVisible()
    await expect(page.getByText('Ready now')).toBeVisible()

    // Withdraw the nomination from the Talent Pools page.
    await page.goto('/talent-pools')
    await settled(page)
    const card = page.locator('.detail-card', { hasText: positionTitle })
    page.once('dialog', (dialog) => void dialog.accept())
    await card.locator('tr', { hasText: candidateLabel }).getByRole('button', { name: 'Withdraw' }).click()
    await settled(page)
    await expect(page.locator('.detail-card', { hasText: positionTitle })).toContainText('No successor candidates nominated yet.')

    // Withdrawn candidate no longer shows on the employee's own detail page.
    await page.goto(`/employees/${candidateId}`)
    await settled(page)
    await expect(page.getByText('Not currently nominated as a successor for any critical post.')).toBeVisible()
  })

  test('a line manager has no Talent Pools nav item and gets 403 hitting the succession API directly', async ({ page }) => {
    await login(page, 'manager')
    await expect(page.getByRole('link', { name: 'Talent Pools' })).toHaveCount(0)
    const response = await page.request.get('/api/v1/succession-candidates/')
    expect(response.status()).toBe(403)
    await page.goto('/talent-pools')
    await page.waitForURL(/\/employees$/)
  })

  test('nobody sees their own succession status, not even hr_admin viewing their own record', async ({ page }) => {
    await login(page, 'hradmin')
    const me = await (await page.request.get('/api/v1/auth/me/')).json()
    const ownId: number = me.employee_id

    // hr_admin's own Employee Detail page: no Succession section at all --
    // the section is skipped client-side, and even a direct API call
    // filtered to their own id would come back empty (backend get_queryset
    // self-exclusion, covered at the API level in succession/test_api.py).
    await page.goto(`/employees/${ownId}`)
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Succession' })).toHaveCount(0)
  })
})
