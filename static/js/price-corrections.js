/**
 * PHASE 4: Price Corrections UI
 * Modal-based price editing for managers
 */

// ============================================================================
// UNSOLD ITEM PRICE EDIT MODAL
// ============================================================================

function openEditPricesModal(itemId, currentOrderPrice, currentSellingPrice, imei) {
  const modal = document.getElementById('editPricesModal');
  if (!modal) {
    console.error('Edit prices modal not found');
    return;
  }
  
  // Reset form
  const form = document.getElementById('editPricesForm');
  form.reset();
  
  // Set current values
  document.getElementById('editItemId').value = itemId;
  document.getElementById('editCurrentOrderPrice').textContent = `K${parseFloat(currentOrderPrice).toFixed(2)}`;
  document.getElementById('editCurrentSellingPrice').textContent = currentSellingPrice ? `K${parseFloat(currentSellingPrice).toFixed(2)}` : 'Not set';
  document.getElementById('editItemIMEI').textContent = imei || 'No IMEI';
  
  // Pre-fill inputs with current values
  document.getElementById('editOrderPrice').value = parseFloat(currentOrderPrice).toFixed(2);
  if (currentSellingPrice) {
    document.getElementById('editSellingPrice').value = parseFloat(currentSellingPrice).toFixed(2);
  }
  
  // Show modal
  modal.style.display = 'flex';
}

function closeEditPricesModal() {
  const modal = document.getElementById('editPricesModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

function submitEditPrices() {
  const itemId = document.getElementById('editItemId').value;
  const orderPrice = document.getElementById('editOrderPrice').value;
  const sellingPrice = document.getElementById('editSellingPrice').value;
  const reason = document.getElementById('editReason').value.trim();
  
  // Validation
  if (!reason || reason.length < 5) {
    alert('Please provide a reason (at least 5 characters)');
    return;
  }
  
  if (!orderPrice && !sellingPrice) {
    alert('Please change at least one price');
    return;
  }
  
  // Disable submit button
  const submitBtn = document.getElementById('editPricesSubmitBtn');
  const originalText = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = 'Saving...';
  
  // Get CSRF token
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
  
  // Submit via fetch
  fetch(`/inventory/api/stock/${itemId}/edit-prices/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-CSRFToken': csrfToken
    },
    body: new URLSearchParams({
      order_price: orderPrice,
      selling_price: sellingPrice,
      reason: reason
    })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert(`✅ Prices updated successfully!\n\nOld Cost: K${data.old_order_price}\nNew Cost: K${data.new_order_price}\n\nOld Selling: K${data.old_selling_price || 'N/A'}\nNew Selling: K${data.new_selling_price || 'N/A'}\n\nAudit ID: #${data.audit_id}`);
      closeEditPricesModal();
      // Reload page to show updated prices
      location.reload();
    } else {
      alert(`❌ Error: ${data.error}`);
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  })
  .catch(error => {
    alert(`❌ Network error: ${error.message}`);
    submitBtn.disabled = false;
    submitBtn.textContent = originalText;
  });
}

// ============================================================================
// SOLD ITEM PRICE ADJUSTMENT MODAL
// ============================================================================

function openAdjustPriceModal(saleId, currentSellingPrice, currentCost, agentName) {
  const modal = document.getElementById('adjustPriceModal');
  if (!modal) {
    console.error('Adjust price modal not found');
    return;
  }
  
  // Reset form
  const form = document.getElementById('adjustPriceForm');
  form.reset();
  
  // Set current values
  document.getElementById('adjustSaleId').value = saleId;
  document.getElementById('adjustCurrentSellingPrice').textContent = `K${parseFloat(currentSellingPrice).toFixed(2)}`;
  document.getElementById('adjustCurrentCost').textContent = currentCost ? `K${parseFloat(currentCost).toFixed(2)}` : 'Unknown';
  document.getElementById('adjustAgentName').textContent = agentName || 'No agent';
  
  // Pre-fill inputs with current values
  document.getElementById('adjustSellingPrice').value = parseFloat(currentSellingPrice).toFixed(2);
  if (currentCost) {
    document.getElementById('adjustCostPrice').value = parseFloat(currentCost).toFixed(2);
  }
  
  // Show/hide commission warning
  const commissionWarning = document.getElementById('commissionWarning');
  if (agentName && agentName !== 'No agent') {
    commissionWarning.style.display = 'block';
  } else {
    commissionWarning.style.display = 'none';
  }
  
  // Show modal
  modal.style.display = 'flex';
}

function closeAdjustPriceModal() {
  const modal = document.getElementById('adjustPriceModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

function submitAdjustPrice() {
  const saleId = document.getElementById('adjustSaleId').value;
  const sellingPrice = document.getElementById('adjustSellingPrice').value;
  const costPrice = document.getElementById('adjustCostPrice').value;
  const reason = document.getElementById('adjustReason').value.trim();
  
  // Validation
  if (!reason || reason.length < 10) {
    alert('Please provide a detailed reason (at least 10 characters)');
    return;
  }
  
  if (!sellingPrice && !costPrice) {
    alert('Please change at least one price');
    return;
  }
  
  // Confirm action
  if (!confirm('⚠️ This will create an immutable audit record and may adjust agent commission. Continue?')) {
    return;
  }
  
  // Disable submit button
  const submitBtn = document.getElementById('adjustPriceSubmitBtn');
  const originalText = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = 'Adjusting...';
  
  // Get CSRF token
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
  
  // Submit via fetch
  fetch(`/sales/${saleId}/adjust-price/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-CSRFToken': csrfToken
    },
    body: new URLSearchParams({
      selling_price: sellingPrice,
      cost_price: costPrice,
      reason: reason
    })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      let message = `✅ Price adjusted successfully!\n\nOriginal Selling: K${data.original_selling_price}\nNew Selling: K${data.new_selling_price}`;
      
      if (data.original_cost_price) {
        message += `\n\nOriginal Cost: K${data.original_cost_price}\nNew Cost: K${data.new_cost_price}`;
      }
      
      if (data.commission_delta_display && data.commission_delta_display !== 'K0.00') {
        message += `\n\n💰 Commission Adjustment: ${data.commission_delta_display}`;
      }
      
      message += `\n\nAdjustment ID: #${data.adjustment_id}`;
      
      alert(message);
      closeAdjustPriceModal();
      // Reload page to show updated values
      location.reload();
    } else {
      alert(`❌ Error: ${data.error}`);
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  })
  .catch(error => {
    alert(`❌ Network error: ${error.message}`);
    submitBtn.disabled = false;
    submitBtn.textContent = originalText;
  });
}

// Close modals when clicking outside
window.onclick = function(event) {
  const editModal = document.getElementById('editPricesModal');
  const adjustModal = document.getElementById('adjustPriceModal');
  
  if (event.target === editModal) {
    closeEditPricesModal();
  }
  if (event.target === adjustModal) {
    closeAdjustPriceModal();
  }
};

