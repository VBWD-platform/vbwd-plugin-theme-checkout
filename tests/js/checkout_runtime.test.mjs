// S152-07 B — the checkout island's client-only rules (run with node --test).
// DRIFT NOTE — mirrored from:
//   passwordStrength / canRegister / mismatch — vue/src/components/checkout/EmailBlock.vue
//   missingRequirements / canCheckout          — plugins/checkout/PublicCheckoutView.vue
//   addCoreCartItem                            — vbwd-fe-core/src/stores/cart.ts addItem
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const RUNTIME_PATH = fileURLToPath(
  new URL('../../theme_checkout/templates/checkout/partials/checkout_runtime.js', import.meta.url),
);

function loadRuntime({ cart = [] } = {}) {
  const listeners = {};
  const writes = [];
  const assigned = [];
  const context = {
    document: {
      addEventListener: (type, listener) => (listeners[type] = listeners[type] || []).push(listener),
    },
    location: { assign: (target) => assigned.push(target) },
    VbwdTheme: {
      readCart: () => JSON.parse(JSON.stringify(cart)),
      writeCart: (storage, document, key, items) => writes.push({ key, items }),
    },
    localStorage: {},
    JSON,
  };
  context.window = context;
  vm.createContext(context);
  const source = readFileSync(RUNTIME_PATH, 'utf8');
  vm.runInContext(source, context);
  vm.runInContext(source, context); // included once per widget: must install once
  return { VbwdCheckout: context.VbwdCheckout, listeners, writes, assigned };
}

const plain = (value) => JSON.parse(JSON.stringify(value));

test('installs once even when the partial is included several times', () => {
  const { listeners } = loadRuntime();

  assert.equal(listeners.click.length, 1);
  assert.equal(listeners.input.length, 1);
});

for (const [password, expected] of [
  ['short1!', 'weak'],
  ['onlyletters', 'weak'],
  ['12345678', 'weak'],
  ['letters123', 'medium'],
  ['letters123!', 'medium'],
  ['Letters1234!', 'strong'],
]) {
  test(`password strength of "${password}" is ${expected}`, () => {
    const { VbwdCheckout } = loadRuntime();

    assert.equal(VbwdCheckout.passwordStrength(password), expected);
  });
}

test('sign-up needs 8+ chars, a non-weak password and a matching confirmation', () => {
  const { VbwdCheckout } = loadRuntime();

  assert.deepEqual(plain(VbwdCheckout.registrationState('letters123', 'letters123')), {
    strength: 'medium',
    mismatch: false,
    canRegister: true,
  });
  assert.deepEqual(plain(VbwdCheckout.registrationState('letters123', 'letters12')), {
    strength: 'medium',
    mismatch: true,
    canRegister: false,
  });
  assert.deepEqual(plain(VbwdCheckout.registrationState('weakweak', '')), {
    strength: 'weak',
    mismatch: false,
    canRegister: false,
  });
});

test('requirements follow missingRequirements and canCheckout', () => {
  const { VbwdCheckout } = loadRuntime();
  const complete = {
    authenticated: true,
    payable: true,
    payZero: false,
    billingComplete: true,
    paymentSelected: true,
    termsAccepted: true,
  };

  assert.deepEqual(plain(VbwdCheckout.missingRequirements(complete)), []);
  assert.deepEqual(
    plain(
      VbwdCheckout.missingRequirements({
        ...complete,
        authenticated: false,
        billingComplete: false,
        paymentSelected: false,
        termsAccepted: false,
      }),
    ),
    ['signIn', 'billingAddress', 'paymentMethod', 'acceptTerms'],
  );
  assert.deepEqual(
    plain(
      VbwdCheckout.missingRequirements({
        ...complete,
        payable: false,
        payZero: true,
        billingComplete: false,
        paymentSelected: false,
      }),
    ),
    [],
  );
});

test('adding a core cart item increments a matching id+type, else appends with quantity 1', () => {
  const { VbwdCheckout } = loadRuntime();
  const existing = [{ type: 'TOKEN_BUNDLE', id: 'b-1', name: 'B', price: 5, quantity: 1 }];

  assert.deepEqual(
    plain(VbwdCheckout.addCoreCartItem(existing, { type: 'TOKEN_BUNDLE', id: 'b-1', name: 'B', price: 5 })),
    [{ type: 'TOKEN_BUNDLE', id: 'b-1', name: 'B', price: 5, quantity: 2 }],
  );
  assert.deepEqual(
    plain(VbwdCheckout.addCoreCartItem(existing, { type: 'PLAN', id: 'b-1', name: 'P', price: 9 })),
    [existing[0], { type: 'PLAN', id: 'b-1', name: 'P', price: 9, quantity: 1 }],
  );
});

test('an add-to-cart click stores the item in vbwd_cart and goes to the checkout', () => {
  const { listeners, writes, assigned } = loadRuntime({ cart: [] });
  const item = { type: 'TOKEN_BUNDLE', id: 'b-9', name: '1,000 Tokens', price: 10, metadata: {} };
  const button = {
    getAttribute: (name) =>
      ({ 'data-vbwd-cart-add': JSON.stringify(item), 'data-vbwd-navigate': '/checkout?source=subscription' })[name] ?? null,
  };
  const target = { closest: (selector) => (selector === '[data-vbwd-cart-add]' ? button : null) };

  listeners.click[0]({ target, preventDefault() {} });

  assert.deepEqual(plain(writes), [{ key: 'vbwd_cart', items: [{ ...item, quantity: 1 }] }]);
  assert.deepEqual(assigned, ['/checkout?source=subscription']);
});

// S152-08 — a successful submit ends with HX-Redirect; like the SPA sources'
// submit (`cart.clearCart()`), the island's cart is emptied before htmx navigates.
function submitResponse({ redirect, cartKey }) {
  const holder = cartKey
    ? { getAttribute: (name) => (name === 'data-vbwd-cart' ? cartKey : null) }
    : null;
  return {
    detail: {
      elt: { closest: (selector) => (selector === '[data-vbwd-cart]' ? holder : null) },
      xhr: { getResponseHeader: (name) => (name === 'HX-Redirect' ? redirect : null) },
    },
  };
}

test('a redirecting submit empties the cart of the island it came from', () => {
  const { listeners, writes } = loadRuntime();

  listeners['htmx:beforeOnLoad'][0](
    submitResponse({ redirect: '/checkout/confirmation?invoice_id=i-1', cartKey: 'vbwd_shop_cart' }),
  );

  assert.deepEqual(plain(writes), [{ key: 'vbwd_shop_cart', items: [] }]);
});

test('a response without HX-Redirect (an error) keeps the cart', () => {
  const { listeners, writes } = loadRuntime();

  listeners['htmx:beforeOnLoad'][0](submitResponse({ redirect: null, cartKey: 'vbwd_cart' }));

  assert.deepEqual(writes, []);
});

test('a redirect from an island without a cart (dataset) clears nothing', () => {
  const { listeners, writes } = loadRuntime();

  listeners['htmx:beforeOnLoad'][0](submitResponse({ redirect: '/pay/stripe?invoice=i-1', cartKey: null }));

  assert.deepEqual(writes, []);
});
