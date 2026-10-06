/**
 * S152 walkthrough @theme_checkout — a guest buys a subscription plan on the themed
 * `/checkout`: the email step finds an existing account, the buyer signs in inline,
 * fills billing, applies and clears a coupon, picks invoice, accepts the terms and
 * confirms; `/checkout/confirmation` shows the invoice region. Then the themed
 * `/pay/stripe` page: auth-required (anonymous → `/login`), it renders for the buyer
 * without completing Stripe.
 *
 * Seeds (admin API, removed afterwards): a plan, a 25 % coupon and a fresh buyer
 * (force-deleted with the invoice and subscription it bought).
 */
import { test, expect, type Page } from '@playwright/test';
import { uniqueSlug } from '@fe-user-e2e/frontend-mode/frontend-mode-support';
import {
  AdminSeeder,
  CONFIRMATION_URL_PATTERN,
  WalkthroughSteps,
  invoiceIdFromConfirmationUrl,
  seedPercentageCoupon,
  seedTariffPlan,
  skipUnlessThemeMode,
  type WalkthroughBuyer,
} from '../../../theme/tests/e2e/support/walkthrough-support';

const PLAN_PRICE = 40;
const COUPON_PERCENT = 25;

async function amountOf(page: Page, testId: string): Promise<number> {
  const text = (await page.locator(`[data-testid="${testId}"]`).first().textContent()) ?? '';
  const match = text.replace(/,/g, '').match(/\d+(\.\d+)?/);
  return match ? Number(match[0]) : Number.NaN;
}

async function fillBillingAddress(page: Page): Promise<void> {
  await page.fill('[data-testid="billing-first-name"]', 'Walk');
  await page.fill('[data-testid="billing-last-name"]', 'Through');
  await page.fill('[data-testid="billing-street"]', '1 Theme Street');
  await page.fill('[data-testid="billing-city"]', 'Berlin');
  await page.fill('[data-testid="billing-zip"]', '10115');
  await page.locator('[data-testid="billing-country"]').selectOption({ index: 1 });
}

test.describe('Walkthrough @theme_checkout — guest email, inline login, coupon, invoice, confirmation, /pay/stripe', () => {
  skipUnlessThemeMode(test);

  const steps = new WalkthroughSteps('theme_checkout');
  const planName = uniqueSlug('Walkthrough Plan');
  let seeder: AdminSeeder;
  let plan: Record<string, any>;
  let couponCode: string;
  let buyer: WalkthroughBuyer;

  test.beforeAll(async () => {
    seeder = await AdminSeeder.open();
    plan = await seedTariffPlan(seeder, planName, PLAN_PRICE);
    couponCode = await seedPercentageCoupon(seeder, COUPON_PERCENT);
    buyer = await seeder.freshBuyer();
  });

  test.afterAll(async () => {
    await seeder?.cleanup();
  });

  test('a guest signs in inside checkout and pays a plan by invoice @theme_checkout', async ({ page }) => {
    await page.goto('/pay/stripe');
    await page.waitForURL(/\/login\?redirect=%2Fpay%2Fstripe/);
    await steps.themed(page, '01-pay-requires-login');

    await page.goto(`/checkout?tarif_plan_id=${plan.slug}`);
    await expect(page.locator('[data-testid="checkout-title"]')).toBeVisible();
    await expect(page.locator('[data-testid="order-summary"]')).toContainText(planName);
    await expect(page.locator('[data-testid="email-block"]')).toBeVisible();
    await steps.themed(page, '02-guest-checkout');

    await page.fill('[data-testid="email-input"]', buyer.email);
    await expect(page.locator('[data-testid="email-existing-user"]')).toBeVisible();
    await page.fill('[data-testid="email-existing-user"] [data-testid="password-input"]', buyer.password);
    await steps.themed(page, '03-existing-account-found');
    await page.click('[data-testid="email-existing-user"] [data-testid="login-button"]');
    await expect(page.locator('[data-testid="logged-in-email"]')).toContainText(buyer.email);
    await steps.themed(page, '04-signed-in-inline');

    await fillBillingAddress(page);
    const totalBeforeCoupon = await amountOf(page, 'order-total-amount');
    expect(totalBeforeCoupon).toBeGreaterThan(0);
    await page.fill('[data-testid="coupon-input"]', couponCode);
    await page.click('[data-testid="coupon-apply"]');
    await expect(page.locator('[data-testid="coupon-applied"]')).toContainText(couponCode);
    await expect(page.locator('[data-testid="order-discount"]')).toBeVisible();
    expect(await amountOf(page, 'order-total-amount')).toBeCloseTo(totalBeforeCoupon * (1 - COUPON_PERCENT / 100), 1);
    await expect(page.locator('[data-testid="billing-street"]')).toHaveValue('1 Theme Street');
    await steps.themed(page, '05-coupon-applied');

    await page.click('[data-testid="coupon-clear"]');
    await expect(page.locator('[data-testid="coupon-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="order-discount"]')).toHaveCount(0);
    expect(await amountOf(page, 'order-total-amount')).toBeCloseTo(totalBeforeCoupon, 2);

    await page.locator('[data-testid="payment-method-invoice"]').click();
    await page.locator('[data-testid="terms-checkbox"] input[type="checkbox"]').check();
    await expect(page.locator('[data-testid="confirm-checkout"]')).toBeEnabled();
    await steps.themed(page, '06-ready-to-confirm');
    await page.click('[data-testid="confirm-checkout"]');

    await page.waitForURL(CONFIRMATION_URL_PATTERN);
    const invoiceId = invoiceIdFromConfirmationUrl(page.url());
    await expect(page.locator('[data-testid="confirmation-banner"]')).toBeVisible();
    await expect(page.locator('[data-testid="invoice-details"]')).toBeVisible();
    await expect(page.locator('[data-testid="line-item-row"]').first()).toContainText(planName);
    await steps.themed(page, '07-confirmation-invoice');

    await page.goto(`/pay/stripe?invoice=${invoiceId}`);
    await expect(page.locator('body')).toHaveAttribute('data-auth', 'user');
    await expect(page.locator('.stripe-payment')).toBeVisible();
    await steps.themed(page, '08-pay-stripe-renders');
  });
});
