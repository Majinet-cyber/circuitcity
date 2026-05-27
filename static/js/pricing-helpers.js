/**
 * Pricing Calculation Helpers
 * Single source of truth for profit/margin/markup calculations
 * Used across all verticals
 */

const PricingHelpers = {
  /**
   * Calculate profit, margin, and markup
   * @param {number} costPrice - Cost/order price
   * @param {number} sellingPrice - Selling price
   * @returns {object} { profit, marginPercent, markupPercent, isProfit }
   */
  calculate(costPrice, sellingPrice) {
    const cost = parseFloat(costPrice) || 0;
    const sell = parseFloat(sellingPrice) || 0;
    
    const profit = sell - cost;
    const isProfit = profit >= 0;
    
    // Margin = profit / selling_price * 100
    let marginPercent = null;
    if (sell > 0) {
      marginPercent = (profit / sell) * 100;
    }
    
    // Markup = profit / cost_price * 100
    let markupPercent = null;
    if (cost > 0) {
      markupPercent = (profit / cost) * 100;
    }
    
    return {
      profit,
      marginPercent,
      markupPercent,
      isProfit,
      cost,
      sell
    };
  },
  
  /**
   * Format currency with comma separators
   * @param {number} amount
   * @param {string} currency - Currency symbol (default: 'MWK')
   * @returns {string}
   */
  formatCurrency(amount, currency = 'MWK') {
    const num = parseFloat(amount) || 0;
    return `${currency} ${num.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  },
  
  /**
   * Round percentage to nearest integer
   * @param {number} percent
   * @returns {number}
   */
  roundPercent(percent) {
    if (percent === null || percent === undefined) return null;
    return Math.round(percent);
  },
  
  /**
   * Get feedback message for pricing
   * @param {object} calc - Result from calculate()
   * @returns {object} { icon, message, type }
   */
  getFeedback(calc) {
    if (!calc.isProfit) {
      // Below cost - Loss
      const lossAmount = this.formatCurrency(Math.abs(calc.profit));
      const marginRounded = this.roundPercent(calc.marginPercent);
      return {
        icon: '🟡',
        message: `Loss: ${lossAmount} — Margin: ${marginRounded}%`,
        type: 'below-cost'
      };
    }
    
    // Above cost - Show both markup and margin
    const markupRounded = this.roundPercent(calc.markupPercent);
    const marginRounded = this.roundPercent(calc.marginPercent);
    
    // Markup is the primary number (more intuitive for merchants)
    // But we show both for transparency
    const markupDisplay = markupRounded !== null ? `${markupRounded}%` : 'N/A';
    const marginDisplay = marginRounded !== null ? `${marginRounded}%` : 'N/A';
    
    let message;
    if (calc.markupPercent !== null && calc.markupPercent < 10) {
      message = `Nice 👍 — ${markupDisplay} markup (${marginDisplay} margin)`;
    } else if (calc.markupPercent !== null && calc.markupPercent < 25) {
      message = `Great choice 💡 — ${markupDisplay} markup (${marginDisplay} margin)`;
    } else if (calc.markupPercent !== null && calc.markupPercent < 50) {
      message = `Excellent 🚀 — ${markupDisplay} markup (${marginDisplay} margin)`;
    } else {
      message = `Amazing deal 🎉 — ${markupDisplay} markup (${marginDisplay} margin)`;
    }
    
    return {
      icon: '🟢',
      message,
      type: 'above-cost'
    };
  },
  
  /**
   * Validate barcode requirement based on config and user selection
   * @param {object} config - { globalBarcodeDisabled, userSelectedNo }
   * @returns {boolean} - true if barcode is required
   */
  isBarcodeRequired(config) {
    if (config.globalBarcodeDisabled) {
      return false;
    }
    if (config.userSelectedNo) {
      return false;
    }
    return true;
  }
};

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PricingHelpers;
}

