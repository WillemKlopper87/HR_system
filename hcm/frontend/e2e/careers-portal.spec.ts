// hcm/frontend/e2e/careers-portal.spec.ts
import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

test.describe('External careers portal (C6)', () => {
  test('anonymous listing only shows open, externally-posted requisitions', async ({ page }) => {
    // No login anywhere in this test -- a genuinely anonymous browser
    // session, same as a real applicant would have.
    await page.goto('/careers')
    await expectHeading(page, 'Careers')
    await settled(page)
    await expect(page.getByRole('link', { name: /Backend Engineer/ })).toBeVisible()
    // Financial Analyst is open but NOT external_posting -- must never
    // appear on the public list even though it's a real, open requisition.
    await expect(page.getByRole('link', { name: /Financial Analyst/ })).toHaveCount(0)
  })

  test('a duplicate application for the same posting is a clean in-form error, not a crash', async ({ page }) => {
    await page.goto('/careers')
    await settled(page)
    await page.getByRole('link', { name: /Backend Engineer/ }).click()
    await page.waitForURL(/\/careers\/\d+$/)
    await settled(page)

    const email = `e2e.dup.${Date.now()}@example.com`
    async function fillAndSubmit() {
      await page.getByLabel('First name').fill('Dup')
      await page.getByLabel('Last name').fill('Licate')
      await page.getByLabel('Email').fill(email)
      await page.getByLabel('Date of birth').fill('1994-01-01')
      await page.locator('input[type="file"]').setInputFiles({
        name: 'cv.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.7\ndemo cv'),
      })
      await page.getByRole('button', { name: 'Submit application' }).click()
    }

    await fillAndSubmit()
    await expect(page.getByText('Thank you — your application has been received.')).toBeVisible()

    // Same posting, same email again.
    await page.goto(page.url())
    await settled(page)
    await fillAndSubmit()
    await expect(page.locator('.form-error')).toBeVisible()
    await expect(page.getByText('Thank you — your application has been received.')).toHaveCount(0)
  })

  test('a portal application reaches hire: stage advance, interview scheduling, a real interviewer scoring, offer, hire', async ({ page }) => {
    // Learn the auditor login's own employee id up front (same trick
    // succession.spec.ts uses) -- needed to select them, by value, in the
    // interviewer picker later, since most of the 150+ seeded employees
    // have no login account to score with afterward.
    await login(page, 'auditor')
    const me = await (await page.request.get('/api/v1/auth/me/')).json()
    const auditorId = String(me.employee_id)
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    // Anonymous application.
    const email = `e2e.hire.${Date.now()}@example.com`
    await page.goto('/careers')
    await settled(page)
    await page.getByRole('link', { name: /Backend Engineer/ }).click()
    await page.waitForURL(/\/careers\/\d+$/)
    await settled(page)
    await page.getByLabel('First name').fill('Portal')
    await page.getByLabel('Last name').fill('Hopeful')
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Phone').fill('0829998888')
    await page.getByLabel('Date of birth').fill('1996-06-06')
    await page.locator('input[type="file"]').setInputFiles({
      name: 'cv.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.7\ndemo cv for hire flow'),
    })
    await page.getByRole('button', { name: 'Submit application' }).click()
    await expect(page.getByText('Thank you — your application has been received.')).toBeVisible()

    // hr_admin: find the portal-sourced applicant, verify provenance, and
    // walk it applied -> screened -> interview, then schedule a session.
    await login(page, 'hradmin')
    await page.goto('/applicants')
    await settled(page)
    const row = page.locator('tr', { hasText: email })
    await expect(row).toBeVisible()
    await expect(row).toContainText('Careers site')
    await row.getByRole('link').first().click()
    await page.waitForURL(/\/applicants\/\d+$/)
    await settled(page)

    await page.getByRole('button', { name: 'Move to Screened' }).click()
    await settled(page)
    await page.getByRole('button', { name: 'Move to Interview' }).click()
    await settled(page)

    await page.getByRole('button', { name: '+ Schedule interview' }).click()
    await page.getByLabel('Date & time').fill('2026-09-15T10:00')
    await page.getByLabel('Location / video link').fill('Video call: https://meet.example.com/e2e')
    await page.getByLabel('Interviewers (panel)').selectOption(auditorId)
    await page.getByRole('button', { name: 'Schedule interview', exact: true }).click()
    await settled(page)
    await expect(page.locator('div.detail-card', { hasText: 'Round 1' })).toBeVisible()
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    // The auditor, as the assigned interviewer, scores the candidate.
    await login(page, 'auditor')
    await page.goto('/my-interviews')
    await settled(page)
    const interviewCard = page.locator('.detail-card', { hasText: 'Portal Hopeful' })
    await expect(interviewCard).toBeVisible()
    await interviewCard.getByLabel('Skill (1-5)').fill('5')
    await interviewCard.getByLabel('Communication (1-5)').fill('4')
    await interviewCard.getByLabel('Culture fit (1-5)').fill('5')
    await interviewCard.getByLabel('Recommendation').selectOption('strong_hire')
    await interviewCard.getByLabel('Comments').fill('Excellent candidate, hire quickly.')
    await interviewCard.getByRole('button', { name: 'Submit scorecard' }).click()
    await settled(page)
    await expect(interviewCard.getByRole('button', { name: 'Update scorecard' })).toBeVisible()
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    // hr_admin: see the scorecard, advance to offer, propose it.
    await login(page, 'hradmin')
    await page.goto('/applicants')
    await settled(page)
    await page.locator('tr', { hasText: email }).getByRole('link').first().click()
    await page.waitForURL(/\/applicants\/\d+$/)
    await settled(page)
    const sessionCard = page.locator('div.detail-card', { hasText: 'Round 1' })
    await sessionCard.getByRole('button', { name: /Show scorecards/ }).click()
    await expect(sessionCard).toContainText('Strong hire')

    await page.getByRole('button', { name: 'Move to Offer' }).click()
    await settled(page)
    await page.getByLabel('Job grade').selectOption({ index: 1 })
    await page.getByLabel('Proposed annual salary (ZAR)').fill('450000')
    await page.getByRole('button', { name: 'Propose offer' }).click()
    await settled(page)
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    // recruiter approves + accepts (segregation of duties: hr_admin proposed it).
    await login(page, 'recruiter')
    await page.goto('/applicants')
    await settled(page)
    await page.locator('tr', { hasText: email }).getByRole('link').first().click()
    await page.waitForURL(/\/applicants\/\d+$/)
    await settled(page)
    await page.getByRole('button', { name: 'Approve' }).click()
    await settled(page)
    await page.getByRole('button', { name: 'Accept' }).click()
    await settled(page)
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    // hr_admin completes the hire -- same real Applicant/hire machinery
    // every internally-sourced applicant goes through (design spec §2.5).
    await login(page, 'hradmin')
    await page.goto('/applicants')
    await settled(page)
    await page.locator('tr', { hasText: email }).getByRole('link').first().click()
    await page.waitForURL(/\/applicants\/\d+$/)
    await settled(page)
    await page.getByRole('button', { name: 'Move to Hired' }).click()
    await settled(page)
    await expect(page.getByText('Hired — see', { exact: false })).toBeVisible()
    await expect(page.getByRole('link', { name: 'the employee record' })).toBeVisible()
  })
})
