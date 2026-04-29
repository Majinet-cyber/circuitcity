/**
 * cc-sounds.js — Emajinet Premium Sound System
 *
 * Uses the Web Audio API to synthesize premium sounds entirely in-browser.
 * No external audio files required. Works on Android Chrome (after first user touch).
 *
 * Usage:
 *   window.CCSounds.playSaleCompleteSound();   // After successful sale
 *   window.CCSounds.playStockAddedSound();      // After successful stock-in
 *   window.CCSounds.playSuccessSound();         // Generic success action
 *   window.CCSounds.isEnabled();               // Check toggle state
 *   window.CCSounds.setEnabled(true/false);    // Update toggle
 */
(function() {
  'use strict';

  var STORAGE_KEY = 'cc_sounds_enabled';

  // Lazy-init AudioContext after user gesture
  var _ctx = null;

  function _getCtx() {
    if (!_ctx) {
      try {
        _ctx = new (window.AudioContext || window.webkitAudioContext)();
      } catch (e) {
        return null;
      }
    }
    if (_ctx.state === 'suspended') {
      _ctx.resume().catch(function() {});
    }
    return _ctx;
  }

  /**
   * Play a single tone with smooth fade-out.
   * @param {number} freq   - Frequency in Hz
   * @param {number} dur    - Duration in seconds
   * @param {string} type   - OscillatorType: 'sine' | 'triangle' | 'square'
   * @param {number} gain   - Peak gain (0–1)
   * @param {number} startDelay - Seconds from now to start
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
    osc.stop(start + dur + 0.01);
  }

  /**
   * SALE COMPLETE — Premium ascending chime.
   * Three rising notes like a confident "transaction done" sound.
   * Inspired by: premium POS + Stripe confirmation.
   */
  function playSaleCompleteSound() {
    if (!isEnabled()) return;
    // C5 → E5 → G5 (major chord arpeggio)
    _tone(523.25, 0.25, 'sine', 0.28, 0.00);
    _tone(659.25, 0.25, 'sine', 0.28, 0.12);
    _tone(783.99, 0.50, 'sine', 0.22, 0.24);
    // Subtle harmonic shimmer on the last note
    _tone(1567.98, 0.30, 'sine', 0.06, 0.24);
  }

  /**
   * STOCK ADDED — Short double-ping confirmation.
   * Lighter than sale sound — feels like "items received".
   */
  function playStockAddedSound() {
    if (!isEnabled()) return;
    _tone(440.00, 0.18, 'sine', 0.20, 0.00);
    _tone(550.00, 0.28, 'sine', 0.18, 0.10);
  }

  /**
   * GENERIC SUCCESS — Single clean chime.
   */
  function playSuccessSound() {
    if (!isEnabled()) return;
    _tone(659.25, 0.30, 'sine', 0.22, 0.00);
    _tone(880.00, 0.25, 'sine', 0.12, 0.15);
  }

  /**
   * ERROR / WARNING — Low descending tone.
   */
  function playErrorSound() {
    if (!isEnabled()) return;
    _tone(330.00, 0.15, 'sine', 0.15, 0.00);
    _tone(220.00, 0.25, 'sine', 0.15, 0.10);
  }

  // ──────────────────────────────────────────────────
  // Settings persistence (localStorage)
  // ──────────────────────────────────────────────────

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

  // ──────────────────────────────────────────────────
  // Bootstrap AudioContext on first user interaction
  // (required for mobile browsers)
  // ──────────────────────────────────────────────────
  var _bootstrapped = false;
  function _bootstrap() {
    if (_bootstrapped) return;
    _bootstrapped = true;
    _getCtx();
    document.removeEventListener('touchstart', _bootstrap);
    document.removeEventListener('click', _bootstrap);
  }
  document.addEventListener('touchstart', _bootstrap, { once: true, passive: true });
  document.addEventListener('click', _bootstrap, { once: true });

  // ──────────────────────────────────────────────────
  // Public API
  // ──────────────────────────────────────────────────
  window.CCSounds = {
    playSaleCompleteSound: playSaleCompleteSound,
    playStockAddedSound: playStockAddedSound,
    playSuccessSound: playSuccessSound,
    playErrorSound: playErrorSound,
    isEnabled: isEnabled,
    setEnabled: setEnabled,
  };

})();
