/*
 * checkout_runtime.js — the client-only rules of the themed checkout (S152-07), ES2019,
 * inlined by the checkout page and the checkout CMS widgets (installs once).
 *   - requirements + the confirm button: PublicCheckoutView missingRequirements / canCheckout;
 *   - sign-up / login enabling and the password strength: EmailBlock;
 *   - the terms popup, payment-method selection and its instructions;
 *   - the coupon Apply button is enabled only for a non-blank code (fe-core CouponInput);
 *   - [data-vbwd-cart-add] adds a fe-core cart item (cart.ts addItem) through window.VbwdTheme,
 *     then follows data-vbwd-navigate (TokenBundleCollection.addToCart);
 *   - a successful submit (HX-Redirect) empties the island's cart before htmx navigates,
 *     like the SPA sources' submit (cart.clearCart()); an island with no cart keeps all.
 * Everything is delegated on document, so swapped islands and regions keep working.
 */
(function (window) {
  'use strict';
  if (window.VbwdCheckout) {
    return;
  }

  var MINIMUM_PASSWORD_LENGTH = 8;
  var STRONG_PASSWORD_LENGTH = 12;
  var SPECIAL_CHARACTERS = /[!@#$%^&*(),.?":{}|<>]/;
  var CORE_CART_KEY = 'vbwd_cart';
  var FORM_SELECTOR = '[data-vbwd-checkout-form]';
  var CART_HOLDER_SELECTOR = '[data-vbwd-cart]';
  var REDIRECT_HEADER = 'HX-Redirect';

  function passwordStrength(password) {
    if (password.length < MINIMUM_PASSWORD_LENGTH) {
      return 'weak';
    }
    var hasLetters = /[a-zA-Z]/.test(password);
    var hasNumbers = /[0-9]/.test(password);
    if (password.length >= STRONG_PASSWORD_LENGTH && hasLetters && hasNumbers && SPECIAL_CHARACTERS.test(password)) {
      return 'strong';
    }
    return hasLetters && hasNumbers ? 'medium' : 'weak';
  }

  function registrationState(password, confirmation) {
    var strength = passwordStrength(password);
    return {
      strength: strength,
      mismatch: confirmation.length > 0 && password !== confirmation,
      canRegister: password.length >= MINIMUM_PASSWORD_LENGTH && password === confirmation && strength !== 'weak'
    };
  }

  function missingRequirements(state) {
    var missing = [];
    if (!state.authenticated) missing.push('signIn');
    if (state.payable && !state.billingComplete) missing.push('billingAddress');
    if (!state.payZero && !state.paymentSelected) missing.push('paymentMethod');
    if (!state.termsAccepted) missing.push('acceptTerms');
    return missing;
  }

  function addCoreCartItem(items, input) {
    var next = items.slice();
    for (var index = 0; index < next.length; index += 1) {
      if (next[index].id === input.id && next[index].type === input.type) {
        next[index] = Object.assign({}, next[index], { quantity: next[index].quantity + 1 });
        return next;
      }
    }
    next.push(Object.assign({}, input, { quantity: 1 }));
    return next;
  }

  function formState(form) {
    var required = Array.prototype.slice.call(form.querySelectorAll('[data-billing-required]'));
    return {
      authenticated: form.getAttribute('data-authenticated') === '1',
      payable: form.getAttribute('data-payable') === '1',
      payZero: form.getAttribute('data-pay-zero') === '1',
      billingComplete: required.every(function (field) { return field.value.trim() !== ''; }),
      paymentSelected: Boolean(form.querySelector('input[name="payment_method"]:checked')),
      termsAccepted: Boolean(form.querySelector('input[name="terms"]:checked'))
    };
  }

  function refreshRequirements(form) {
    var missing = missingRequirements(formState(form));
    Array.prototype.slice.call(form.querySelectorAll('[data-requirement]')).forEach(function (item) {
      item.hidden = missing.indexOf(item.getAttribute('data-requirement')) === -1;
    });
    var list = form.querySelector('[data-testid="checkout-requirements"]');
    if (list) list.hidden = missing.length === 0;
    var confirm = form.querySelector('[data-testid="confirm-checkout"]');
    if (confirm) confirm.disabled = missing.length > 0;
  }

  function refreshRegistration(container) {
    var password = container.querySelector('[data-vbwd-new-password]');
    var confirmation = container.querySelector('[data-vbwd-confirm-password]');
    var state = registrationState(password.value, confirmation.value);
    var bar = container.querySelector('[data-vbwd-strength-bar]');
    var label = container.querySelector('[data-vbwd-strength-label]');
    bar.className = 'strength-bar ' + state.strength;
    label.className = 'strength-label ' + state.strength;
    label.textContent = label.getAttribute('data-label-' + state.strength);
    container.querySelector('[data-testid="password-mismatch"]').hidden = !state.mismatch;
    container.querySelector('[data-vbwd-signup]').disabled = !state.canRegister;
  }

  function handleInput(event) {
    var target = event.target;
    if (!target || !target.closest) return;
    var registration = target.closest('.new-user-form');
    if (registration) refreshRegistration(registration);
    var login = target.closest('.login-form');
    if (login) login.querySelector('[data-vbwd-login]').disabled = target.value.length === 0;
    var coupon = target.closest('.vbwd-coupon__row');
    if (coupon) coupon.querySelector('[data-testid="coupon-apply"]').disabled = target.value.trim() === '';
    var form = target.closest(FORM_SELECTOR);
    if (form) refreshRequirements(form);
  }

  function selectPaymentMethod(option) {
    var form = option.closest(FORM_SELECTOR);
    var radio = option.querySelector('input[type="radio"]');
    radio.checked = true;
    Array.prototype.slice.call(form.querySelectorAll('[data-vbwd-payment-method]')).forEach(function (other) {
      other.classList.toggle('selected', other === option);
    });
    var instructions = form.querySelector('[data-testid="payment-method-instructions"]');
    var text = option.getAttribute('data-instructions') || '';
    instructions.hidden = text === '';
    instructions.querySelector('p').textContent = text;
    refreshRequirements(form);
  }

  function addToCart(button, event) {
    event.preventDefault();
    var items = window.VbwdTheme.readCart(window.localStorage, CORE_CART_KEY);
    var input = JSON.parse(button.getAttribute('data-vbwd-cart-add'));
    window.VbwdTheme.writeCart(window.localStorage, window.document, CORE_CART_KEY, addCoreCartItem(items, input));
    var destination = button.getAttribute('data-vbwd-navigate');
    if (destination) window.location.assign(destination);
  }

  function handleClick(event) {
    var target = event.target;
    if (!target || !target.closest) return;
    var cartButton = target.closest('[data-vbwd-cart-add]');
    if (cartButton) return addToCart(cartButton, event);
    var termsOpen = target.closest('[data-vbwd-terms-open]');
    var termsClose = target.closest('[data-vbwd-terms-close]');
    if (termsOpen || termsClose) {
      event.preventDefault();
      var popup = (termsOpen || termsClose).closest('.terms-checkbox').querySelector('[data-vbwd-terms-popup]');
      popup.hidden = Boolean(termsClose);
      return;
    }
    var option = target.closest('[data-vbwd-payment-method]');
    if (option) selectPaymentMethod(option);
    if (target.closest('.forgot-password-link')) event.preventDefault();
  }

  function handleSubmitRedirect(event) {
    if (!event.detail.xhr.getResponseHeader(REDIRECT_HEADER)) return;
    var holder = event.detail.elt.closest(CART_HOLDER_SELECTOR);
    if (!holder) return;
    window.VbwdTheme.writeCart(window.localStorage, window.document, holder.getAttribute('data-vbwd-cart'), []);
  }

  window.document.addEventListener('input', handleInput);
  window.document.addEventListener('htmx:beforeOnLoad', handleSubmitRedirect);
  window.document.addEventListener('change', handleInput);
  window.document.addEventListener('click', handleClick);

  window.VbwdCheckout = Object.freeze({
    passwordStrength: passwordStrength,
    registrationState: registrationState,
    missingRequirements: missingRequirements,
    addCoreCartItem: addCoreCartItem
  });
})(window);
