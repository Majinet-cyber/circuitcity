/**
 * Corrections Modal Handler (Feb 2026)
 * =====================================
 * 
 * Ensures delete modal is properly initialized and clickable in production.
 * 
 * PROBLEM SOLVED:
 * - Delete button not clickable in production
 * - Modal not opening when button is clicked
 * - Conflicts with emajinet-ui-init.js modal cleanup
 * 
 * ROOT CAUSE:
 * - emajinet-ui-init.js resets all modals on page load
 * - Bootstrap modal data attributes need explicit initialization
 * - Z-index/overlay issues in production environment
 * 
 * SOLUTION:
 * - Explicit modal initialization after DOM ready
 * - Re-initialize after emajinet-ui-init cleanup
 * - Ensure proper event delegation
 * - Validate button is clickable (not covered by overlay)
 */

(function () {
  'use strict';

  const CorrectionsModal = {
    __initialized: false,
    __version: '1.0.0',

    /**
     * Initialize delete modal for gym_payment corrections
     */
    init: function () {
      console.log('[CorrectionsModal] Initializing v' + this.__version);

      // Wait for Bootstrap to be available
      this._waitForBootstrap(function () {
        CorrectionsModal.initDeleteModal();
        CorrectionsModal.__initialized = true;
        console.log('[CorrectionsModal] Initialization complete');
      });
    },

    /**
     * Initialize the delete modal
     */
    initDeleteModal: function () {
      const deleteBtn = document.querySelector('[data-bs-target="#deleteModal"]');
      const deleteModal = document.getElementById('deleteModal');

      if (!deleteBtn || !deleteModal) {
        console.log('[CorrectionsModal] Delete modal elements not found on this page');
        return;
      }

      console.log('[CorrectionsModal] Initializing delete modal');

      // Ensure modal is properly hidden initially
      deleteModal.classList.remove('show');
      deleteModal.style.display = 'none';
      deleteModal.setAttribute('aria-hidden', 'true');

      // Remove any existing Bootstrap modal instance
      const existingModal = bootstrap.Modal.getInstance(deleteModal);
      if (existingModal) {
        try {
          existingModal.dispose();
          console.log('[CorrectionsModal] Disposed existing modal instance');
        } catch (e) {
          console.warn('[CorrectionsModal] Error disposing modal:', e);
        }
      }

      // Create new Bootstrap modal instance with proper configuration
      try {
        const modalInstance = new bootstrap.Modal(deleteModal, {
          backdrop: true,
          keyboard: true,
          focus: true
        });

        console.log('[CorrectionsModal] Modal instance created');

        // Add explicit click handler to delete button (fallback if data attributes fail)
        deleteBtn.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          
          console.log('[CorrectionsModal] Delete button clicked');
          
          // Validate button is not disabled
          if (deleteBtn.disabled || deleteBtn.hasAttribute('disabled')) {
            console.warn('[CorrectionsModal] Delete button is disabled');
            return;
          }

          // Show the modal
          try {
            modalInstance.show();
            console.log('[CorrectionsModal] Modal shown');
          } catch (err) {
            console.error('[CorrectionsModal] Error showing modal:', err);
          }
        });

        // Add event listeners for modal lifecycle
        deleteModal.addEventListener('show.bs.modal', function () {
          console.log('[CorrectionsModal] Modal is showing');
          
          // Clear any previous validation states
          const deleteForm = document.getElementById('deleteForm');
          if (deleteForm) {
            deleteForm.classList.remove('was-validated');
            
            // Reset form fields
            const reasonSelect = document.getElementById('delete_reason');
            const notesTextarea = document.getElementById('delete_notes');
            if (reasonSelect) reasonSelect.value = '';
            if (notesTextarea) notesTextarea.value = '';
          }
        });

        deleteModal.addEventListener('shown.bs.modal', function () {
          console.log('[CorrectionsModal] Modal is shown');
          
          // Focus on reason select
          const reasonSelect = document.getElementById('delete_reason');
          if (reasonSelect) {
            setTimeout(function() {
              reasonSelect.focus();
            }, 100);
          }
        });

        deleteModal.addEventListener('hide.bs.modal', function () {
          console.log('[CorrectionsModal] Modal is hiding');
        });

        deleteModal.addEventListener('hidden.bs.modal', function () {
          console.log('[CorrectionsModal] Modal is hidden');
          
          // Ensure backdrop is removed
          const backdrops = document.querySelectorAll('.modal-backdrop');
          backdrops.forEach(function (backdrop) {
            backdrop.remove();
          });
          
          // Clean up body classes
          document.body.classList.remove('modal-open');
          document.body.style.overflow = '';
          document.body.style.paddingRight = '';
        });

        // Add form validation before submit
        const deleteForm = document.getElementById('deleteForm');
        if (deleteForm) {
          deleteForm.addEventListener('submit', function (e) {
            const reasonSelect = document.getElementById('delete_reason');
            
            if (!reasonSelect || !reasonSelect.value) {
              e.preventDefault();
              e.stopPropagation();
              
              deleteForm.classList.add('was-validated');
              
              // Show error message
              if (reasonSelect) {
                reasonSelect.focus();
                reasonSelect.classList.add('is-invalid');
              }
              
              console.warn('[CorrectionsModal] Form validation failed: reason required');
              return false;
            }
            
            console.log('[CorrectionsModal] Form submitting with reason:', reasonSelect.value);
          });
        }

        // Validate button is clickable (not covered by overlay)
        this._validateButtonClickable(deleteBtn);

      } catch (e) {
        console.error('[CorrectionsModal] Failed to initialize modal:', e);
      }
    },

    /**
     * Validate that the delete button is clickable (not covered by overlay)
     */
    _validateButtonClickable: function (button) {
      try {
        const rect = button.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        
        const elementAtPoint = document.elementFromPoint(centerX, centerY);
        
        if (elementAtPoint !== button && !button.contains(elementAtPoint)) {
          console.warn('[CorrectionsModal] Delete button may be covered by overlay:', elementAtPoint);
          console.warn('[CorrectionsModal] Button z-index:', window.getComputedStyle(button).zIndex);
          console.warn('[CorrectionsModal] Overlay z-index:', window.getComputedStyle(elementAtPoint).zIndex);
        } else {
          console.log('[CorrectionsModal] Delete button is clickable');
        }
      } catch (e) {
        console.warn('[CorrectionsModal] Could not validate button clickability:', e);
      }
    },

    /**
     * Helper: Wait for Bootstrap to be available
     */
    _waitForBootstrap: function (callback) {
      if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
        callback();
      } else {
        console.log('[CorrectionsModal] Waiting for Bootstrap...');
        setTimeout(function () {
          CorrectionsModal._waitForBootstrap(callback);
        }, 50);
      }
    },

    /**
     * Reinitialize after emajinet-ui-init cleanup
     */
    reinit: function () {
      if (this.__initialized) {
        console.log('[CorrectionsModal] Reinitializing after UI cleanup');
        this.initDeleteModal();
      }
    }
  };

  // Expose globally
  window.CorrectionsModal = CorrectionsModal;

  // Auto-initialize on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      CorrectionsModal.init();
    });
  } else {
    // DOM already loaded
    CorrectionsModal.init();
  }

  // Re-initialize after emajinet-ui-init runs (it resets modals)
  // Listen for custom event or use timeout
  setTimeout(function() {
    if (window.EmajinetUI && window.EmajinetUI.__initialized) {
      console.log('[CorrectionsModal] Re-initializing after EmajinetUI');
      CorrectionsModal.reinit();
    }
  }, 500);

  // Re-initialize on pageshow (BFCache restoration)
  window.addEventListener('pageshow', function (event) {
    if (event.persisted) {
      console.log('[CorrectionsModal] Page restored from BFCache, reinitializing');
      CorrectionsModal.init();
    }
  });

  console.log('[CorrectionsModal] Module loaded');
})();

