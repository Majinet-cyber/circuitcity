/**
 * CC Fetch Helper - Centralized fetch utility for Emajinet/CircuitCity
 * Handles JSON endpoints, session expiry, and error messages gracefully
 */

(function(window) {
  'use strict';

  /**
   * Centralized JSON fetch helper
   * @param {string} url - The endpoint URL
   * @param {Object} options - Fetch options
   * @returns {Promise<Object>} - Parsed JSON response
   */
  async function ccFetchJson(url, options = {}) {
    try {
      const response = await fetch(url, {
        credentials: 'same-origin',
        headers: {
          'Accept': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
          ...options.headers
        },
        ...options
      });

      // Handle HTTP errors
      if (!response.ok) {
        // Check if it's a redirect to login (302)
        if (response.redirected && response.url.includes('/login')) {
          throw new Error('Session expired, please login');
        }

        // Handle specific HTTP status codes
        switch (response.status) {
          case 400:
            throw new Error('Bad request');
          case 401:
            throw new Error('Unauthorized - please login');
          case 403:
            throw new Error('Access denied');
          case 404:
            throw new Error('Endpoint not found');
          case 500:
            throw new Error('Server error');
          case 503:
            throw new Error('Service unavailable');
          default:
            throw new Error(`HTTP ${response.status}`);
        }
      }

      // Check if response is actually JSON
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        // Try to read as text to see if it's HTML (login page)
        const text = await response.text();
        console.error('Non-JSON response received:', text.substring(0, 200));
        
        if (text.includes('<!DOCTYPE') || text.includes('<html')) {
          throw new Error('Session expired, please login');
        }
        
        throw new Error('Invalid response format (expected JSON)');
      }

      // Parse and return JSON
      const data = await response.json();
      
      // Handle API-level errors
      if (data.error) {
        throw new Error(data.error);
      }
      
      if (data.ok === false) {
        throw new Error(data.message || data.error || 'Request failed');
      }

      return data;

    } catch (error) {
      // Log full error details for debugging
      console.error('[ccFetchJson] Error fetching', url, error);
      
      // Network errors
      if (error.name === 'TypeError' && error.message === 'Failed to fetch') {
        throw new Error('Network error - please check your connection');
      }
      
      // Re-throw with context
      throw error;
    }
  }

  /**
   * Safe wrapper for ccFetchJson that returns empty state instead of throwing
   * @param {string} url - The endpoint URL  
   * @param {Object} defaultValue - Default value to return on error
   * @returns {Promise<Object>} - Parsed JSON or default value
   */
  async function ccFetchJsonSafe(url, defaultValue = { labels: [], values: [] }) {
    try {
      return await ccFetchJson(url);
    } catch (error) {
      console.warn('[ccFetchJsonSafe] Returning default value due to error:', error.message);
      return defaultValue;
    }
  }

  /**
   * Fetch with retry logic
   * @param {string} url - The endpoint URL
   * @param {number} maxRetries - Maximum number of retries
   * @param {number} retryDelay - Delay between retries in ms
   * @returns {Promise<Object>} - Parsed JSON response
   */
  async function ccFetchJsonRetry(url, maxRetries = 3, retryDelay = 1000) {
    let lastError;
    
    for (let i = 0; i < maxRetries; i++) {
      try {
        return await ccFetchJson(url);
      } catch (error) {
        lastError = error;
        
        // Don't retry on auth errors or client errors
        if (error.message.includes('login') || 
            error.message.includes('Unauthorized') ||
            error.message.includes('Access denied') ||
            error.message.includes('Bad request')) {
          throw error;
        }
        
        // Wait before retry (except on last attempt)
        if (i < maxRetries - 1) {
          await new Promise(resolve => setTimeout(resolve, retryDelay * (i + 1)));
        }
      }
    }
    
    throw lastError;
  }

  // Expose to global scope
  window.ccFetchJson = ccFetchJson;
  window.ccFetchJsonSafe = ccFetchJsonSafe;
  window.ccFetchJsonRetry = ccFetchJsonRetry;

})(window);

