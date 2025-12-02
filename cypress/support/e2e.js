// ***********************************************************
// This support file is processed and loaded automatically before your test files.
// You can read more here: https://on.cypress.io/configuration
// ***********************************************************

// Import commands.js using ES2015 syntax:
import './commands';

// Alternatively you can use CommonJS syntax:
// require('./commands')

// Hide fetch/XHR logs to reduce noise
const app = window.top;
if (!app.document.head.querySelector('[data-hide-command-log-request]')) {
  const style = app.document.createElement('style');
  style.innerHTML = '.command-name-request, .command-name-xhr { display: none }';
  style.setAttribute('data-hide-command-log-request', '');
  app.document.head.appendChild(style);
}

// Suppress uncaught exceptions that may occur during navigation
Cypress.on('uncaught:exception', (err, runnable) => {
  // Returning false here prevents Cypress from failing the test
  // Only use this for known, non-critical errors
  console.warn('Uncaught exception:', err.message);
  return false;
});

