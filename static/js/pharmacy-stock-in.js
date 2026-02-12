/**
 * Pharmacy Stock-In - Progressive Enhancement JavaScript
 * 
 * CRITICAL: This file ONLY provides UX enhancements.
 * The page MUST work without JavaScript (progressive enhancement).
 * NO step gating, NO required state management.
 */

(function() {
  'use strict';
  
  // ===== UTILITY FUNCTIONS =====
  
  function updateSummary(field, value) {
    const summaryEl = document.getElementById(`summary-${field}`);
    if (summaryEl) {
      summaryEl.textContent = value;
    }
  }
  
  function scrollToSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (section) {
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
  
  // ===== CATEGORY SEARCH FILTER =====
  
  function setupCategorySearch() {
    const searchInput = document.getElementById('category-search');
    const cards = document.querySelectorAll('.category-card');
    
    if (!searchInput) return;
    
    searchInput.addEventListener('input', function() {
      const query = this.value.toLowerCase();
      cards.forEach(card => {
        const label = card.querySelector('.label');
        if (label && label.textContent.toLowerCase().includes(query)) {
          card.style.display = 'block';
        } else {
          card.style.display = 'none';
        }
      });
    });
  }
  
  // ===== PRODUCT SELECTION =====
  
  function setupProductSelection() {
    const productCards = document.querySelectorAll('.product-card[data-product-id]');
    const createNewCard = document.getElementById('create-new-card');
    const productNameInput = document.getElementById('product-name');
    
    // Handle existing product selection
    productCards.forEach(card => {
      card.addEventListener('click', function() {
        const productName = this.getAttribute('data-product-name');
        
        // Visual feedback
        productCards.forEach(c => c.classList.remove('selected'));
        this.classList.add('selected');
        
        // Fill product name
        if (productNameInput && productName) {
          productNameInput.value = productName;
          updateSummary('product', productName);
        }
        
        // Scroll to barcode section
        setTimeout(() => {
          const barcodeSection = document.querySelector('.section-card:has(#barcode-section)');
          if (barcodeSection) {
            barcodeSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        }, 200);
      });
    });
    
    // Handle "Create New" card
    if (createNewCard) {
      createNewCard.addEventListener('click', function() {
        productCards.forEach(c => c.classList.remove('selected'));
        if (productNameInput) {
          productNameInput.value = '';
          productNameInput.focus();
          updateSummary('product', '—');
        }
        
        // Scroll to barcode section
        setTimeout(() => {
          const barcodeSection = document.querySelector('.section-card:has(#barcode-section)');
          if (barcodeSection) {
            barcodeSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        }, 200);
      });
    }
  }
  
  // ===== PRODUCT SEARCH FILTER =====
  
  function setupProductSearch() {
    const searchInput = document.getElementById('product-search');
    const productCards = document.querySelectorAll('.product-card[data-product-id]');
    const createCard = document.getElementById('create-new-card');
    
    if (!searchInput) return;
    
    searchInput.addEventListener('input', function() {
      const query = this.value.toLowerCase();
      
      productCards.forEach(card => {
        const productName = card.getAttribute('data-product-name') || '';
        if (productName.toLowerCase().includes(query)) {
          card.style.display = 'block';
        } else {
          card.style.display = 'none';
        }
      });
      
      // Always show "Create New" card when searching
      if (createCard) {
        createCard.style.display = 'flex';
      }
    });
  }
  
  // ===== BARCODE MODE SELECTION =====
  
  function setupBarcodeMode() {
    const choiceCards = document.querySelectorAll('.choice-card[data-barcode]');
    const hiddenInput = document.getElementById('has-barcode-hidden');
    const barcodeSection = document.getElementById('barcode-section');
    const barcodeInput = document.getElementById('barcode-input');
    
    choiceCards.forEach(card => {
      card.addEventListener('click', function() {
        const mode = this.getAttribute('data-barcode');
        
        // Visual feedback
        choiceCards.forEach(c => c.classList.remove('selected'));
        this.classList.add('selected');
        
        // Update hidden field
        if (hiddenInput) {
          hiddenInput.value = mode;
        }
        
        // Show/hide barcode input
        if (mode === 'yes') {
          if (barcodeSection) {
            barcodeSection.classList.remove('hidden');
          }
          if (barcodeInput) {
            barcodeInput.required = true;
            setTimeout(() => barcodeInput.focus(), 100);
          }
          updateSummary('barcode', 'Scan Barcode');
        } else {
          if (barcodeSection) {
            barcodeSection.classList.add('hidden');
          }
          if (barcodeInput) {
            barcodeInput.required = false;
            barcodeInput.value = '';
          }
          updateSummary('barcode', 'No Barcode');
        }
      });
    });
  }
  
  // ===== REAL-TIME SUMMARY UPDATES =====
  
  function setupSummaryUpdates() {
    const productNameInput = document.getElementById('product-name');
    const quantityInput = document.getElementById('quantity');
    const costInput = document.getElementById('cost-price');
    const sellingInput = document.getElementById('selling-price');
    const expiryInput = document.getElementById('expiry-date');
    
    if (productNameInput) {
      productNameInput.addEventListener('input', function() {
        updateSummary('product', this.value || '—');
      });
    }
    
    if (quantityInput) {
      quantityInput.addEventListener('input', function() {
        updateSummary('quantity', this.value || '—');
      });
    }
    
    if (costInput) {
      costInput.addEventListener('input', function() {
        updateSummary('cost', this.value ? `K${parseFloat(this.value).toFixed(2)}` : '—');
      });
    }
    
    if (sellingInput) {
      sellingInput.addEventListener('input', function() {
        updateSummary('selling', this.value ? `K${parseFloat(this.value).toFixed(2)}` : '—');
      });
    }
    
    if (expiryInput) {
      expiryInput.addEventListener('input', function() {
        updateSummary('expiry', this.value || '—');
      });
    }
  }
  
  // ===== PRICE HELPERS =====
  
  function setupPriceHelpers() {
    const helperButtons = document.querySelectorAll('.chip-btn[data-margin]');
    const costInput = document.getElementById('cost-price');
    const sellingInput = document.getElementById('selling-price');
    
    helperButtons.forEach(button => {
      button.addEventListener('click', function() {
        const margin = parseInt(this.getAttribute('data-margin'));
        const cost = parseFloat(costInput.value) || 0;
        
        if (cost === 0) {
          alert('Please enter a cost price first');
          costInput.focus();
          return;
        }
        
        let selling;
        if (margin === 0) {
          // Match cost
          selling = cost;
        } else {
          // Apply markup
          selling = cost * (1 + margin / 100);
        }
        
        sellingInput.value = selling.toFixed(2);
        updateSummary('selling', `K${selling.toFixed(2)}`);
        
        // Visual feedback
        sellingInput.style.borderColor = '#10b981';
        sellingInput.style.boxShadow = '0 0 0 3px rgba(16, 185, 129, 0.3)';
        setTimeout(() => {
          sellingInput.style.borderColor = '';
          sellingInput.style.boxShadow = '';
        }, 1000);
      });
    });
  }
  
  // ===== AUTO-GENERATE BATCH NUMBER =====
  
  function setupBatchAutoGenerate() {
    const autoBtn = document.getElementById('auto-batch-btn');
    const batchInput = document.getElementById('batch-number');
    
    if (!autoBtn || !batchInput) return;
    
    autoBtn.addEventListener('click', function() {
      const today = new Date();
      const year = today.getFullYear();
      const random = Math.floor(Math.random() * 1000).toString().padStart(3, '0');
      
      const batchNumber = `BT-${year}-${random}`;
      batchInput.value = batchNumber;
      
      // Visual feedback
      batchInput.style.borderColor = '#8b5cf6';
      batchInput.style.boxShadow = '0 0 0 3px rgba(139, 92, 246, 0.3)';
      setTimeout(() => {
        batchInput.style.borderColor = '';
        batchInput.style.boxShadow = '';
      }, 1000);
    });
  }
  
  // ===== FORM VALIDATION (CLIENT-SIDE ENHANCEMENT) =====
  
  function setupFormValidation() {
    const form = document.getElementById('stock-in-form');
    
    if (!form) return;
    
    form.addEventListener('submit', function(e) {
      const productName = document.getElementById('product-name');
      const quantity = document.getElementById('quantity');
      const costPrice = document.getElementById('cost-price');
      const sellingPrice = document.getElementById('selling-price');
      const batchNumber = document.getElementById('batch-number');
      const expiryDate = document.getElementById('expiry-date');
      const hasBarcodeValue = document.getElementById('has-barcode-hidden').value;
      const barcodeInput = document.getElementById('barcode-input');
      
      // Check required fields
      if (!productName || !productName.value.trim()) {
        e.preventDefault();
        alert('Product name is required');
        if (productName) productName.focus();
        return;
      }
      
      if (!quantity || !quantity.value || parseInt(quantity.value) <= 0) {
        e.preventDefault();
        alert('Please enter a valid quantity');
        if (quantity) quantity.focus();
        return;
      }
      
      if (!costPrice || !costPrice.value || parseFloat(costPrice.value) < 0) {
        e.preventDefault();
        alert('Please enter a valid cost price');
        if (costPrice) costPrice.focus();
        return;
      }
      
      if (!sellingPrice || !sellingPrice.value || parseFloat(sellingPrice.value) < 0) {
        e.preventDefault();
        alert('Please enter a valid selling price');
        if (sellingPrice) sellingPrice.focus();
        return;
      }
      
      if (!batchNumber || !batchNumber.value.trim()) {
        e.preventDefault();
        alert('Batch number is required');
        if (batchNumber) batchNumber.focus();
        return;
      }
      
      if (!expiryDate || !expiryDate.value) {
        e.preventDefault();
        alert('Expiry date is required for pharmacy stock');
        if (expiryDate) expiryDate.focus();
        return;
      }
      
      // Barcode validation
      if (hasBarcodeValue === 'yes') {
        if (!barcodeInput || !barcodeInput.value.trim()) {
          e.preventDefault();
          alert('Barcode is required when "Scan Barcode" is selected');
          if (barcodeInput) barcodeInput.focus();
          return;
        }
      }
    });
  }
  
  // ===== INITIALIZATION =====
  
  document.addEventListener('DOMContentLoaded', function() {
    setupCategorySearch();
    setupProductSelection();
    setupProductSearch();
    setupBarcodeMode();
    setupSummaryUpdates();
    setupPriceHelpers();
    setupBatchAutoGenerate();
    setupFormValidation();
    
    console.log('✅ Pharmacy Stock-In: Progressive enhancements loaded');
  });
  
})();






