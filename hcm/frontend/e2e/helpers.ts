import { createHmac } from 'node:crypto'
import { expect, type Page } from '@playwright/test'

/** Demo logins from `seed_demo_data` — password is username + "123". */
export const USERS = {
  hradmin: 'hradmin',
  manager: 'manager',
  recruiter: 'recruiter',
  compmanager: 'compmanager',
  eemanager: 'eemanager',
  accountingofficer: 'accountingofficer',
  auditor: 'auditor',
  employee: 'employee',
} as const
export type DemoUser = keyof typeof USERS

export async function login(page: Page, user: DemoUser, expectedPath: string | RegExp = '/employees') {
  await page.goto('/login')
  await page.getByLabel('Username').fill(USERS[user])
  await page.getByLabel('Password').fill(`${USERS[user]}123`)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForURL(expectedPath)
}

export async function logout(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.waitForURL(/\/login$/)
}

/** RFC 6238 TOTP (SHA-1, 6 digits, 30 s) — used to drive the ADR-009 step-up
 * flow for real rather than stubbing it. Mirrors what an authenticator app does. */
export function totp(base32Secret: string, now = Date.now()): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = ''
  for (const ch of base32Secret.replace(/=+$/, '').toUpperCase()) {
    const val = alphabet.indexOf(ch)
    if (val < 0) continue
    bits += val.toString(2).padStart(5, '0')
  }
  const bytes = Buffer.alloc(Math.floor(bits.length / 8))
  for (let i = 0; i < bytes.length; i++) bytes[i] = parseInt(bits.slice(i * 8, i * 8 + 8), 2)
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(Math.floor(now / 1000 / 30)))
  const hmac = createHmac('sha1', bytes).update(counter).digest()
  const offset = hmac[hmac.length - 1] & 0x0f
  const code = ((hmac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).toString().padStart(6, '0')
  return code
}

/** Every page in the app renders exactly one <h1>; assert it. */
export async function expectHeading(page: Page, text: string | RegExp) {
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(text)
}

/** Waits until no "Loading…" placeholder is visible on the page. */
export async function settled(page: Page) {
  await expect(page.getByText('Loading…', { exact: true })).toHaveCount(0, { timeout: 15_000 })
}
