// Keeps the recovered storefront safe and predictable when run locally.
document.addEventListener('DOMContentLoaded', () => {
  const local = location.hostname === '127.0.0.1' || location.hostname === 'localhost';
  if (!local) return;
  document.querySelectorAll('form[action*="/cart"], form[action*="/contact"]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      alert('Backup local: envio, carrinho e checkout precisam de um backend para funcionar.');
    });
  });
});
