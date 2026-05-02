/**
 * cc-sounds.js — Emajinet Premium Sound System v2
 *
 * Synthesizes premium sounds in-browser using Web Audio API.
 * No external audio files. Works on Android/iOS after first user gesture.
 *
 * API:
 *   window.CCSounds.playSaleSuccessSound()    // After successful sale
 *   window.CCSounds.playSaleCompleteSound()   // Alias
 *   window.CCSounds.playCreditSaleSound()     // After credit sale
 *   window.CCSounds.playStockAddedSound()     // After stock-in
 *   window.CCSounds.playPaymentSuccessSound() // After payment collected
 *   window.CCSounds.playSuccessSound()        // Generic success
 *   window.CCSounds.playErrorSound()          // Error/warning
 *   window.CCSounds.isEnabled()              // Check toggle state
 *   window.CCSounds.setEnabled(bool)         // Update toggle
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'cc_sounds_enabled';

  // Lazy-init AudioContext after user gesture
  var _ctx = null;

  // Anti-double-trigger: track last play time per sound key
  var _lastPlayed = {};
  var MIN_INTERVAL_MS = 400;

  function _canPlay(key) {
    var now = Date.now();
    if (_lastPlayed[key] && (now - _lastPlayed[key]) < MIN_INTERVAL_MS) return false;
    _lastPlayed[key] = now;
    return true;
  }

  function _getCtx() {
    if (!_ctx) {
      try {
        _ctx = new (window.AudioContext || window.webkitAudioContext)();
      } catch (e) {
        return null;
      }
    }
    if (_ctx.state === 'suspended') {
      _ctx.resume().catch(function () {});
    }
    return _ctx;
  }

  /**
   * Play a single tone with envelope.
   * @param {number} freq       - Hz
   * @param {number} dur        - seconds
   * @param {string} type       - OscillatorType
   * @param {number} gain       - peak gain 0–1
   * @param {number} startDelay - seconds from now
   */
  function _tone(freq, dur, type, gain, startDelay) {
    var ctx = _getCtx();
    if (!ctx) return;

    var osc = ctx.createOscillator();
    var gainNode = ctx.createGain();

    osc.connect(gainNode);
    gainNode.connect(ctx.destination);

    osc.type = type || 'sine';
    osc.frequency.value = freq;

    var start = ctx.currentTime + (startDelay || 0);
    gainNode.gain.setValueAtTime(0, start);
    gainNode.gain.linearRampToValueAtTime(gain || 0.25, start + 0.015);
    gainNode.gain.exponentialRampToValueAtTime(0.001, start + dur);

    osc.start(start);
    osc.stop(start + dur + 0.02);
  }

  // ─── Sound Definitions ──────────────────────────────────────────────────────

  /**
   * SALE COMPLETE — Premium ascending chime (C5→E5→G5 major arpeggio).
   * Premium POS-style. Used after every successful cash or card sale.
   */
  function playSaleCompleteSound() {
    if (!isEnabled() || !_canPlay('sale')) return;
    _tone(523.25, 0.22, 'sine', 0.28, 0.00);  // C5
    _tone(659.25, 0.22, 'sine', 0.26, 0.11);  // E5
    _tone(783.99, 0.40, 'sine', 0.22, 0.22);  // G5
    _tone(1046.5, 0.28, 'sine', 0.10, 0.22);  // C6 shimmer
  }

  /**
   * CREDIT SALE — Slightly more reserved rising pair (signals "tab opened").
   */
  function playCreditSaleSound() {
    if (!isEnabled() || !_canPlay('credit')) return;
    _tone(493.88, 0.20, 'sine', 0.22, 0.00);  // B4
    _tone(659.25, 0.32, 'sine', 0.20, 0.14);  // E5
    _tone(880.00, 0.22, 'sine', 0.08, 0.30);  // A5 soft tail
  }

  /**
   * STOCK ADDED — Double-ping confirmation. Lighter "items received" feel.
   */
  function playStockAddedSound() {
    if (!isEnabled() || !_canPlay('stock')) return;
    _tone(440.00, 0.16, 'sine', 0.20, 0.00);  // A4
    _tone(550.00, 0.26, 'sine', 0.18, 0.09);  // C#5
    _tone(659.25, 0.18, 'sine', 0.10, 0.20);  // E5 tail
  }

  /**
   * PAYMENT COLLECTED — Warm two-note coin-drop feel.
   */
  function playPaymentSuccessSound() {
    if (!isEnabled() || !_canPlay('payment')) return;
    _tone(783.99, 0.18, 'sine', 0.26, 0.00);  // G5
    _tone(1046.5, 0.30, 'sine', 0.22, 0.12);  // C6
    _tone(783.99, 0.22, 'sine', 0.12, 0.28);  // G5 echo
  }

  /**
   * GENERIC SUCCESS — Single clean chime.
   */
  function playSuccessSound() {
    if (!isEnabled() || !_canPlay('success')) return;
    _tone(659.25, 0.28, 'sine', 0.22, 0.00);
    _tone(880.00, 0.22, 'sine', 0.12, 0.14);
  }

  /**
   * ERROR / WARNING — Low descending pair.
   */
  function playErrorSound() {
    if (!isEnabled() || !_canPlay('error')) return;
    _tone(330.00, 0.14, 'sine', 0.16, 0.00);
    _tone(220.00, 0.24, 'sine', 0.16, 0.10);
  }

  // ─── Settings persistence ────────────────────────────────────────────────────

  function isEnabled() {
    try {
      return localStorage.getItem(STORAGE_KEY) !== 'false';
    } catch (e) {
      return true;
    }
  }

  function setEnabled(enabled) {
    try {
      localStorage.setItem(STORAGE_KEY, enabled ? 'true' : 'false');
    } catch (e) {}
  }

  // ─── Bootstrap AudioContext on first user interaction ────────────────────────

  var _bootstrapped = false;
  function _bootstrap() {
    if (_bootstrapped) return;
    _bootstrapped = true;
    _getCtx();
  }
  document.addEventListener('touchstart', _bootstrap, { once: true, passive: true });
  document.addEventListener('click', _bootstrap, { once: true });

  // ─── Global custom event listeners ───────────────────────────────────────────
  // Any page/vertical can fire these events to trigger sounds:
  //   document.dispatchEvent(new CustomEvent('cc:sale_success'))
  //   document.dispatchEvent(new CustomEvent('cc:credit_sale'))
  //   document.dispatchEvent(new CustomEvent('cc:stock_added'))
  //   document.dispatchEvent(new CustomEvent('cc:payment_success'))

  document.addEventListener('cc:sale_success',    function () { playSaleCompleteSound(); });
  document.addEventListener('cc:credit_sale',     function () { playCreditSaleSound(); });
  document.addEventListener('cc:stock_added',     function () { playStockAddedSound(); });
  document.addEventListener('cc:payment_success', function () { playPaymentSuccessSound(); });
  document.addEventListener('cc:success',         function () { playSuccessSound(); });

  // ─── Public API ──────────────────────────────────────────────────────────────

  window.CCSounds = {
    // Primary named functions
    playSaleSuccessSound: playSaleCompleteSound,   // canonical name
    playSaleCompleteSound: playSaleCompleteSound,  // backward compat
    playCreditSaleSound: playCreditSaleSound,
    playStockAddedSound: playStockAddedSound,
    playStockSuccessSound: playStockAddedSound,    // alias
    playPaymentSuccessSound: playPaymentSuccessSound,
    playSuccessSound: playSuccessSound,
    playErrorSound: playErrorSound,
    // Settings
    isEnabled: isEnabled,
    setEnabled: setEnabled,
  };

})();
