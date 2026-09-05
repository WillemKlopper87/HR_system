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
    // The seed already has several *other* people's agreements "Submitted to
    // Head" under the same manager, so every /team-performance lookup below
    // must be scoped to this employee's own row by name, never `.first()`.
    const employeeName = (
      await page.locator('.detail-field', { hasText: 'Employee' }).locator('dd').textContent()
    )?.trim()
    if (!employeeName) throw new Error('could not read the employee name off /my-performance')

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
    const row = page.locator('table tbody tr', { hasText: employeeName }).filter({ hasText: 'Submitted to Head' })
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
    await expect(page.locator('.form-notice').first()).toContainText('Add a stretch target to the 5G KPI')
    await page.getByRole('button', { name: 'Submit to my Head' }).click()
    await expect(page.locator('.status-badge').first()).toContainText('Submitted')
    await logout(page)

    // --- Head: approve, then be refused the first signature
    await login(page, 'manager')
    await page.goto('/team-performance')
    await settled(page)
    await page.locator('table tbody tr', { hasText: employeeName }).filter({ hasText: 'Submitted to Head' })
      .getByRole('button', { name: 'Open' }).click()
    await settled(page)
    await page.getByRole('button', { name: 'Approve — ready for signature' }).click()
    await expect(page.locator('.status-badge').filter({ hasText: 'awaiting employee signature' }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: /^Sign as Head$/ })).toHaveCount(0)
    await expect(page.locator('.form-notice').first()).toContainText('employee signs first')
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
    await page.locator('table tbody tr', { hasText: employeeName }).filter({ hasText: 'awaiting Head signature' })
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

/** PC-2: mid-year (Q2) and final (Q4) reviews. Deliberately in this same
 * file, after the PC-1 describe block above (not a separate spec file):
 * both use the same fixed `employee`/`manager` demo login, and HR opening
 * mid-year/final here is genuinely period-wide (PC-1's `open_phase`), so it
 * would advance the PC-1 test's agreement too if the two files' run order
 * ever inverted -- `workers: 1` + `fullyParallel: false` only guarantees
 * top-to-bottom order *within* a file, not a stable order *across* files.
 */
test.describe('performance reviews: mid-year and final (PC-2)', () => {
  test('a full year: contracting → mid-year → final, with evidence and a computed score', async ({ page }) => {
    // Nine login/logout cycles plus every intermediate page load and
    // settled() wait -- comfortably the longest single flow in the suite.
    // The default 45s budget is tight for that even on an idle machine;
    // give it real headroom rather than chasing a phantom app bug every
    // time a busy dev box makes one round trip land a few seconds slow.
    test.setTimeout(120_000)
    // --- get the seeded employee/head pair to AGREED as quickly as the UI allows
    await login(page, 'employee')
    await page.goto('/my-performance')
    await expectHeading(page, 'My Performance')
    await settled(page)
    const employeeName = (
      await page.locator('.detail-field', { hasText: 'Employee' }).locator('dd').textContent()
    )?.trim()
    if (!employeeName) throw new Error('could not read the employee name off /my-performance')
    if ((await page.locator('.status-badge').first().textContent())?.includes('Draft')) {
      await page.getByRole('button', { name: 'Submit to my Head' }).click()
      await expect(page.locator('.status-badge').first()).toContainText('Submitted')
    }
    await logout(page)

    await login(page, 'manager')
    await page.goto('/team-performance')
    await expectHeading(page, 'Team Performance')
    await settled(page)
    const teamRow = () =>
      page.locator('table tbody tr', { hasText: employeeName }).filter({ hasText: 'Submitted to Head' })
    if (await teamRow().count()) {
      await teamRow().getByRole('button', { name: 'Open' }).click()
      await settled(page)
      await page.getByRole('button', { name: 'Approve — ready for signature' }).click()
    }
    await logout(page)

    await login(page, 'employee')
    await page.goto('/my-performance')
    await expectHeading(page, 'My Performance')
    await settled(page)
    if (await page.getByRole('button', { name: 'Sign as the individual' }).count()) {
      await page.getByLabel('Confirm your password to sign').fill('employee123')
      await page.getByRole('button', { name: 'Sign as the individual' }).click()
    }
    await logout(page)

    await login(page, 'manager')
    await page.goto('/team-performance')
    await expectHeading(page, 'Team Performance')
    await settled(page)
    const signRow = () =>
      page.locator('table tbody tr', { hasText: employeeName }).filter({ hasText: 'awaiting Head signature' })
    if (await signRow().count()) {
      await signRow().getByRole('button', { name: 'Open' }).click()
      await settled(page)
      await page.getByLabel('Confirm your password to sign').fill('manager123')
      await page.getByRole('button', { name: /^Sign as Head$/ }).click()
      await expect(page.locator('.status-badge').filter({ hasText: 'Agreed' }).first()).toBeVisible()
    }
    await logout(page)

    // --- HR opens the mid-year phase for the whole period
    await login(page, 'hradmin')
    await page.goto('/performance-periods')
    await expectHeading(page, 'Performance Periods')
    await settled(page)
    await page.getByRole('button', { name: /Open mid-year review/i }).click()
    await expect(page.getByText(/Mid-year review open/i).first()).toBeVisible()
    await logout(page)

    // --- employee: the Q2 review section appears, fill in the target note + comment
    await login(page, 'employee')
    await page.goto('/my-performance')
    await expectHeading(page, 'My Performance')
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Mid-year review (Q2)' })).toBeVisible()
    const q2TargetNote = page.locator('textarea[aria-label="q2_target_note"]').first()
    await q2TargetNote.fill('On track for R1.5m, ahead of the R1m target')
    await q2TargetNote.blur()
    const q2EmployeeComment = page.locator('textarea[aria-label="q2_employee_comment"]').first()
    await q2EmployeeComment.fill('Pipeline is solid, two deals closing next month')
    await q2EmployeeComment.blur()
    await page.getByLabel('Confirm your password to sign').fill('employee123')
    await page.getByRole('button', { name: 'Sign as the individual' }).click()
    await expect(page.locator('.status-badge').first()).toContainText('employee signed')
    await logout(page)

    // --- Head: adds their own Q2 comment, then signs
    await login(page, 'manager')
    await page.goto('/team-performance')
    await expectHeading(page, 'Team Performance')
    await settled(page)
    await page.locator('table tbody tr', { hasText: employeeName }).filter({ hasText: 'Mid-year' })
      .getByRole('button', { name: 'Open' }).click()
    await settled(page)
    const q2HeadComment = page.locator('textarea[aria-label="q2_head_comment"]').first()
    await q2HeadComment.fill('Agreed — good progress, keep it up')
    await q2HeadComment.blur()
    await page.getByLabel('Confirm your password to sign').fill('manager123')
    await page.getByRole('button', { name: /^Sign as Head$/ }).click()
    await expect(page.locator('.status-badge').filter({ hasText: 'Mid-year review signed' }).first()).toBeVisible()
    await logout(page)

    // --- HR opens the final phase
    await login(page, 'hradmin')
    await page.goto('/performance-periods')
    await expectHeading(page, 'Performance Periods')
    await settled(page)
    await page.getByRole('button', { name: /Open final assessment/i }).click()
    await expect(page.getByText(/Final assessment open/i).first()).toBeVisible()
    await logout(page)

    // --- employee: rate every KPI, attach evidence (a link and a file), then try to sign
    await login(page, 'employee')
    await page.goto('/my-performance')
    await expectHeading(page, 'My Performance')
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Final assessment (Q4)' })).toBeVisible()
    const ratingSelects = page.locator('select[aria-label^="Rating for"]')
    const count = await ratingSelects.count()
    expect(count).toBeGreaterThan(0)
    // Rated below the attention threshold (default 3.00) on purpose — PC-3's
    // improvement-plan flow and rating-distribution dashboard need a genuine
    // hr_attention case to exercise, not a synthetic one built separately.
    for (let i = 0; i < count; i++) {
      await ratingSelects.nth(i).selectOption('2')
    }
    const commentBoxes = page.locator('textarea[aria-label="final_employee_comment"]')
    await commentBoxes.first().fill('Fell short of target this quarter')
    await commentBoxes.first().blur()

    // attach a link to the first KPI's evidence panel
    const firstEvidenceToggle = page.getByRole('button', { name: /No evidence attached|Evidence \(/ }).first()
    await firstEvidenceToggle.click()
    await page.getByPlaceholder('https://…').first().fill('https://sentech.sharepoint.com/sites/ri/Q4-evidence.xlsx')
    await page.getByPlaceholder('Description (optional)').first().fill('Q4 revenue tracking sheet')
    await page.getByRole('button', { name: 'Add' }).first().click()
    await expect(page.getByRole('button', { name: /Evidence \(1\)/ }).first()).toBeVisible()

    await page.getByLabel('Confirm your password to sign').fill('employee123')
    await page.getByRole('button', { name: 'Sign as the individual' }).click()
    await expect(page.locator('.status-badge').first()).toContainText('Final: employee signed')
    await logout(page)

    // --- Head signs off final — the score and any HR-attention flag appear
    await login(page, 'manager')
    await page.goto('/team-performance')
    await expectHeading(page, 'Team Performance')
    await settled(page)
    await page.locator('table tbody tr', { hasText: employeeName }).filter({ hasText: 'Final: employee signed' })
      .getByRole('button', { name: 'Open' }).click()
    await settled(page)
    await page.getByLabel('Confirm your password to sign').fill('manager123')
    await page.getByRole('button', { name: /^Sign as Head$/ }).click()
    await expect(page.locator('.status-badge').filter({ hasText: 'Final assessment signed' }).first()).toBeVisible()
    await expect(page.locator('.detail-field', { hasText: 'Final score' })).toContainText('2.00')
    await expect(page.getByText('Flagged for HR attention').first()).toBeVisible()

    // both the mid-year and the final signed PDFs are real, downloadable PDFs
    const pdfLinks = page.getByRole('link', { name: /Download (midyear|final) PDF/ })
    await expect(pdfLinks).toHaveCount(2)
    for (let i = 0; i < 2; i++) {
      const href = await pdfLinks.nth(i).getAttribute('href')
      const pdf = await page.request.get(href!)
      expect(pdf.status()).toBe(200)
      expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-')
    }
  })

  test('evidence uploaded via the UI is a real file, hashed and downloadable', async ({ page }) => {
    // Independently exercise the file-upload path (the flow test above only
    // covers the link path) against whichever agreement is already open for
    // final review from the previous test, read fresh via the API so this
    // test doesn't depend on run order.
    await login(page, 'hradmin')
    const response = await page.request.get('/api/v1/performance-agreements/?status=final_signed')
    const agreements = (await response.json()).results as { id: number; elements: { id: number }[] }[]
    expect(agreements.length).toBeGreaterThan(0)
    const elementId = agreements[0].elements[0].id

    const csrf = await page.request.get('/api/v1/auth/csrf/')
    const cookies = await page.context().cookies()
    const csrfToken = cookies.find((c) => c.name === 'csrftoken')?.value ?? ''
    expect(csrf.ok()).toBeTruthy()

    const upload = await page.request.post('/api/v1/agreement-evidence/', {
      multipart: {
        element: String(elementId),
        kind: 'file',
        description: 'Signed off attendance register',
        file: { name: 'evidence.txt', mimeType: 'text/plain', buffer: Buffer.from('Q4 evidence content') },
      },
      headers: { 'X-CSRFToken': csrfToken },
    })
    expect(upload.status()).toBe(201)
    const body = await upload.json()
    expect(body.sha256).toHaveLength(64)
    expect(body.added_after_signoff).toBe(true) // this agreement is already final_signed

    const download = await page.request.get(body.download_url)
    expect(download.status()).toBe(200)
    expect(await download.text()).toBe('Q4 evidence content')
  })
})

/** PC-3: improvement plans, period archive, and the new hr_admin/auditor
 * records page. Deliberately the third describe block in this same file,
 * after PC-1 and PC-2 above, for the same shared-demo-login/state-ordering
 * reason PC-2's comment explains -- it reuses the agreement PC-2's flow just
 * finished (final_signed, hr_attention=True since that flow rates every KPI
 * a 2, below the default 3.00 threshold) rather than building its own. */
test.describe('PC-3: improvement plans, archive, records', () => {
  test('an improvement plan is opened by the Head, its outcome updated, and read-only for the employee', async ({
    page,
  }) => {
    await login(page, 'manager')
    await page.goto('/team-performance')
    await expectHeading(page, 'Team Performance')
    await settled(page)
    const flaggedRow = page.locator('table tbody tr').filter({ hasText: 'Flagged' }).first()
    await expect(flaggedRow).toBeVisible()
    await flaggedRow.getByRole('button', { name: 'Open' }).click()
    await settled(page)

    await expect(page.getByRole('heading', { name: 'Improvement plan' })).toBeVisible()
    await expect(page.getByText('No improvement plan opened yet.')).toBeVisible()
    await page.getByRole('button', { name: '+ New plan' }).click()
    await page.getByLabel('Reasons').fill('Missed revenue target this quarter.')
    await page.getByLabel('Actions').fill('Weekly pipeline review with the Head; shadow a senior AE.')
    await page.getByLabel('Review date').fill('2026-10-01')
    await page.getByRole('button', { name: 'Open plan' }).click()
    await expect(page.getByText('Missed revenue target this quarter.')).toBeVisible()

    await page.getByRole('combobox', { name: 'Outcome', exact: true }).selectOption('resolved')
    await page.getByLabel('Outcome notes').fill('Back on target for two consecutive months.')
    await page.getByRole('button', { name: 'Save outcome' }).click()
    await expect(page.locator('.form-error')).toHaveCount(0)
    await logout(page)

    await login(page, 'employee')
    await page.goto('/my-performance')
    await expectHeading(page, 'My Performance')
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Improvement plan' })).toBeVisible()
    await expect(page.getByText(/Outcome:\s*Resolved/)).toBeVisible()
    // read-only: the employee it's about never gets the create/edit controls
    await expect(page.getByRole('button', { name: '+ New plan' })).toHaveCount(0)
    await expect(page.getByRole('combobox', { name: 'Outcome', exact: true })).toHaveCount(0)
  })

  test('hr_admin archives the period; the signed PDF and evidence manifest are visible to hr_admin and auditor', async ({
    page,
  }) => {
    await login(page, 'hradmin')
    await page.goto('/performance-periods')
    await expectHeading(page, 'Performance Periods')
    await settled(page)
    // .first(): a sanity check that the section renders at all, not tied to
    // a specific period -- the seeded 2025/26 calibration-demo period has
    // its own "Rating distribution" heading too, so an unscoped
    // toBeVisible() is a strict-mode violation once both periods are on
    // the page.
    await expect(page.getByRole('heading', { name: 'Rating distribution' }).first()).toBeVisible()

    page.on('dialog', (dialog) => dialog.accept())
    // Scoped to the specific period card being archived, not a page-wide
    // count: the seeded 2025/26 calibration-demo period is deliberately
    // left un-archived (see seed_demo_data.py) and has its own "Archive
    // period" button, so a global toHaveCount(0) never passes once it
    // exists alongside whichever period this test is actually archiving.
    // `.first()` (not a `has:`/`hasText:` filter) on purpose: PerformancePeriod
    // orders by -start_date, which archiving doesn't change, so the index
    // stays a stable reference to the SAME card before and after the
    // click -- a content filter keyed on "still has the button" or "still
    // has this status text" would stop matching this exact card the
    // moment the click succeeds and silently re-resolve to a different one.
    const periodCard = page.locator('.detail-card').first()
    await expect(periodCard.getByRole('button', { name: 'Archive period' })).toHaveCount(1)
    await periodCard.getByRole('button', { name: 'Archive period' }).click()
    await expect(periodCard.getByRole('button', { name: 'Archive period' })).toHaveCount(0)
    await logout(page)

    await login(page, 'hradmin')
    await page.goto('/performance-records')
    await expectHeading(page, 'Performance Records')
    await settled(page)
    const archivedRow = page.locator('table tbody tr').filter({ hasText: 'Archived' }).first()
    await expect(archivedRow).toBeVisible()
    await archivedRow.getByRole('button', { name: 'Open' }).click()
    await expect(page.getByRole('heading', { name: 'Signed documents' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Evidence manifest' })).toBeVisible()
    const pdfLinks = page.getByRole('link', { name: 'Download PDF' })
    expect(await pdfLinks.count()).toBeGreaterThan(0)
    const href = await pdfLinks.first().getAttribute('href')
    const pdf = await page.request.get(href!)
    expect(pdf.status()).toBe(200)
    expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-')
    await logout(page)

    // the auditor never had a way to reach performance data before PC-3 —
    // this is the first browser proof that the read-only pull actually works
    await login(page, 'auditor')
    await page.goto('/performance-records')
    await expectHeading(page, 'Performance Records')
    await settled(page)
    await expect(page.getByRole('link', { name: 'Performance Periods' })).toHaveCount(0)
    const auditorRow = page.locator('table tbody tr').filter({ hasText: 'Archived' }).first()
    await expect(auditorRow).toBeVisible()
    await auditorRow.getByRole('button', { name: 'Open' }).click()
    const auditorPdfLink = page.getByRole('link', { name: 'Download PDF' }).first()
    const auditorHref = await auditorPdfLink.getAttribute('href')
    const auditorPdf = await page.request.get(auditorHref!)
    expect(auditorPdf.status()).toBe(200)
    await page.goto('/performance-periods')
    await page.waitForURL(/\/employees$/)
  })
})
