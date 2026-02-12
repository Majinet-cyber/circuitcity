/**
 * Gym Member Delete/Purge functionality
 * 
 * Handles deletion of gym members with confirmation modal.
 * Uses event delegation for dynamically loaded content.
 * Production-safe: no inline JS, proper CSRF handling, no CSP violations.
 */

(function() {
    'use strict';

    // Get CSRF token from cookie (Django standard)
    function getCsrfToken() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Show toast notification
    function showToast(message, type = 'success') {
        // Check if Bootstrap toast is available
        const toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            // Fallback to alert if no toast container
            alert(message);
            return;
        }

        const toastId = 'toast-' + Date.now();
        const bgClass = type === 'success' ? 'bg-success' : 'bg-danger';
        
        const toastHtml = `
            <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="d-flex">
                    <div class="toast-body">
                        ${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            </div>
        `;
        
        toastContainer.insertAdjacentHTML('beforeend', toastHtml);
        const toastElement = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
        toast.show();
        
        // Remove from DOM after hidden
        toastElement.addEventListener('hidden.bs.toast', function() {
            toastElement.remove();
        });
    }

    // Initialize modal (create if doesn't exist)
    function initModal() {
        let modal = document.getElementById('deleteMemberModal');
        if (!modal) {
            const modalHtml = `
                <div class="modal fade" id="deleteMemberModal" tabindex="-1" aria-labelledby="deleteMemberModalLabel" aria-hidden="true">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content">
                            <div class="modal-header bg-danger text-white">
                                <h5 class="modal-title" id="deleteMemberModalLabel">
                                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                                    Delete Member
                                </h5>
                                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                <div class="alert alert-danger mb-3">
                                    <strong>Warning:</strong> This will permanently delete the member and ALL related records:
                                    <ul class="mb-0 mt-2">
                                        <li>All payments</li>
                                        <li>All check-ins</li>
                                        <li>All wallet entries</li>
                                        <li>All activity logs</li>
                                    </ul>
                                    <p class="mb-0 mt-2"><strong>This action cannot be undone!</strong></p>
                                </div>

                                <div class="mb-3">
                                    <strong>Member:</strong> <span id="deleteMemberName"></span>
                                </div>

                                <div class="mb-3">
                                    <label for="deleteReason" class="form-label fw-bold">
                                        Reason for deletion <span class="text-danger">*</span>
                                    </label>
                                    <select class="form-select" id="deleteReason" required>
                                        <option value="">-- Select reason --</option>
                                        <option value="duplicate">Duplicate entry</option>
                                        <option value="entered_by_mistake">Entered by mistake</option>
                                        <option value="requested_removal">Member requested removal</option>
                                        <option value="other">Other</option>
                                    </select>
                                </div>

                                <div class="mb-3">
                                    <label for="deleteNotes" class="form-label">Additional notes (optional)</label>
                                    <textarea class="form-control" id="deleteNotes" rows="2" placeholder="Any additional context..."></textarea>
                                </div>

                                <div class="mb-3">
                                    <label for="deleteConfirmation" class="form-label fw-bold">
                                        Type <code>DELETE</code> to confirm <span class="text-danger">*</span>
                                    </label>
                                    <input type="text" class="form-control" id="deleteConfirmation" placeholder="Type DELETE" required>
                                    <div class="form-text">This ensures you understand this action is permanent.</div>
                                </div>

                                <div id="deleteError" class="alert alert-danger d-none"></div>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                                <button type="button" class="btn btn-danger" id="confirmDeleteBtn">
                                    <i class="bi bi-trash-fill me-1"></i>
                                    Delete Member
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            modal = document.getElementById('deleteMemberModal');
        }
        return modal;
    }

    // Show delete modal
    function showDeleteModal(memberId, memberName, deleteUrl) {
        const modal = initModal();
        const bsModal = new bootstrap.Modal(modal);

        // Set member name
        document.getElementById('deleteMemberName').textContent = memberName;

        // Reset form
        document.getElementById('deleteReason').value = '';
        document.getElementById('deleteNotes').value = '';
        document.getElementById('deleteConfirmation').value = '';
        document.getElementById('deleteError').classList.add('d-none');

        // Store data on confirm button
        const confirmBtn = document.getElementById('confirmDeleteBtn');
        confirmBtn.dataset.memberId = memberId;
        confirmBtn.dataset.memberName = memberName;
        confirmBtn.dataset.deleteUrl = deleteUrl;

        // Show modal
        bsModal.show();
    }

    // Handle delete confirmation
    function handleDeleteConfirm(e) {
        const btn = e.target;
        const memberId = btn.dataset.memberId;
        const memberName = btn.dataset.memberName;
        const deleteUrl = btn.dataset.deleteUrl;

        // Get form values
        const reason = document.getElementById('deleteReason').value.trim();
        const notes = document.getElementById('deleteNotes').value.trim();
        const confirmation = document.getElementById('deleteConfirmation').value.trim();
        const errorDiv = document.getElementById('deleteError');

        // Validate
        if (!reason) {
            errorDiv.textContent = 'Please select a reason for deletion';
            errorDiv.classList.remove('d-none');
            return;
        }

        if (confirmation !== 'DELETE') {
            errorDiv.textContent = 'Please type DELETE to confirm';
            errorDiv.classList.remove('d-none');
            return;
        }

        // Hide error
        errorDiv.classList.add('d-none');

        // Disable button and show loading
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Deleting...';

        // Prepare form data
        const formData = new FormData();
        formData.append('reason', reason);
        formData.append('notes', notes);
        formData.append('confirmation', confirmation);

        // Send DELETE request
        fetch(deleteUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: formData,
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || 'Failed to delete member');
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.ok) {
                // Close modal
                const modal = bootstrap.Modal.getInstance(document.getElementById('deleteMemberModal'));
                modal.hide();

                // Show success message
                showToast(data.message || 'Member deleted successfully', 'success');

                // Remove row from table if on list page
                const row = document.querySelector(`tr[data-member-id="${memberId}"]`);
                if (row) {
                    row.style.transition = 'opacity 0.3s';
                    row.style.opacity = '0';
                    setTimeout(() => row.remove(), 300);
                }

                // Redirect if on detail page
                if (window.location.pathname.includes('/member/')) {
                    setTimeout(() => {
                        window.location.href = '/gym/members/';
                    }, 1500);
                }
            } else {
                throw new Error(data.error || 'Failed to delete member');
            }
        })
        .catch(error => {
            console.error('Delete error:', error);
            errorDiv.textContent = error.message || 'An error occurred while deleting the member';
            errorDiv.classList.remove('d-none');
            
            // Re-enable button
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-trash-fill me-1"></i>Delete Member';
        });
    }

    // Event delegation for delete buttons
    document.addEventListener('click', function(e) {
        // Check if clicked element or its parent is a delete button
        const deleteBtn = e.target.closest('.js-delete-member');
        if (deleteBtn) {
            e.preventDefault();
            e.stopPropagation();

            const memberId = deleteBtn.dataset.memberId;
            const memberName = deleteBtn.dataset.memberName;
            const deleteUrl = deleteBtn.dataset.deleteUrl;

            if (memberId && memberName && deleteUrl) {
                showDeleteModal(memberId, memberName, deleteUrl);
            }
        }

        // Handle confirm button in modal
        if (e.target.id === 'confirmDeleteBtn') {
            handleDeleteConfirm(e);
        }
    });

    // Initialize toast container if it doesn't exist
    document.addEventListener('DOMContentLoaded', function() {
        if (!document.getElementById('toast-container')) {
            const container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            container.style.zIndex = '9999';
            document.body.appendChild(container);
        }
    });

})();













