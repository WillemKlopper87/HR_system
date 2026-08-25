// hcm/frontend/e2e/documents.spec.ts
import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

const PDF_BYTES = Buffer.from('%PDF-1.4\nE2E test document content.')

test.describe('Employee documents & POPIA rights (C2)', () => {
  test('employee uploads a qualification, then a consent-gated ID copy, and deletes both', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/my-documents')
    await expectHeading(page, 'My Documents')
    await settled(page)

    // Qualification: Internal-tier, no consent required.
    await page.getByRole('button', { name: '+ Upload document' }).click()
    await page.getByLabel('Document type').selectOption('qualification')
    await page.getByLabel('Title').fill('E2E BCom Certificate')
    await page.getByLabel('File (PDF, JPEG, PNG, or Word)').setInputFiles({
      name: 'cert.pdf', mimeType: 'application/pdf', buffer: PDF_BYTES,
    })
    await page.getByRole('button', { name: 'Upload' }).click()
    await settled(page)
    const qualRow = page.locator('table tbody tr', { hasText: 'E2E BCom Certificate' })
    await expect(qualRow).toBeVisible()
    await expect(qualRow.getByRole('link', { name: 'Download' })).toHaveAttribute('href', /\/employee-documents\/\d+\/download\//)

    // ID copy: Restricted-tier, consent required — first attempt without
    // consent should surface the DocumentError as a form error.
    await page.getByRole('button', { name: '+ Upload document' }).click()
    await page.getByLabel('Document type').selectOption('id_copy')
    await expect(page.getByText('requires consent to be captured')).toBeVisible()
    await page.getByLabel('Title').fill('E2E ID Copy')
    await page.getByLabel('File (PDF, JPEG, PNG, or Word)').setInputFiles({
      name: 'id.pdf', mimeType: 'application/pdf', buffer: PDF_BYTES,
    })
    await page.getByRole('button', { name: 'Upload' }).click()
    await expect(page.locator('.form-error', { hasText: /consent/i })).toBeVisible()

    await page.getByRole('button', { name: 'Capture consent now' }).click()
    await page.getByRole('button', { name: 'Upload' }).click()
    await settled(page)
    const idRow = page.locator('table tbody tr', { hasText: 'E2E ID Copy' })
    await expect(idRow).toBeVisible()

    // Cleanup — delete both.
    page.on('dialog', (dialog) => void dialog.accept())
    await qualRow.getByRole('button', { name: 'Delete' }).click()
    await settled(page)
    await expect(page.locator('table tbody tr', { hasText: 'E2E BCom Certificate' })).toHaveCount(0)
  })

  test('employee adds a dependant and an emergency contact', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/my-documents')
    await settled(page)

    await page.getByRole('button', { name: '+ Add dependant' }).click()
    await page.getByLabel('First name').fill('E2E')
    await page.getByLabel('Last name').fill('Dependant')
    await page.getByLabel('Relationship').selectOption('child')
    await page.getByRole('button', { name: 'Add dependant' }).click()
    await settled(page)
    await expect(page.locator('table tbody tr', { hasText: 'E2E Dependant' })).toBeVisible()

    await page.getByRole('button', { name: '+ Add contact' }).click()
    await page.getByLabel('Name').fill('E2E Emergency Contact')
    await page.getByLabel('Phone').fill('0821234567')
    await page.getByRole('button', { name: 'Add contact' }).click()
    await settled(page)
    await expect(page.locator('table tbody tr', { hasText: 'E2E Emergency Contact' })).toBeVisible()
  })

  test('hr_admin manages documents/dependants/emergency contacts from the employee detail page', async ({ page }) => {
    // Resolve `employee`'s own id directly via the API rather than through
    // the /employees list page: that page fetchAllPages's the ENTIRE
    // (150+-row) employee list + current versions on first load with no
    // server-side filtering until a search term is typed, which is the
    // known pre-existing settled() timing flake documented in
    // SESSION-STATE.md ("Loading… still visible after 15s on the large
    // employee list") — a plain API call sidesteps it rather than risking
    // it, and is faster besides.
    await login(page, 'employee')
    await page.goto('/my-profile')
    await settled(page)
    const employeeNumber = await page.locator('dt:has-text("Employee number") + dd').innerText()

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'hradmin')
    const searchResponse = await page.request.get(`/api/v1/employees/?search=${encodeURIComponent(employeeNumber)}`)
    const employeeId = (await searchResponse.json()).results[0].id as number

    await page.goto(`/employees/${employeeId}`)
    await settled(page)

    await page.getByRole('heading', { name: 'Documents' }).scrollIntoViewIfNeeded()
    await page.getByRole('button', { name: '+ Upload document' }).click()
    await page.getByLabel('Document type').selectOption('employment_contract')
    await page.getByLabel('Title').fill('E2E Employment Contract')
    await page.getByLabel('File (PDF, JPEG, PNG, or Word)').setInputFiles({
      name: 'contract.pdf', mimeType: 'application/pdf', buffer: PDF_BYTES,
    })
    await page.getByRole('button', { name: 'Upload' }).click()
    await settled(page)
    const contractRow = page.locator('table tbody tr', { hasText: 'E2E Employment Contract' })
    await expect(contractRow).toBeVisible()
    await expect(contractRow.locator('td').nth(2)).toHaveText('R') // Restricted tier

    await page.getByRole('button', { name: '+ Add dependant' }).click()
    await page.getByLabel('First name').fill('HRAdded')
    await page.getByLabel('Last name').fill('Dependant')
    await page.getByRole('button', { name: 'Add dependant' }).click()
    await settled(page)
    await expect(page.locator('table tbody tr', { hasText: 'HRAdded Dependant' })).toBeVisible()
  })

  test('POPIA export request: employee submits, hr_admin completes it and can download the export', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/my-documents')
    await settled(page)

    await page.getByRole('button', { name: 'Request data export' }).click()
    await settled(page)
    await expect(page.locator('table tbody tr', { hasText: 'Export my data' }).first()).toContainText('Submitted')
    await expect(page.getByRole('button', { name: 'Export request pending' })).toBeVisible()

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'hradmin')
    await page.goto('/data-subject-requests')
    await expectHeading(page, 'Data-Subject Requests')
    await settled(page)
    // The queue hides actioned (non-"submitted") rows by default — check
    // this up front so the row stays visible once its status flips to
    // "Completed", rather than disappearing out from under the locator.
    await page.getByLabel('Show actioned').check()

    const row = page.locator('table tbody tr', { hasText: 'Export my data' }).first()
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Generate export' }).click()
    await settled(page)
    // The row's own "Working…" button state is a more precise signal than
    // settled() (which only tracks the page-level "Loading…" placeholder,
    // not this row-scoped mutation) — wait for it to clear before asserting
    // on the outcome, with a generous timeout for a loaded test environment.
    await expect(row.getByRole('button', { name: 'Working…' })).toHaveCount(0, { timeout: 20_000 })
    await expect(row).toContainText('Completed')
    await expect(row.getByRole('link', { name: 'Download' })).toHaveAttribute('href', /\/data-subject-requests\/\d+\/download\//)
  })

  test('POPIA erasure request: hr_admin can decline with a reason', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/my-documents')
    await settled(page)
    await page.getByRole('button', { name: 'Request erasure' }).click()
    await settled(page)

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'hradmin')
    await page.goto('/data-subject-requests')
    await settled(page)
    await page.getByLabel('Show actioned').check()

    const row = page.locator('table tbody tr', { hasText: 'Erasure request' }).first()
    await expect(row).toBeVisible()
    page.once('dialog', (dialog) => void dialog.accept('Not enough detail to action.'))
    await row.getByRole('button', { name: 'Decline' }).click()
    await settled(page)
    await expect(row.getByRole('button', { name: 'Working…' })).toHaveCount(0, { timeout: 20_000 })
    await expect(row).toContainText('Declined')
  })

  test('auditor sees the data-subject request queue read-only', async ({ page }) => {
    await login(page, 'auditor')
    await page.goto('/data-subject-requests')
    await expectHeading(page, 'Data-Subject Requests')
    await settled(page)
    await expect(page.getByRole('button', { name: 'Generate export' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Decline' })).toHaveCount(0)
  })

  test('a plain employee cannot reach the data-subject request queue', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/data-subject-requests')
    await page.waitForURL(/\/employees$/)
  })
})
