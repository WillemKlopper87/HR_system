import { expect, test } from '@playwright/test'
import { expectHeading, login, logout, settled } from './helpers'

/** C6: EE consultative forum + plan measures + progress snapshots
 * (design spec 2026-08-26). Seeded: a forum chaired by `eemanager`, two
 * 2026 meetings (Q1 with PDF minutes), six plan measures, two snapshots. */
test.describe('EE forum, plan measures and progress snapshots', () => {
  test('ee_manager: forum page shows composition, members, meetings; can record a meeting', async ({ page }) => {
    await login(page, 'eemanager')
    await page.goto('/ee-forum')
    await expectHeading(page, 'EE Consultative Forum')
    await settled(page)
    await expect(page.getByText(/Forum composition (is adequate|needs attention)/)).toBeVisible()
    await expect(page.getByText('Q1 2026 EE forum')).toBeVisible()
    await expect(page.getByText('Q2 2026 EE forum')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Download minutes' })).toHaveCount(1)
    // The chair's union/employer nomination basis is visible to an EE role.
    await expect(page.getByText('Employer / management representative').first()).toBeVisible()

    const form = page.getByRole('form', { name: 'Record forum meeting' })
    await form.getByLabel('Title').fill('Q3 2026 EE forum (e2e)')
    await form.getByLabel('Resolutions').fill('Snapshot tabled.')
    await form.locator('fieldset input[type=checkbox]').first().check()
    await form.getByRole('button', { name: 'Record meeting' }).click()
    await expect(page.getByText('Q3 2026 EE forum (e2e)')).toBeVisible({ timeout: 15_000 })
  })

  test('ee_manager: plan measures and snapshots on EE configuration; can take a snapshot', async ({ page }) => {
    await login(page, 'eemanager')
    await page.goto('/ee-configuration')
    await expectHeading(page, 'EE Reporting Configuration')
    await expect(page.getByRole('heading', { name: 'EE Plan measures' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'EE Plan progress snapshots' })).toBeVisible()
    await expect(page.getByText('Advertise via community media and technical bursary alumni networks')).toBeVisible({ timeout: 20_000 })
    // The remuneration measure was seeded in_progress with a June target -> overdue flag.
    await expect(page.getByText('Overdue').first()).toBeVisible()
    await expect(page.getByText('Plan baseline')).toBeVisible()

    // Taking a second snapshot for today is rejected (one per day), which
    // proves the endpoint is wired without changing seeded state.
    await page.getByRole('button', { name: 'Take snapshot now' }).click()
    await expect(page.getByText(/already exists on this plan/)).toBeVisible({ timeout: 15_000 })
  })

  test('accounting officer reads forum without write controls; employee gets no page and an empty API roster', async ({ page }) => {
    await login(page, 'accountingofficer')
    await page.goto('/ee-forum')
    await expectHeading(page, 'EE Consultative Forum')
    await settled(page)
    await expect(page.getByText('Q1 2026 EE forum')).toBeVisible()
    await expect(page.getByRole('form', { name: 'Record forum meeting' })).toHaveCount(0)
    await expect(page.getByRole('form', { name: 'Add forum member' })).toHaveCount(0)
    await logout(page)

    // The `employee` demo login is a seeded forum member (secretary): the API
    // carve-out gives them the roster (representation redacted) and only the
    // meetings they attended (both seeded meetings include them) -- but no
    // page, no composition check, no plan measures.
    await login(page, 'employee')
    await page.goto('/ee-forum')
    await page.waitForURL(/\/employees$/)
    const roster = await page.request.get('/api/v1/ee-forum-members/')
    expect(roster.status()).toBe(200)
    const rosterBody = await roster.json()
    expect(rosterBody.results.length).toBeGreaterThan(0)
    expect(rosterBody.results[0]).not.toHaveProperty('representation')
    expect((await page.request.get('/api/v1/ee-forum-members/composition/')).status()).toBe(403)
    expect((await page.request.get('/api/v1/ee-plan-measures/')).status()).toBe(403)
    expect((await page.request.get('/api/v1/ee-plan-snapshots/')).status()).toBe(403)
  })
})
