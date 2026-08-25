// hcm/frontend/e2e/recruitment-interviews.spec.ts
import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

// seed_demo_data's recruitment slice (C6): Werner Botha is at the
// 'interview' stage on the Backend Engineer requisition, with one
// InterviewSession (round 1, interviewers = [eng_head ("manager" login),
// ops_head ("eemanager" login)]) and exactly ONE submitted scorecard
// (eng_head's) -- a real, pre-seeded blind-review example. Aisha Cassim
// (Financial Analyst, 'offer' stage) has a cleared background check.
test.describe('Interview scheduling and panel scorecards (C6)', () => {
  test('hr_admin sees the seeded session, its scorecard aggregate, and the background check', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/applicants')
    await expectHeading(page, 'Applicants')
    await settled(page)
    await page.locator('tr', { hasText: 'Werner Botha' }).getByRole('link').first().click()
    await page.waitForURL(/\/applicants\/\d+$/)
    await settled(page)

    await expect(page.getByRole('heading', { name: 'Interviews' })).toBeVisible()
    // div.detail-card, not the plain .detail-card class selector -- the
    // wrapping <section> around "Interviews" also carries that class, so an
    // untagged selector matches both the section and the inner session card.
    const sessionCard = page.locator('div.detail-card', { hasText: 'Round 1' })
    await expect(sessionCard).toBeVisible()
    await expect(sessionCard).toContainText('Boardroom 2')

    await sessionCard.getByRole('button', { name: /Show scorecards/ }).click()
    await expect(sessionCard).toContainText('1 of 2 submitted')
    await expect(sessionCard).toContainText('avg skill rating: 4.0')
    await expect(sessionCard.locator('table')).toContainText('Hire')

    // Background checks section (Werner has an in-progress reference check).
    const bgSection = page.locator('section', { has: page.getByRole('heading', { name: 'Background checks' }) })
    await expect(bgSection).toContainText('Reference check')
    await expect(bgSection.locator('select')).toHaveValue('in_progress')
  })

  test('the first interviewer sees their own already-submitted scorecard; the second sees it masked until they submit', async ({ page }) => {
    // eng_head's login ("manager") already has a submitted scorecard.
    await login(page, 'manager')
    await page.goto('/my-interviews')
    await expectHeading(page, 'My Interviews')
    await settled(page)
    const card = page.locator('.detail-card', { hasText: 'Werner Botha' })
    await expect(card).toBeVisible()
    // Pre-filled with the existing values, and the button reflects "update".
    await expect(card.getByRole('button', { name: 'Update scorecard' })).toBeVisible()
    await expect(card.getByLabel('Skill (1-5)')).toHaveValue('4')
    // ops_head hasn't submitted anything at all yet -- no peer row exists
    // to even show as masked.
    await expect(card.getByRole('heading', { name: 'Fellow panelists' })).toHaveCount(0)
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    // ops_head's login ("eemanager") hasn't submitted yet -- sees eng_head's
    // row masked, submits their own, and the peer row unmasks.
    await login(page, 'eemanager')
    await page.goto('/my-interviews')
    await settled(page)
    const opsCard = page.locator('.detail-card', { hasText: 'Werner Botha' })
    await expect(opsCard).toBeVisible()
    await expect(opsCard.getByRole('button', { name: 'Submit scorecard' })).toBeVisible()
    await expect(opsCard.getByRole('heading', { name: 'Fellow panelists' })).toBeVisible()
    await expect(opsCard).toContainText('not visible until you submit yours')
    await expect(opsCard).not.toContainText('Strong technical fundamentals')

    await opsCard.getByLabel('Skill (1-5)').fill('3')
    await opsCard.getByLabel('Communication (1-5)').fill('4')
    await opsCard.getByLabel('Culture fit (1-5)').fill('3')
    await opsCard.getByLabel('Recommendation').selectOption('hire')
    await opsCard.getByLabel('Comments').fill('Solid, would work well with the team.')
    await opsCard.getByRole('button', { name: 'Submit scorecard' }).click()
    await settled(page)

    const refreshedCard = page.locator('.detail-card', { hasText: 'Werner Botha' })
    await expect(refreshedCard.getByRole('button', { name: 'Update scorecard' })).toBeVisible()
    // eng_head's peer row is now unmasked.
    await expect(refreshedCard).toContainText('skill 4, communication 5, culture fit 4')
  })

  test('an employee with no panel assignment sees an empty My Interviews page and 403s the background-check API directly', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/my-interviews')
    await expectHeading(page, 'My Interviews')
    await settled(page)
    await expect(page.getByText('No interviews assigned to you right now.')).toBeVisible()

    const response = await page.request.get('/api/v1/background-checks/')
    expect(response.status()).toBe(403)
  })
})
