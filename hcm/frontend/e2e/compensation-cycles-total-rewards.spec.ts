import { expect, test, type Page } from '@playwright/test'
import { expectHeading, login, settled, totp } from './helpers'

/** hradmin2 isn't in helpers.ts's USERS map: unlike every other demo
 * login, its seeded password is "hradmin123" (matching hradmin's own),
 * not the "<username>123" pattern every other account follows (see
 * seed_demo_data.py's own printed credentials line) -- login() would
 * compute the wrong password for it, so this account logs in directly
 * rather than being folded into the shared, pattern-assuming helper. */
async function loginAsSecondHrAdmin(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Username').fill('hradmin2')
  await page.getByLabel('Password').fill('hradmin123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForURL('/employees')
}

/** Completes ADR-009 step-up for whichever employee is currently logged
 * in, tolerating either state: a fresh account (no authenticator on
 * file yet -- enroll first) or one that's already enrolled but lacks an
 * active grant (skip straight to the challenge). The only account this
 * spec ever runs this against is hradmin2, which nothing else in the
 * suite touches, so "fresh" is the expected path here, but this stays
 * correct either way rather than assuming it. */
async function completePayrollStepUp(page: Page) {
  await page.goto('/pay-bands')
  // RequirePayrollStepUp renders "Checking access…" while its own
  // step-up-status fetch is in flight -- a bare .count() check on the
  // challenge heading immediately after goto() would race that fetch
  // and could see neither the challenge nor the granted page yet.
  await expect(page.getByText('Checking access…')).toHaveCount(0, { timeout: 10_000 })
  const challengeHeading = page.getByRole('heading', { name: 'Step-up authentication required' })
  await expect.poll(async () =>
    (await challengeHeading.count()) + (await page.getByRole('heading', { level: 1 }).count()),
  ).toBeGreaterThan(0)
  if ((await challengeHeading.count()) === 0) return
  // StepUpChallenge has its OWN nested "Loading…" while it fetches TOTP
  // enrollment status, independent of the check above -- wait for that
  // too, or neither EnrollForm nor StepUpForm has rendered yet.
  await settled(page)
  const enrollButton = page.getByRole('button', { name: 'Set up authenticator' })
  if ((await enrollButton.count()) > 0) {
    await page.getByLabel('Current password').fill('hradmin123')
    await enrollButton.click()
    const secret = await page.getByLabel('Manual entry key').inputValue()
    await page.getByLabel('6-digit code').fill(totp(secret))
    await page.getByRole('button', { name: 'Confirm and activate' }).click()
    await page.getByLabel('6-digit authenticator code').fill(totp(secret))
  } else {
    // Reachable only if this account's device was already enrolled by
    // some OTHER means (never true for hradmin2 today) -- there is no
    // recoverable secret to complete the challenge with in that case, so
    // fail loudly rather than getting stuck on a missing field.
    throw new Error('completePayrollStepUp: account already enrolled and no secret in scope.')
  }
  await page.getByLabel('Reason for access').selectOption('payroll_processing')
  await page.getByRole('button', { name: 'Verify and continue' }).click()
  await expectHeading(page, 'Pay Bands')
}

test.describe('C6: salary-review/bonus cycles + total-rewards statement', () => {
  test('comp cycles are role-gated but NOT step-up-gated, unlike pay bands/proposals', async ({ page }) => {
    await login(page, 'compmanager')
    await page.goto('/comp-cycles')
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Step-up authentication required' })).toHaveCount(0)
    await expectHeading(page, 'Compensation Cycles')

    await page.getByRole('button', { name: '+ New cycle' }).click()
    await page.getByLabel('Name').fill('E2E Gate Check Cycle')
    await page.getByLabel('Period start').fill('2026-04-01')
    await page.getByLabel('Period end').fill('2027-03-31')
    await page.getByLabel('Budget (ZAR)').fill('100000')
    await page.getByRole('button', { name: 'Create cycle' }).click()
    await settled(page)

    const row = page.locator('tr', { hasText: 'E2E Gate Check Cycle' })
    await expect(row).toBeVisible()
    await expect(row).toContainText('Draft')

    await row.getByRole('button', { name: 'Open' }).click()
    await settled(page)
    await expect(row).toContainText('Open')
  })

  // Uses hradmin2, not hradmin/compmanager: compensation.spec.ts's own
  // tests assume THOSE two accounts have never enrolled a TOTP device
  // ("comp_manager: pay bands are gated by a real TOTP enrol -> confirm
  // -> challenge flow", "hr_admin is challenged independently (no
  // cross-user grant leakage)") -- a StepUpGrant is time-boxed but tied
  // to the EMPLOYEE, not the browser session, so touching either account
  // here would leak state into those pre-existing tests within the same
  // shared seeded backend (playwright.config.ts: workers: 1). hradmin2 is
  // the only comp_manager/hr_admin demo account nothing else touches.
  // This also means the "a genuinely different admin can approve with an
  // override reason" happy path isn't re-exercised at the UI level here
  // (it would need a THIRD such account, which doesn't exist in the demo
  // data) -- it's already covered directly by
  // compensation.tests.CycleUtilizationTests and
  // compensation.test_api.CompCycleApiTests at the backend level; this
  // test's job is the self-approval block plus the NEW budget flag.
  test('a proposal that would push a cycle over budget is flagged, not blocked, and needs an override reason to approve', async ({ page }) => {
    // A little more work than the 45s default budget covers comfortably
    // on a loaded machine: a step-up enrollment round-trip, cycle setup,
    // two employee searches, and proposal approval checks.
    test.setTimeout(180_000)
    await loginAsSecondHrAdmin(page)

    await page.goto('/comp-cycles')
    await settled(page)
    await page.getByRole('button', { name: '+ New cycle' }).click()
    await page.getByLabel('Name').fill('E2E Budget Race Cycle')
    await page.getByLabel('Period start').fill('2026-04-01')
    await page.getByLabel('Period end').fill('2027-03-31')
    await page.getByLabel('Budget (ZAR)').fill('50000')
    await page.getByRole('button', { name: 'Create cycle' }).click()
    await settled(page)
    const cycleRow = page.locator('tr', { hasText: 'E2E Budget Race Cycle' })
    await cycleRow.getByRole('button', { name: 'Open' }).click()
    await settled(page)

    await completePayrollStepUp(page)

    // completePayrollStepUp navigated away from /comp-cycles to /pay-bands;
    // go back to find the cycle's proposal-count link again.
    await page.goto('/comp-cycles')
    await settled(page)
    await page.locator('tr', { hasText: 'E2E Budget Race Cycle' }).getByRole('link').click()
    await settled(page)
    // The heading suffix depends on the SAME parallel fetch that also
    // walks the full ~150-employee list (the slowest of the three) --
    // give it more room than the global 10s default rather than racing
    // it, matching this codebase's documented "large /employees list is
    // genuinely slow on this machine, not flaky" characterization.
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(
      /Compensation Proposals — E2E Budget Race Cycle/, { timeout: 30_000 },
    )

    // Two fixed, always-seeded, distinctively-named demo employees (the
    // contract-renewal fixtures) -- searched by name rather than picked
    // by raw index out of the full ~150-employee list, both for realism
    // (this is how the search box is meant to be used) and reliability
    // (selectOption against a filtered-to-one-match list, not a huge one).
    // First bonus (30000) fits comfortably inside the 50000 budget.
    await page.getByRole('button', { name: '+ New proposal' }).click()
    const newProposalForm = page.locator('form.inline-form')
    await newProposalForm.getByRole('combobox', { name: 'Employee' }).fill('Renewal')
    await newProposalForm.locator('.employee-search-results [role="option"]').first().click()
    await page.getByLabel('Type').selectOption('bonus')
    await page.getByLabel('Bonus amount (ZAR)').fill('30000')
    await page.getByLabel('Cycle (optional)').selectOption({ label: 'E2E Budget Race Cycle' })
    await page.getByRole('button', { name: 'Propose change' }).click()
    await settled(page)
    const firstRow = page.locator('tr', { hasText: 'Renewal Contractor' })
    // settled() only confirms "Loading…" is gone, not that the reloaded
    // proposals list (a THIRD parallel fetch alongside the slow
    // employees list) has actually committed to the DOM yet -- give the
    // row itself, not just its content, room to appear.
    await expect(firstRow).toBeVisible({ timeout: 20_000 })
    await expect(firstRow).not.toContainText('Over cycle budget')

    // Second bonus (30000): 30000 + 30000 = 60000 > 50000 -- flagged, not blocked.
    await page.getByRole('button', { name: '+ New proposal' }).click()
    await newProposalForm.getByRole('combobox', { name: 'Employee' }).fill('Lapse')
    await newProposalForm.locator('.employee-search-results [role="option"]').first().click()
    await page.getByLabel('Type').selectOption('bonus')
    await page.getByLabel('Bonus amount (ZAR)').fill('30000')
    await page.getByLabel('Cycle (optional)').selectOption({ label: 'E2E Budget Race Cycle' })
    await page.getByRole('button', { name: 'Propose change' }).click()
    await settled(page)
    const secondRow = page.locator('tr', { hasText: 'Lapse Contractor' })
    await expect(secondRow).toBeVisible({ timeout: 20_000 })
    await expect(secondRow).toContainText('Over cycle budget')

    // hradmin2 proposed both -- even supplying an override reason,
    // hradmin2 cannot approve its own proposal (segregation of duties, a
    // pre-existing rule, now exercised against the NEW
    // exceeds_cycle_budget flag rather than only requires_override as
    // before).
    await secondRow.getByRole('button', { name: 'Approve' }).click()
    await secondRow.getByLabel('Override reason').fill('Attempting self-approval.')
    await secondRow.getByRole('button', { name: 'Confirm approval' }).click()
    await expect(secondRow.locator('.form-error')).toBeVisible()
    await expect(secondRow).not.toContainText('Approved')
  })

  test('employee: My Total Rewards shows own salary/band/benefits/performance, never any comp proposal', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/my-total-rewards')
    await settled(page)
    await expectHeading(page, 'My Total Rewards')
    await expect(page.getByRole('heading', { name: 'Current salary' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Pay-band position' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Benefits' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Performance context' })).toBeVisible()
    // seed_demo_data gives every employee a RemunerationRecord scaled off
    // their pay band, so the salary section should render real figures,
    // not the "no record yet" empty state.
    await expect(page.getByText('No remuneration record is on file for you yet.')).toHaveCount(0)

    // The endpoint is unconditionally self-scoped server-side (design
    // spec §3.2) -- an id-shaped query param is simply ignored, never
    // read to redirect the answer to someone else, and no comp_proposal
    // shape ever appears in the payload at all.
    const me = await (await page.request.get('/api/v1/auth/me/')).json()
    const response = await page.request.get('/api/v1/my-total-rewards/?employee=1')
    const body = await response.json()
    expect(body.employee).toBe(me.employee_id)
    const serialized = JSON.stringify(body)
    expect(serialized).not.toContain('comp_proposal')
    expect(serialized).not.toContain('proposed_annual_salary')
  })

  test('a non-comp/hr role has no Comp Cycles nav item and gets 403 hitting the API directly', async ({ page }) => {
    await login(page, 'manager')
    await expect(page.getByRole('link', { name: 'Comp Cycles' })).toHaveCount(0)
    const response = await page.request.get('/api/v1/comp-cycles/')
    expect(response.status()).toBe(403)
    await page.goto('/comp-cycles')
    await page.waitForURL(/\/employees$/)
  })
})
