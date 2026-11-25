// Local storefront behavior and project-specific visual overrides.
(() => {
  const isLocal = location.hostname === '127.0.0.1' || location.hostname === 'localhost';
  if (!isLocal) return;

  const config = Object.assign({ checkoutUrl: '' }, window.KAORI_STOREFRONT_CONFIG || {});
  const unavailableRoutes = new Map([
    ['/apps/parcelpanel', 'Order tracking will be connected with the order system.'],
    ['/customer_authentication/redirect', 'Customer accounts will be connected with the store backend.'],
    ['/a/loop_subscriptions/customer', 'Subscription management will be connected with the store backend.'],
  ]);

  function showNotice(message) {
    let notice = document.querySelector('.kaori-local-notice');
    if (!notice) {
      notice = document.createElement('div');
      notice.className = 'kaori-local-notice';
      notice.setAttribute('role', 'status');
      notice.setAttribute('aria-live', 'polite');
      document.body.appendChild(notice);
    }
    notice.textContent = message;
    notice.classList.add('kaori-local-notice--visible');
    window.clearTimeout(notice._hideTimer);
    notice._hideTimer = window.setTimeout(() => {
      notice.classList.remove('kaori-local-notice--visible');
    }, 3200);
  }

  function openCheckout() {
    const checkoutUrl = String(config.checkoutUrl || '').trim();
    if (!checkoutUrl) {
      showNotice('Checkout is ready to connect. Add the final URL in storefront-config.js.');
      return;
    }
    window.location.assign(checkoutUrl);
  }

  function installLocalStyles() {
    if (document.querySelector('#kaori-local-styles')) return;
    const style = document.createElement('style');
    style.id = 'kaori-local-styles';
    style.textContent = `
      .kaori-local-notice {
        background: #21352e;
        border: 1px solid rgba(255,255,255,.18);
        border-radius: 8px;
        bottom: 22px;
        box-shadow: 0 14px 36px rgba(0,0,0,.2);
        color: #fff;
        font-size: 13px;
        left: 50%;
        line-height: 1.45;
        max-width: min(440px, calc(100vw - 32px));
        opacity: 0;
        padding: 13px 17px;
        pointer-events: none;
        position: fixed;
        text-align: center;
        transform: translate(-50%, 14px);
        transition: opacity .2s ease, transform .2s ease;
        visibility: hidden;
        z-index: 2147483647;
      }
      .kaori-local-notice--visible {
        opacity: 1;
        transform: translate(-50%, 0);
        visibility: visible;
      }
      a[data-local-feature] { cursor: not-allowed; }
      .kaori-local-search-results {
        margin-top: 42px;
      }
      .kaori-local-search-results__summary {
        color: rgba(var(--color-foreground), .7);
        margin: 0 0 22px;
        text-align: center;
      }
      .kaori-local-search-results__empty {
        padding: 42px 0 10px;
        text-align: center;
      }
      .kaori-local-checkout-button {
        position: relative;
        width: 100%;
        z-index: 3;
      }
    `;
    document.head.appendChild(style);
  }

  function repairLocalAssetUrls(root = document) {
    const attributes = ['src', 'srcset', 'data-src', 'data-srcset', 'poster'];
    const selector = '[src], [srcset], [data-src], [data-srcset], [poster]';
    const elements = root.querySelectorAll ? [...root.querySelectorAll(selector)] : [];
    if (root.matches && root.matches(selector)) elements.unshift(root);
    elements.forEach((element) => {
      attributes.forEach((attribute) => {
        const value = element.getAttribute(attribute);
        if (!value) return;
        const localValue = value.replace(/https?:\/\/(?:www\.)?try-kaori\.com/gi, '').replace(/\/\/(?:www\.)?try-kaori\.com/gi, '');
        if (localValue !== value) element.setAttribute(attribute, localValue);
      });
    });
  }

  function installLocalGuards() {
    document.querySelectorAll('a[href]').forEach((link) => {
      try {
        const path = new URL(link.href, location.href).pathname;
        if (unavailableRoutes.has(path)) {
          link.dataset.localFeature = path;
          link.setAttribute('aria-disabled', 'true');
        }
      } catch { /* Ignore malformed third-party links. */ }
    });

    window.addEventListener('submit', (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      const action = form.getAttribute('action') || '';
      if (action.includes('/cart')) {
        event.preventDefault();
        event.stopImmediatePropagation();
        openCheckout();
      } else if (action.includes('/contact')) {
        event.preventDefault();
        event.stopImmediatePropagation();
        showNotice('The contact form will be enabled when the site backend is connected.');
      } else if (action.includes('/localization')) {
        event.preventDefault();
        event.stopImmediatePropagation();
        showNotice('Country selection will be enabled with the commerce backend.');
      }
    }, true);

    window.addEventListener('click', (event) => {
      const link = event.target.closest('a[href]');
      if (link) {
        try {
          const path = new URL(link.href, location.href).pathname;
          if (path === '/cart' || path.startsWith('/buy/')) {
            event.preventDefault();
            event.stopImmediatePropagation();
            openCheckout();
            return;
          }
          if (unavailableRoutes.has(path)) {
            event.preventDefault();
            event.stopImmediatePropagation();
            showNotice(unavailableRoutes.get(path));
            return;
          }
        } catch { /* Ignore malformed third-party links. */ }
      }

      const button = event.target.closest('button, [role="button"]');
      const label = button ? (button.textContent || button.getAttribute('aria-label') || '').trim() : '';
      if (button && /(add to (cart|ritual)|buy now|checkout)/i.test(label)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        openCheckout();
      }
    }, true);
  }

  async function installLocalSearch() {
    if (location.pathname !== '/search') return;
    const query = new URLSearchParams(location.search).get('q')?.trim() || '';
    document.querySelectorAll('input[name="q"]').forEach((input) => {
      input.value = query;
    });
    if (!query || document.querySelector('.kaori-local-search-results')) return;

    const host = document.querySelector('.template-search');
    const header = host?.querySelector('.template-search__header');
    if (!host || !header) return;

    try {
      const response = await fetch('/collections/all');
      if (!response.ok) throw new Error(`Catalog request failed: ${response.status}`);
      const catalog = new DOMParser().parseFromString(await response.text(), 'text/html');
      const needle = query.toLocaleLowerCase('en');
      const items = [...catalog.querySelectorAll('#product-grid > li')].filter((item) => {
        const name = item.querySelector('.card__heading a')?.textContent || item.textContent || '';
        return name.toLocaleLowerCase('en').includes(needle);
      });

      const results = document.createElement('section');
      results.className = 'kaori-local-search-results page-width';
      results.setAttribute('aria-label', 'Search results');
      const summary = document.createElement('p');
      summary.className = 'kaori-local-search-results__summary';
      summary.textContent = `${items.length} ${items.length === 1 ? 'product' : 'products'} found for “${query}”`;
      results.appendChild(summary);

      if (items.length) {
        const grid = document.createElement('ul');
        grid.id = 'kaori-local-search-grid';
        grid.className = 'grid product-grid grid--2-col-tablet-down grid--4-col-desktop';
        items.forEach((item) => grid.appendChild(document.importNode(item, true)));
        grid.querySelectorAll('form[action*="/cart"]').forEach((form) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'button button--full-width button--primary kaori-local-checkout-button';
          button.textContent = 'Buy now';
          button.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopImmediatePropagation();
            openCheckout();
          }, true);
          (form.closest('product-form') || form).replaceWith(button);
        });
        results.appendChild(grid);
      } else {
        const empty = document.createElement('p');
        empty.className = 'kaori-local-search-results__empty';
        empty.textContent = 'No products matched your search.';
        results.appendChild(empty);
      }

      header.insertAdjacentElement('afterend', results);
      host.classList.remove('template-search--empty');
      repairLocalAssetUrls(results);
    } catch {
      showNotice('Local search could not load the product catalog.');
    }
  }

  function init() {
    installLocalStyles();
    repairLocalAssetUrls();
    installLocalGuards();
    installLocalSearch();

    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === 'attributes') repairLocalAssetUrls(mutation.target);
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType !== Node.ELEMENT_NODE) return;
          repairLocalAssetUrls(node);
        });
      });
    });
    observer.observe(document.documentElement, {
      attributeFilter: ['src', 'srcset', 'data-src', 'data-srcset', 'poster'],
      attributes: true,
      childList: true,
      subtree: true,
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
