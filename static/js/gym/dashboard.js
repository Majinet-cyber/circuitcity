/**
 * Gym Dashboard Polish - Premium Interactions
 * Subtle animations, count-up effects, smooth micro-interactions
 */

(function() {
  'use strict';

  // Check for reduced motion preference
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /**
   * Count-up animation for KPI numbers
   * Animates numbers from 0 to target value with easing
   */
  function animateCountUp(element, target, duration = 1000) {
    if (prefersReducedMotion) {
      element.textContent = target;
      return;
    }

    const start = 0;
    const startTime = performance.now();
    const isDecimal = target.toString().includes('.');
    const isMoney = element.textContent.includes('K') || element.textContent.includes('MWK');
    
    // Parse target value (strip commas, K suffix, currency symbols)
    let numericTarget = target.toString().replace(/[^0-9.-]/g, '');
    
    // Check if it's a "K" formatted number
    const hasKSuffix = target.toString().includes('K');
    if (hasKSuffix) {
      numericTarget = parseFloat(numericTarget);
    } else {
      numericTarget = parseFloat(numericTarget);
    }

    // Don't animate if not a valid number
    if (isNaN(numericTarget)) {
      return;
    }

    function easeOutCubic(t) {
      return 1 - Math.pow(1 - t, 3);
    }

    function updateNumber(currentTime) {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const easedProgress = easeOutCubic(progress);
      const current = start + (numericTarget - start) * easedProgress;

      // Format the number based on original format
      let formattedValue;
      if (hasKSuffix) {
        formattedValue = current.toFixed(1) + 'K';
      } else if (isMoney) {
        formattedValue = Math.round(current).toLocaleString();
      } else if (isDecimal) {
        formattedValue = current.toFixed(1);
      } else {
        formattedValue = Math.round(current).toLocaleString();
      }

      element.textContent = formattedValue;

      if (progress < 1) {
        requestAnimationFrame(updateNumber);
      } else {
        // Ensure we end with the exact target value
        element.textContent = target;
      }
    }

    requestAnimationFrame(updateNumber);
  }

  /**
   * Initialize count-up animations for elements with data-count attribute
   */
  function initCountUpAnimations() {
    const countElements = document.querySelectorAll('[data-count]');
    
    countElements.forEach((element, index) => {
      const targetValue = element.getAttribute('data-count');
      
      // Don't animate empty or placeholder values
      if (!targetValue || targetValue === '0' || targetValue === '—' || targetValue === '-') {
        return;
      }

      // Stagger the animations
      const delay = prefersReducedMotion ? 0 : index * 100;
      
      setTimeout(() => {
        animateCountUp(element, targetValue, 1200);
      }, delay);
    });
  }

  /**
   * Animate payment mix progress bars
   */
  function animatePaymentBars() {
    const bars = document.querySelectorAll('.payment-bar');
    
    bars.forEach((bar, index) => {
      const targetWidth = bar.getAttribute('data-width');
      
      if (!targetWidth) return;

      if (prefersReducedMotion) {
        bar.style.width = targetWidth + '%';
        return;
      }

      // Start with 0 width
      bar.style.width = '0%';
      
      // Animate to target width with stagger
      setTimeout(() => {
        bar.style.width = targetWidth + '%';
      }, 100 + (index * 80));
    });
  }

  /**
   * Initialize Bootstrap tooltips
   */
  function initTooltips() {
    if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
      const tooltipTriggerList = [].slice.call(
        document.querySelectorAll('[data-bs-toggle="tooltip"]')
      );
      
      tooltipTriggerList.forEach(function(tooltipTriggerEl) {
        new bootstrap.Tooltip(tooltipTriggerEl);
      });
    }
  }

  /**
   * Add subtle hover effect to interactive cards
   */
  function initCardInteractions() {
    const cards = document.querySelectorAll('.metric-card, .recent-item');
    
    cards.forEach(card => {
      card.addEventListener('mouseenter', function() {
        if (!prefersReducedMotion) {
          this.style.transition = 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
        }
      });
    });
  }

  /**
   * Observe elements entering viewport for animation trigger
   * (Optional enhancement for long pages)
   */
  function initIntersectionObserver() {
    if ('IntersectionObserver' in window && !prefersReducedMotion) {
      const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
      };

      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
            observer.unobserve(entry.target);
          }
        });
      }, observerOptions);

      // Observe recent blocks that are far down the page
      const recentBlocks = document.querySelectorAll('.recent-block');
      recentBlocks.forEach((block, index) => {
        if (index > 2) { // Only observe blocks after the first 2
          block.style.opacity = '0';
          block.style.transform = 'translateY(20px)';
          block.style.transition = 'all 0.5s cubic-bezier(0.4, 0, 0.2, 1)';
          observer.observe(block);
        }
      });
    }
  }

  /**
   * Add smooth scroll behavior to anchor links
   */
  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
      anchor.addEventListener('click', function(e) {
        const targetId = this.getAttribute('href');
        if (targetId === '#') return;
        
        const target = document.querySelector(targetId);
        if (target) {
          e.preventDefault();
          target.scrollIntoView({
            behavior: prefersReducedMotion ? 'auto' : 'smooth',
            block: 'start'
          });
        }
      });
    });
  }

  /**
   * Initialize all dashboard enhancements
   */
  function init() {
    // Wait for DOM to be fully loaded
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
      return;
    }

    // Initialize all features
    initTooltips();
    initCountUpAnimations();
    animatePaymentBars();
    initCardInteractions();
    initIntersectionObserver();
    initSmoothScroll();

    // Log initialization (only in development)
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      console.log('✨ Gym Dashboard polish initialized');
    }
  }

  // Auto-initialize
  init();

  // Expose refresh function for dynamic content updates
  window.gymDashboard = {
    refresh: function() {
      initCountUpAnimations();
      animatePaymentBars();
      initTooltips();
    }
  };

})();








