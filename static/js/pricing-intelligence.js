/**
 * Pricing Intelligence Module
 * ===========================
 * Real-time price validation with smart suggestions and warnings.
 * Used across ALL verticals (Phones, Liquor, Pharmacy, etc.) for consistent UX.
 * 
 * Usage:
 * ```javascript
 * const validator = new PricingIntelligence({
 *   sellingPriceInput: '#selling-price-input',
 *   costPrice: 31500,
 *   suggestedPrice: 35000,
 *   feedbackContainer: '#price-feedback',
 *   onValidate: (result) => { console.log(result); }
 * });
 * ```
 */

class PricingIntelligence {
  constructor(options) {
    this.options = {
      sellingPriceInput: null,
      costPrice: null,
      suggestedPrice: null,
      feedbackContainer: null,
      onValidate: null,
      currency: 'MK',
      ...options
    };

    this.inputElement = this._getElement(this.options.sellingPriceInput);
    this.feedbackElement = this._getElement(this.options.feedbackContainer);
    
    if (!this.inputElement) {
      console.error('PricingIntelligence: sellingPriceInput element not found');
      return;
    }

    this._init();
  }

  _getElement(selector) {
    if (!selector) return null;
    return typeof selector === 'string' ? document.querySelector(selector) : selector;
  }

  _init() {
    // Attach event listeners
    this.inputElement.addEventListener('input', () => this._onInput());
    this.inputElement.addEventListener('blur', () => this._onBlur());
    
    // Add CSS classes for styling
    if (this.inputElement.parentElement) {
      this.inputElement.parentElement.classList.add('pricing-intelligence-field');
    }
    
    // Initial validation if value exists
    if (this.inputElement.value) {
      this._validatePrice();
    }
  }

  _onInput() {
    // Real-time validation as user types
    clearTimeout(this._debounceTimer);
    this._debounceTimer = setTimeout(() => {
      this._validatePrice();
    }, 300); // 300ms debounce
  }

  _onBlur() {
    // Format price on blur
    const value = this._parseInput(this.inputElement.value);
    if (value > 0) {
      // Format with commas for readability
      this.inputElement.value = value.toFixed(2);
    }
    this._validatePrice();
  }

  _parseInput(input) {
    if (!input) return 0;
    
    // Remove commas, currency symbols
    const cleaned = String(input).replace(/,/g, '').replace(/MK/gi, '').replace(/K/gi, '').trim();
    
    const parsed = parseFloat(cleaned);
    return isNaN(parsed) ? 0 : parsed;
  }

  _formatCurrency(amount) {
    try {
      // Format with commas, strip unnecessary decimal zeros
      const formatted = amount.toFixed(2).replace(/\.00$/, '').replace(/(\d)(?=(\d{3})+(?!\d))/g, '$1,');
      return `${this.options.currency} ${formatted}`;
    } catch (e) {
      return `${this.options.currency} ${amount}`;
    }
  }

  _detectMagnitudeError(sellingPrice, costPrice) {
    if (!costPrice || costPrice <= 0) return null;
    
    // Price is way too low compared to cost (less than 10% of cost)
    if (sellingPrice > 0 && sellingPrice < (costPrice * 0.10)) {
      const suggestions = [];
      
      const multiplied10 = sellingPrice * 10;
      const multiplied100 = sellingPrice * 100;
      
      // Only suggest if it gets close to reasonable range (0.8x to 2x cost)
      if (multiplied10 >= costPrice * 0.8 && multiplied10 <= costPrice * 2) {
        suggestions.push(this._formatCurrency(multiplied10));
      }
      
      if (multiplied100 >= costPrice * 0.8 && multiplied100 <= costPrice * 2) {
        suggestions.push(this._formatCurrency(multiplied100));
      }
      
      if (suggestions.length > 0) {
        return {
          detected: true,
          suggestions: suggestions,
          message: `This looks unusually low. Did you mean ${suggestions.join(' or ')}?`
        };
      }
    }
    
    return null;
  }

  _validatePrice() {
    const sellingPrice = this._parseInput(this.inputElement.value);
    const costPrice = this.options.costPrice;
    const suggestedPrice = this.options.suggestedPrice;
    
    const result = {
      valid: true,
      warnings: [],
      suggestions: [],
      feedback: '',
      severity: 'info',
      profitMargin: null,
      profitMarginPct: null
    };
    
    // Basic validation
    if (sellingPrice <= 0) {
      result.valid = false;
      result.warnings.push('❌ Price must be greater than zero');
      result.severity = 'error';
      this._displayFeedback(result);
      return result;
    }
    
    // Check for absurdly high prices
    if (sellingPrice > 100000000) {
      result.valid = false;
      result.warnings.push('❌ Price is unreasonably high. Please check your input.');
      result.severity = 'error';
      this._displayFeedback(result);
      return result;
    }
    
    // Check for suspiciously high prices
    if (sellingPrice > 10000000) {
      result.warnings.push('⚠️ This price looks unusually high. Please confirm.');
      result.severity = 'warning';
    }
    
    // Cost-based validation (PRIMARY INTELLIGENCE)
    if (costPrice && costPrice > 0) {
      const profitMargin = sellingPrice - costPrice;
      const profitMarginPct = (profitMargin / costPrice) * 100;
      
      result.profitMargin = profitMargin;
      result.profitMarginPct = profitMarginPct;
      
      // 1. Check for magnitude errors FIRST (most critical)
      const magnitudeError = this._detectMagnitudeError(sellingPrice, costPrice);
      if (magnitudeError) {
        result.warnings.push(magnitudeError.message);
        result.suggestions.push(...magnitudeError.suggestions);
        result.severity = 'warning';
      }
      
      // 2. Below cost warning (CRITICAL)
      if (sellingPrice < costPrice) {
        const loss = costPrice - sellingPrice;
        result.warnings.push(
          `⚠️ This is below order value (${this._formatCurrency(costPrice)}).`
        );
        result.suggestions.push(`Did you mean ${this._formatCurrency(costPrice)}?`);
        
        // Add reasonable markup suggestions
        const markup10 = costPrice * 1.10;  // 10% markup
        const markup20 = costPrice * 1.20;  // 20% markup
        result.suggestions.push(`Or ${this._formatCurrency(markup10)}?`);
        result.suggestions.push(`Or ${this._formatCurrency(markup20)}?`);
        
        result.severity = 'warning';
      }
      // 3. Very low margin warning (< 5%)
      else if (profitMarginPct < 5) {
        result.warnings.push(
          `⚠️ Low profit margin (${profitMarginPct.toFixed(1)}%). Consider pricing higher.`
        );
        result.severity = 'warning';
      }
      // 4. Good margin feedback (>= 10%)
      else if (profitMarginPct >= 15) {
        result.feedback = `✅ Great profit margin (${profitMarginPct.toFixed(1)}%)!`;
        result.severity = 'success';
      } else if (profitMarginPct >= 10) {
        result.feedback = `✅ Good profit margin (${profitMarginPct.toFixed(1)}%)`;
        result.severity = 'success';
      } else {
        result.feedback = `Profit margin: ${profitMarginPct.toFixed(1)}%`;
        result.severity = 'info';
      }
    }
    
    // Suggested price comparison (if available and different from cost-based feedback)
    if (suggestedPrice && suggestedPrice > 0 && costPrice) {
      const diff = sellingPrice - suggestedPrice;
      const diffPct = (diff / suggestedPrice) * 100;
      
      // Only warn if deviation is significant
      if (Math.abs(diffPct) > 30) {
        if (diff > 0) {
          result.warnings.push(
            `⚠️ Price is ${diffPct.toFixed(0)}% higher than typical (${this._formatCurrency(suggestedPrice)})`
          );
        } else {
          result.warnings.push(
            `⚠️ Price is ${Math.abs(diffPct).toFixed(0)}% lower than typical (${this._formatCurrency(suggestedPrice)})`
          );
        }
        
        if (result.severity === 'info') {
          result.severity = 'warning';
        }
      }
    }
    
    this._displayFeedback(result);
    
    // Call custom callback if provided
    if (this.options.onValidate) {
      this.options.onValidate(result);
    }
    
    return result;
  }

  _displayFeedback(result) {
    if (!this.feedbackElement) return;
    
    // Clear previous feedback
    this.feedbackElement.innerHTML = '';
    this.feedbackElement.className = 'pricing-feedback';
    
    // Add severity class
    this.feedbackElement.classList.add(`pricing-feedback-${result.severity}`);
    
    // Apply visual state to input
    this.inputElement.classList.remove('input-error', 'input-warning', 'input-success', 'input-info');
    if (result.severity === 'error' || result.severity === 'warning') {
      this.inputElement.classList.add(`input-${result.severity}`);
    } else if (result.severity === 'success') {
      this.inputElement.classList.add('input-success');
    }
    
    // Display warnings
    if (result.warnings.length > 0) {
      const warningsDiv = document.createElement('div');
      warningsDiv.className = 'pricing-warnings';
      result.warnings.forEach(warning => {
        const p = document.createElement('p');
        p.textContent = warning;
        warningsDiv.appendChild(p);
      });
      this.feedbackElement.appendChild(warningsDiv);
    }
    
    // Display suggestions (clickable)
    if (result.suggestions.length > 0) {
      const suggestionsDiv = document.createElement('div');
      suggestionsDiv.className = 'pricing-suggestions';
      
      const label = document.createElement('p');
      label.textContent = 'Suggestions:';
      label.style.fontWeight = '600';
      label.style.marginBottom = '0.5rem';
      suggestionsDiv.appendChild(label);
      
      result.suggestions.forEach((suggestion, index) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'pricing-suggestion-btn';
        btn.textContent = suggestion;
        btn.onclick = () => {
          // Extract numeric value from formatted suggestion
          const numericValue = suggestion.replace(/[^0-9.,]/g, '').replace(/,/g, '');
          this.inputElement.value = numericValue;
          this.inputElement.focus();
          this._validatePrice();
        };
        suggestionsDiv.appendChild(btn);
      });
      
      this.feedbackElement.appendChild(suggestionsDiv);
    }
    
    // Display positive feedback
    if (result.feedback && result.severity === 'success') {
      const feedbackDiv = document.createElement('div');
      feedbackDiv.className = 'pricing-positive-feedback';
      feedbackDiv.textContent = result.feedback;
      this.feedbackElement.appendChild(feedbackDiv);
    }
    
    // Show/hide feedback container
    if (result.warnings.length > 0 || result.suggestions.length > 0 || result.feedback) {
      this.feedbackElement.style.display = 'block';
    } else {
      this.feedbackElement.style.display = 'none';
    }
  }

  // Public method to update cost price dynamically
  updateCostPrice(newCostPrice) {
    this.options.costPrice = newCostPrice;
    if (this.inputElement.value) {
      this._validatePrice();
    }
  }

  // Public method to update suggested price dynamically
  updateSuggestedPrice(newSuggestedPrice) {
    this.options.suggestedPrice = newSuggestedPrice;
    if (this.inputElement.value) {
      this._validatePrice();
    }
  }
}

// Export for use in modules (if using module system)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PricingIntelligence;
}

// Also attach to window for direct script inclusion
if (typeof window !== 'undefined') {
  window.PricingIntelligence = PricingIntelligence;
}

