// hcm/frontend/e2e/performance-calibration-360.spec.ts
import { expect, test } from '@playwright/test'
import { expectHeading, login, logout, settled } from './helpers'

// seed_demo_data's calibration/360 slice (C6, design spec 2026-08-25-
// performance-calibration-360-design.md): a second, already-elapsed period
// (2025/26) with one agreement -- fin_head ("compmanager" login) under ceo
// ("accountingofficer" login) -- taken to FINAL_SIGNED, one "reviewed, no
// change" calibration outcome already recorded, and a 360 round open with
// self+manager responded and one approved peer (ops_head, "eemanager"
// login) left un-responded on purpose, so this spec can drive the
// remaining lifecycle for real rather than asserting a fully-finished
// fixture.
test.describe('Performance calibration/moderation + 360 feedback (C6)', () => {
  test('hr_admin sees the seeded calibration outcome and can close the session', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/calibration')
    await expectHeading(page, 'Calibration')
    await settled(page)

    await page.getByLabel('Period').selectOption({ label: '2025/26' })
    await settled(page)

    const sessionCard = page.locator('section.detail-card', { hasText: 'Org-wide' })
    await expect(sessionCard).toBeVisible()
    await expect(sessionCard).toContainText('Open')
    await expect(sessionCard).toContainText('Recorded outcomes')
    await expect(sessionCard).toContainText('No change')
    await expect(sessionCard).toContainText('Consistent with the rest of the organisation')

    await sessionCard.getByRole('button', { name: 'Close session' }).click()
    await settled(page)
    const closedCard = page.locator('section.detail-card', { hasText: 'Org-wide' })
    await expect(closedCard).toContainText('Completed')
    await expect(closedCard.getByRole('button', { name: 'Close session' })).toHaveCount(0)
  })

  test('an unrelated employee cannot reach calibration data at all', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/calibration')
    // RequireRole bounces a non-hr_admin straight back out.
    await page.waitForURL(/\/employees$/)

    const response = await page.request.get('/api/v1/calibration-sessions/')
    expect(response.status()).toBe(403)
  })

  test('360 visibility: the subject sees self+manager attributed but never an individual peer response; the Head sees everything', async ({ page }) => {
    // --- Subject's own view: calibration summary + 360 raters table -------
    await login(page, 'compmanager')
    await page.goto('/my-performance')
    await expectHeading(page, 'My Performance')
    await settled(page)

    // The 2026/27 agreement (the org-wide contracting round) sorts first;
    // open the seeded 2025/26 one specifically.
    await page.locator('tr', { hasText: '2025/26' }).getByRole('button', { name: 'Open' }).click()
    await settled(page)

    const card = page.locator('section.detail-card', { hasText: '2025/26 scorecard' })
    await expect(card).toBeVisible()

    // Calibration section: the recorded "no change" outcome is visible to
    // the subject, reason and all -- never hidden, even though it changed
    // nothing (design spec §2.4/§2.6).
    const calibrationSection = page.locator('section.detail-card', { has: page.getByRole('heading', { name: 'Calibration' }) })
    await expect(calibrationSection).toContainText('No change')
    await expect(calibrationSection).toContainText('Consistent with the rest of the organisation')

    // 360 section: three raters (self, manager, one approved peer).
    const feedbackSection = page.locator('section.detail-card', { has: page.getByRole('heading', { name: '360° feedback' }) })
    await expect(feedbackSection).toBeVisible()
    const rows = feedbackSection.locator('table.data-table tbody tr')
    await expect(rows).toHaveCount(3)

    // Self and manager rows are attributed in full to the subject -- no new
    // exposure, both are already visible elsewhere on this same scorecard.
    const selfRow = rows.filter({ hasText: 'Self' })
    await expect(selfRow).toContainText('Yes') // has_submitted
    await selfRow.getByText('View response').click()
    await expect(selfRow).toContainText('Delivers consistently')

    const managerRow = rows.filter({ hasText: 'Manager / Head' })
    await expect(managerRow).toContainText('Yes')
    await managerRow.getByText('View response').click()
    await expect(managerRow).toContainText('Excellent cross-functional partner')

    // The seeded peer hasn't responded yet -- not submitted, nothing to view.
    const peerRow = rows.filter({ hasText: 'Peer' })
    await expect(peerRow).toContainText('No') // has_submitted
    await expect(peerRow.getByText('View response')).toHaveCount(0)

    // Peer feedback isn't aggregated yet (need >=3 responses).
    await expect(feedbackSection).toContainText("isn't summarised yet")

    // Nominate a second peer while here -- exercises the nomination UI path
    // the Head approves below. The dropdown already excludes the subject
    // and every existing rater (self/manager/the seeded peer), so picking
    // the first real option is safe without hardcoding a name the RNG-seeded
    // bulk-hire could vary.
    await feedbackSection.getByRole('button', { name: '+ Nominate a rater' }).click()
    const nominateSelect = feedbackSection.getByLabel('Nominate')
    const firstRealOption = await nominateSelect.locator('option').nth(1).textContent()
    await nominateSelect.selectOption({ label: firstRealOption ?? '' })
    await feedbackSection.getByRole('button', { name: 'Nominate' }).click()
    await settled(page)
    await expect(feedbackSection.locator('table.data-table tbody tr')).toHaveCount(4)

    await logout(page)

    // --- The pending peer (ops_head / "eemanager") responds ---------------
    await login(page, 'eemanager')
    await page.goto('/my-feedback-requests')
    await expectHeading(page, 'My 360° Feedback Requests')
    await settled(page)
    const raterCard = page.locator('.detail-card', { hasText: 'Peer' })
    await expect(raterCard).toBeVisible()
    await raterCard.getByLabel('Collaboration (1-5)').fill('5')
    await raterCard.getByLabel('Communication (1-5)').fill('4')
    await raterCard.getByLabel('Reliability (1-5)').fill('5')
    await raterCard.getByLabel('Strengths').fill('Always steps in when Finance needs an OPS read on a plan.')
    await raterCard.getByRole('button', { name: 'Submit response' }).click()
    await settled(page)
    await logout(page)

    // --- Subject reloads: submitted, but STILL never individually shown ---
    await login(page, 'compmanager')
    await page.goto('/my-performance')
    await settled(page)
    await page.locator('tr', { hasText: '2025/26' }).getByRole('button', { name: 'Open' }).click()
    await settled(page)
    const feedbackSection2 = page.locator('section.detail-card', { has: page.getByRole('heading', { name: '360° feedback' }) })
    const peerRowAfter = feedbackSection2.locator('table.data-table tbody tr').filter({ hasText: 'Peer' }).first()
    await expect(peerRowAfter).toContainText('Yes') // now submitted
    await expect(peerRowAfter.getByText('View response')).toHaveCount(0) // still masked, permanently
    await expect(feedbackSection2).not.toContainText('Always steps in when Finance needs')
    // Still only 1 of the 2 needed extra peer responses -- aggregate floor
    // (>=3) genuinely not met yet.
    await expect(feedbackSection2).toContainText("isn't summarised yet")
    await logout(page)

    // --- The Head sees everything, fully attributed ------------------------
    await login(page, 'accountingofficer')
    await page.goto('/team-performance')
    await expectHeading(page, 'Team Performance')
    await settled(page)
    await page.locator('tr', { hasText: '2025/26' }).getByRole('button', { name: 'Open' }).click()
    await settled(page)
    const headFeedbackSection = page.locator('section.detail-card', { has: page.getByRole('heading', { name: '360° feedback' }) })
    await expect(headFeedbackSection).toBeVisible()
    const headPeerRow = headFeedbackSection.locator('table.data-table tbody tr').filter({ hasText: 'Peer' }).first()
    await headPeerRow.getByText('View response').click()
    await expect(headPeerRow).toContainText('Always steps in when Finance needs an OPS read on a plan.')

    // The Head also approves the newly nominated second peer.
    const pendingRow = headFeedbackSection.locator('table.data-table tbody tr').filter({ hasText: 'Pending approval' })
    await expect(pendingRow).toHaveCount(1)
    await pendingRow.getByRole('button', { name: 'Approve' }).click()
    await settled(page)
    await expect(headFeedbackSection).not.toContainText('Pending approval')
  })
})
