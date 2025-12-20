/**
 * Gamified Add-Product Wizard Engine
 * Mobile-first, card-driven, premium UX
 * 
 * Usage:
 *   const wizard = new WizardEngine('wizard-container', {
 *     steps: [...],
 *     onComplete: (data) => { ... }
 *   });
 */

class WizardEngine {
  constructor(containerId, config) {
    this.container = document.getElementById(containerId);
    if (!this.container) {
      console.error(`Wizard container '${containerId}' not found`);
      return;
    }
    
    this.config = {
      steps: [],
      onComplete: null,
      onCancel: null,
      theme: 'default',
      ...config
    };
    
    this.currentStep = 0;
    this.data = {};
    this.history = [];
    
    this.init();
  }
  
  init() {
    this.container.classList.add('wizard-container');
    this.render();
  }
  
  render() {
    const step = this.config.steps[this.currentStep];
    if (!step) return;
    
    const html = `
      <div class="wizard-wrapper">
        <!-- Progress -->
        <div class="wizard-progress">
          <div class="wizard-progress-bar" style="width: ${((this.currentStep + 1) / this.config.steps.length) * 100}%"></div>
        </div>
        
        <!-- Step indicator -->
        <div class="wizard-header">
          <div class="wizard-step-indicator">
            <span class="wizard-step-number">Step ${this.currentStep + 1} of ${this.config.steps.length}</span>
            ${this.currentStep > 0 ? '<button class="wizard-back-btn" onclick="wizard.back()"><i class="bi bi-arrow-left"></i> Back</button>' : ''}
          </div>
          <h2 class="wizard-title">${step.title}</h2>
          ${step.subtitle ? `<p class="wizard-subtitle">${step.subtitle}</p>` : ''}
        </div>
        
        <!-- Content -->
        <div class="wizard-content" id="wizard-step-content">
          ${this.renderStepContent(step)}
        </div>
        
        <!-- Actions -->
        <div class="wizard-actions">
          ${step.skipable ? '<button class="wizard-btn wizard-btn-ghost" onclick="wizard.skip()">Skip</button>' : ''}
          ${this.config.onCancel ? '<button class="wizard-btn wizard-btn-ghost" onclick="wizard.cancel()">Cancel</button>' : ''}
        </div>
      </div>
    `;
    
    this.container.innerHTML = html;
    this.attachEventListeners();
  }
  
  renderStepContent(step) {
    switch (step.type) {
      case 'cards':
        return this.renderCards(step);
      case 'input':
        return this.renderInput(step);
      case 'multi-input':
        return this.renderMultiInput(step);
      case 'toggle':
        return this.renderToggle(step);
      case 'custom':
        return step.render(this.data);
      default:
        return '<p>Unknown step type</p>';
    }
  }
  
  renderCards(step) {
    const options = typeof step.options === 'function' ? step.options(this.data) : step.options;
    
    return `
      <div class="wizard-cards-grid ${step.columns || 'auto'}">
        ${options.map((opt, idx) => `
          <button class="wizard-card ${opt.featured ? 'wizard-card-featured' : ''}" 
                  onclick="wizard.selectCard('${step.key}', ${JSON.stringify(opt.value).replace(/"/g, '&quot;')}, ${idx})"
                  data-card-index="${idx}">
            ${opt.icon ? `<div class="wizard-card-icon">${opt.icon}</div>` : ''}
            <div class="wizard-card-label">${opt.label}</div>
            ${opt.badge ? `<div class="wizard-card-badge">${opt.badge}</div>` : ''}
            ${opt.description ? `<div class="wizard-card-description">${opt.description}</div>` : ''}
          </button>
        `).join('')}
      </div>
      ${step.allowCustom ? `
        <div class="wizard-custom-input mt-3">
          <label class="form-label">Or enter custom ${step.title.toLowerCase()}</label>
          <div class="input-group">
            <input type="text" class="form-control" id="custom-${step.key}" placeholder="${step.customPlaceholder || 'Type here...'}">
            <button class="btn btn-primary" onclick="wizard.selectCustom('${step.key}')">
              <i class="bi bi-plus-circle"></i> Add
            </button>
          </div>
        </div>
      ` : ''}
    `;
  }
  
  renderInput(step) {
    const value = this.data[step.key] || step.default || '';
    return `
      <div class="wizard-input-group">
        <label class="wizard-label">${step.label || step.title}</label>
        <input 
          type="${step.inputType || 'text'}" 
          class="wizard-input"
          id="input-${step.key}"
          value="${value}"
          placeholder="${step.placeholder || ''}"
          ${step.required ? 'required' : ''}
          ${step.min !== undefined ? `min="${step.min}"` : ''}
          ${step.max !== undefined ? `max="${step.max}"` : ''}
          ${step.step !== undefined ? `step="${step.step}"` : ''}
        >
        ${step.hint ? `<div class="wizard-hint">${step.hint}</div>` : ''}
        <button class="wizard-btn wizard-btn-primary mt-3" onclick="wizard.submitInput('${step.key}')">
          Continue <i class="bi bi-arrow-right ms-1"></i>
        </button>
      </div>
    `;
  }
  
  renderMultiInput(step) {
    return `
      <div class="wizard-multi-input-group">
        ${step.fields.map(field => {
          const value = this.data[field.key] || field.default || '';
          return `
            <div class="wizard-field-group">
              <label class="wizard-label">${field.label}</label>
              <input 
                type="${field.type || 'text'}" 
                class="wizard-input"
                id="input-${field.key}"
                value="${value}"
                placeholder="${field.placeholder || ''}"
                ${field.required ? 'required' : ''}
                ${field.min !== undefined ? `min="${field.min}"` : ''}
                ${field.max !== undefined ? `max="${field.max}"` : ''}
                ${field.step !== undefined ? `step="${field.step}"` : ''}
              >
              ${field.hint ? `<div class="wizard-hint">${field.hint}</div>` : ''}
            </div>
          `;
        }).join('')}
        <button class="wizard-btn wizard-btn-primary mt-3" onclick="wizard.submitMultiInput('${step.key}')">
          Continue <i class="bi bi-arrow-right ms-1"></i>
        </button>
      </div>
    `;
  }
  
  renderToggle(step) {
    const options = step.options;
    return `
      <div class="wizard-toggle-group">
        ${options.map((opt, idx) => `
          <button class="wizard-toggle-btn ${idx === 0 ? 'active' : ''}" 
                  onclick="wizard.selectToggle('${step.key}', '${opt.value}', ${idx})">
            ${opt.icon ? `${opt.icon} ` : ''}${opt.label}
          </button>
        `).join('')}
        <button class="wizard-btn wizard-btn-primary mt-4" onclick="wizard.submitToggle('${step.key}')">
          Continue <i class="bi bi-arrow-right ms-1"></i>
        </button>
      </div>
    `;
  }
  
  selectCard(key, value, index) {
    this.data[key] = value;
    this.history.push({ step: this.currentStep, key, value });
    
    // Visual feedback
    document.querySelectorAll('.wizard-card').forEach(c => c.classList.remove('selected'));
    const card = document.querySelector(`[data-card-index="${index}"]`);
    if (card) {
      card.classList.add('selected');
      setTimeout(() => this.next(), 300);
    }
  }
  
  selectCustom(key) {
    const input = document.getElementById(`custom-${key}`);
    if (!input || !input.value.trim()) {
      this.toast('Please enter a value', 'warning');
      return;
    }
    this.data[key] = input.value.trim();
    this.history.push({ step: this.currentStep, key, value: input.value.trim() });
    setTimeout(() => this.next(), 300);
  }
  
  submitInput(key) {
    const input = document.getElementById(`input-${key}`);
    if (!input) return;
    
    const step = this.config.steps[this.currentStep];
    if (step.required && !input.value.trim()) {
      this.toast('This field is required', 'error');
      input.focus();
      return;
    }
    
    if (step.validate) {
      const error = step.validate(input.value, this.data);
      if (error) {
        this.toast(error, 'error');
        input.focus();
        return;
      }
    }
    
    this.data[key] = input.value;
    this.history.push({ step: this.currentStep, key, value: input.value });
    this.next();
  }
  
  submitMultiInput(stepKey) {
    const step = this.config.steps[this.currentStep];
    let hasError = false;
    
    step.fields.forEach(field => {
      const input = document.getElementById(`input-${field.key}`);
      if (!input) return;
      
      if (field.required && !input.value.trim()) {
        this.toast(`${field.label} is required`, 'error');
        input.focus();
        hasError = true;
        return;
      }
      
      if (field.validate) {
        const error = field.validate(input.value, this.data);
        if (error) {
          this.toast(error, 'error');
          input.focus();
          hasError = true;
          return;
        }
      }
      
      this.data[field.key] = input.value;
    });
    
    if (!hasError) {
      this.history.push({ step: this.currentStep });
      this.next();
    }
  }
  
  submitToggle(key) {
    if (!this.data[key]) {
      // Get first active toggle
      const activeBtn = document.querySelector('.wizard-toggle-btn.active');
      if (activeBtn) {
        const value = activeBtn.textContent.trim();
        this.data[key] = value;
      }
    }
    this.history.push({ step: this.currentStep, key, value: this.data[key] });
    this.next();
  }
  
  selectToggle(key, value, index) {
    this.data[key] = value;
    document.querySelectorAll('.wizard-toggle-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.wizard-toggle-btn')[index].classList.add('active');
  }
  
  next() {
    if (this.currentStep < this.config.steps.length - 1) {
      this.currentStep++;
      this.render();
    } else {
      this.complete();
    }
  }
  
  back() {
    if (this.currentStep > 0) {
      this.currentStep--;
      this.render();
    }
  }
  
  skip() {
    const step = this.config.steps[this.currentStep];
    if (step.skipable) {
      this.data[step.key] = step.skipValue || null;
      this.next();
    }
  }
  
  cancel() {
    if (this.config.onCancel) {
      this.config.onCancel();
    }
  }
  
  complete() {
    if (this.config.onComplete) {
      this.config.onComplete(this.data);
    }
  }
  
  toast(message, type = 'info') {
    // Use existing toast system if available
    if (window.showToast) {
      window.showToast(message, type);
    } else if (window.toast) {
      window.toast(message, type);
    } else {
      alert(message);
    }
  }
  
  attachEventListeners() {
    // Handle Enter key in inputs
    this.container.querySelectorAll('.wizard-input').forEach(input => {
      input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const btn = this.container.querySelector('.wizard-btn-primary');
          if (btn) btn.click();
        }
      });
    });
  }
}

// Global wizard instance
let wizard = null;

