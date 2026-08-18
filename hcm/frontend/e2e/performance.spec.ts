import { expect, test } from '@playwright/test'
import { expectHeading, login, logout, settled } from './helpers'

/** PC-1: KPI contracting end to end in a real browser — the scorecard grid,
 * the 100%-weight rule, submit → return → resubmit → approve, the
 * employee-then-Head signing order (including the refusal), the signed PDF and
 * its signature trail, and HR's period/reminder view.
 *
 * The seeded `employee` login reports to the seeded `manager` login, so those
 * two drive the whole contracting conversation the way two real people would.
 */
test.describe('performance agreements (PC-1)', () => {
  test('hr_admin sees the period, its reminder schedule and contracting completion', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/performance-periods')
    await expectHeading(page, 'Performance Periods')
    await settled(page)
    await expect(page.getByRole('heading', { name: /2026\/27/ })).toBeVisible()
    await expect(page.getByLabel('Reminder offsets in days before the deadline').first()).toHaveValue('28, 14, 7, 1')
    await expect(page.getByRole('heading', { name: 'Contracting completion' })).toBeVisible()
    await expect(page.getByText(/of \d+ signed/)).toBeVisible()
    const templateRow = page.locator('table tbody tr', { hasText: 'Sentech Individual Scorecard' })
    await expect(templateRow).toContainText('Published')
    await expect(templateRow).toContainText('100%')
  })

  test('full contracting flow: draft → submit → return → resubmit → approve → employee signs → Head signs', async ({
    page,
  }) => {
    // --- employee: read the scorecard, break the weight rule, fix it, submit
    await login(page, 'employee')
    await page.goto('/my-performance')
    await expectHeading(page, 'My Performance')
    await settled(page)
    await expect(page.getByRole('heading', { name: /2026\/27 scorecard/ })).toBeVisible()
    await expect(page.getByText('DRIVE SUSTAINABLE GROWTH')).toBeVisible()
    await expect(page.getByText('Diversified (new) revenue growth')).toBeVisible()
    await expect(page.locator('.detail-field', { hasText: 'Total weight' })).toContainText('100%')
    // nothing to sign yet — the Head has not approved
    await expect(page.getByRole('button', { name: 'Sign as the individual' })).toHaveCount(0)

    const weight = page.getByLabel(/^Weight for /).first()
    const original = await weight.inputValue()
    await weight.fill('5')
    await weight.blur()
    await expect(page.locator('.detail-field', { hasText: 'Total weight' })).toContainText('must total 100%')
    await page.getByRole('button', { name: 'Submit to my Head' }).click()
    await expect(page.locator('.form-error').first()).toContainText(/1\.00|100%/)

    await page.getByLabel(/^Weight for /).first().fill(original)
    await page.getByLabel(/^Weight for /).first().blur()
    // ("must total 100%" also contains "100%", so assert the warning is gone)
    await expect(page.locator('.detail-field', { hasText: 'Total weight' })).not.toContainText('must total')
    await page.getByRole('button', { name: 'Submit to my Head' }).click()
    await expect(page.locator('.status-badge').first()).toContainText('Submitted')
    await logout(page)

    // --- Head: return it for changes
    await login(page, 'manager')
    await page.goto('/team-performance')
    await expectHeading(page, 'Team Performance')
    await settled(page)
    const row = page.locator('table tbody tr', { hasText: 'Submitted to Head' }).first()
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Open' }).click()
    await settled(page)
    // the Head cannot sign anything yet
    await expect(page.getByRole('button', { name: /^Sign as Head$/ })).toHaveCount(0)
    await page.getByLabel('Return for changes — reason').fill('Add a stretch target to the 5G KPI')
    await page.getByRole('button', { name: 'Return for changes' }).click()
    await expect(page.locator('.status-badge').filter({ hasText: 'Returned' }).first()).toBeVisible()
    await logout(page)

    // --- employee: sees why it came back, resubmits
    await login(page, 'employee')
    await page.goto('/my-performance')
    await settled(page)
    await expect(page.locator('.form-notice')).toContainText('Add a stretch target to the 5G KPI')
    await page.getByRole('button', { name: 'Submit to my Head' }).click()
    await expect(page.locator('.status-badge').first()).toContainText('Submitted')
    await logout(page)

    // --- Head: approve, then be refused the first signature
    await login(page, 'manager')
    await page.goto('/team-performance')
    await settled(page)
    await page.locator('table tbody tr', { hasText: 'Submitted to Head' }).first()
      .getByRole('button', { name: 'Open' }).click()
    await settled(page)
    await page.getByRole('button', { name: 'Approve — ready for signature' }).click()
    await expect(page.locator('.status-badge').filter({ hasText: 'awaiting employee signature' }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: /^Sign as Head$/ })).toHaveCount(0)
    await expect(page.locator('.form-notice')).toContainText('employee signs first')
    await logout(page)

    // --- employee signs (password re-authentication), then the Head signs
    await login(page, 'employee')
    await page.goto('/my-performance')
    await settled(page)
    await page.getByLabel('Confirm your password to sign').fill('employee123')
    await page.getByRole('button', { name: 'Sign as the individual' }).click()
    await expect(page.locator('.status-badge').first()).toContainText('awaiting Head signature')
    await expect(page.locator('table', { hasText: 'Signatory' })).toContainText('Individual')
    await logout(page)

    await login(page, 'manager')
    await page.goto('/team-performance')
    await settled(page)
    await page.locator('table tbody tr', { hasText: 'awaiting Head signature' }).first()
      .getByRole('button', { name: 'Open' }).click()
    await settled(page)
    await page.getByLabel('Confirm your password to sign').fill('manager123')
    await page.getByRole('button', { name: /^Sign as Head$/ }).click()
    await expect(page.locator('.status-badge').filter({ hasText: 'Agreed (contracted)' }).first()).toBeVisible()

    // --- the signed PDF exists, is a real PDF, and the trail is complete
    const link = page.getByRole('link', { name: /Download contracting PDF/ }).first()
    await expect(link).toBeVisible()
    const href = await link.getAttribute('href')
    const pdf = await page.request.get(href!)
    expect(pdf.status()).toBe(200)
    expect(pdf.headers()['content-type']).toContain('application/pdf')
    expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-')
  })

  test('HR receives the signed agreement but has no signing route', async ({ page }) => {
    await login(page, 'hradmin')
    const response = await page.request.get('/api/v1/performance-agreements/?status=agreed')
    expect(response.ok()).toBeTruthy()
    const agreements: { id: number; status: string; signatures: unknown[]; documents: { download_url: string }[] }[] =
      (await response.json()).results
    const signed = agreements.find((a) => a.status === 'agreed')
    expect(signed, 'the seed signs a few agreements for real').toBeTruthy()
    expect(signed!.signatures).toHaveLength(2)
    expect(signed!.documents.length).toBeGreaterThan(0)

    const pdf = await page.request.get(signed!.documents[0].download_url)
    expect(pdf.status()).toBe(200)
    expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-')

    // hr_admin may not sign on anyone's behalf
    const refused = await page.request.post(`/api/v1/performance-agreements/${signed!.id}/sign/`, {
      data: { role: 'head', password: 'hradmin123' },
      headers: { 'X-CSRFToken': (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? '' },
    })
    expect(refused.status()).toBeGreaterThanOrEqual(400)
  })

  test('a plain employee cannot reach the Head or HR performance pages', async ({ page }) => {
    await login(page, 'employee')
    await expect(page.getByRole('link', { name: 'Team Performance' })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Performance Periods' })).toHaveCount(0)
    await page.goto('/performance-periods')
    await page.waitForURL(/\/employees$/)
  })
})
