/**
 * Location tracking for agent time logs and bonuses/penalties.
 * 
 * Usage:
 * 1. On agent signup completion: call requestLocationPermission()
 * 2. On agent dashboard: call startPeriodicPings() if location enabled
 */

const LocationTracking = {
    // Configuration
    pingIntervalMs: 5 * 60 * 1000,  // 5 minutes
    pingIntervalId: null,
    isTrackingActive: false,
    
    /**
     * Request location permission from the browser.
     * Called on agent signup completion or settings page.
     * 
     * @param {Function} onSuccess - Callback on success
     * @param {Function} onError - Callback on error
     */
    requestLocationPermission(onSuccess, onError) {
        if (!navigator.geolocation) {
            console.error("Geolocation is not supported by this browser");
            if (onError) onError("Geolocation not supported");
            return;
        }
        
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const lat = position.coords.latitude;
                const lng = position.coords.longitude;
                
                // Send coordinates to backend to enable tracking
                this.enableLocationTracking(lat, lng)
                    .then(() => {
                        console.log("Location tracking enabled successfully");
                        if (onSuccess) onSuccess(lat, lng);
                    })
                    .catch((error) => {
                        console.error("Failed to enable location tracking:", error);
                        if (onError) onError(error);
                    });
            },
            (error) => {
                console.error("Geolocation error:", error);
                let message = "Unable to get location";
                switch (error.code) {
                    case error.PERMISSION_DENIED:
                        message = "Location permission denied. Please enable location access in your browser settings.";
                        break;
                    case error.POSITION_UNAVAILABLE:
                        message = "Location information is unavailable.";
                        break;
                    case error.TIMEOUT:
                        message = "Location request timed out.";
                        break;
                }
                if (onError) onError(message);
            },
            {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 0
            }
        );
    },
    
    /**
     * Enable location tracking on the backend.
     * 
     * @param {Number} lat - Latitude
     * @param {Number} lng - Longitude
     * @returns {Promise}
     */
    async enableLocationTracking(lat, lng) {
        const response = await fetch('/tenants/location-tracking/enable/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken(),
            },
            body: JSON.stringify({
                latitude: lat,
                longitude: lng
            })
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to enable location tracking');
        }
        
        return response.json();
    },
    
    /**
     * Send a location ping to the backend.
     * 
     * @param {Number} lat - Latitude
     * @param {Number} lng - Longitude
     * @returns {Promise}
     */
    async sendLocationPing(lat, lng) {
        const response = await fetch('/timelogs/ping-location/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken(),
            },
            body: JSON.stringify({
                latitude: lat,
                longitude: lng,
                timestamp: new Date().toISOString()
            })
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to send location ping');
        }
        
        return response.json();
    },
    
    /**
     * Start periodic location pings (called on agent dashboard).
     * Only starts if location tracking is enabled.
     */
    async startPeriodicPings() {
        // Check if tracking is enabled
        const status = await this.getTrackingStatus();
        if (!status.tracking_enabled) {
            console.log("Location tracking not enabled, skipping pings");
            return;
        }
        
        console.log("Starting periodic location pings every", this.pingIntervalMs / 1000, "seconds");
        this.isTrackingActive = true;
        
        // Send first ping immediately
        this.sendPing();
        
        // Then send pings at interval
        this.pingIntervalId = setInterval(() => {
            this.sendPing();
        }, this.pingIntervalMs);
    },
    
    /**
     * Stop periodic location pings.
     */
    stopPeriodicPings() {
        console.log("Stopping periodic location pings");
        this.isTrackingActive = false;
        
        if (this.pingIntervalId) {
            clearInterval(this.pingIntervalId);
            this.pingIntervalId = null;
        }
    },
    
    /**
     * Send a single location ping.
     * @private
     */
    sendPing() {
        if (!navigator.geolocation) {
            console.error("Geolocation not supported");
            return;
        }
        
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const lat = position.coords.latitude;
                const lng = position.coords.longitude;
                
                this.sendLocationPing(lat, lng)
                    .then((data) => {
                        console.log("Location ping successful:", data);
                        
                        // Update UI if elements exist
                        this.updateLocationUI(data);
                    })
                    .catch((error) => {
                        console.error("Location ping failed:", error);
                    });
            },
            (error) => {
                console.error("Geolocation error:", error);
            },
            {
                enableHighAccuracy: false,  // Use less accurate but faster method for periodic pings
                timeout: 5000,
                maximumAge: 60000  // Accept cached position up to 1 minute old
            }
        );
    },
    
    /**
     * Get location tracking status from backend.
     * @returns {Promise}
     */
    async getTrackingStatus() {
        const response = await fetch('/tenants/location-tracking/status/', {
            headers: {
                'X-CSRFToken': this.getCsrfToken(),
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to get tracking status');
        }
        
        return response.json();
    },
    
    /**
     * Update UI elements with location data.
     * @param {Object} data - Response from ping endpoint
     * @private
     */
    updateLocationUI(data) {
        // Update location status indicator
        const statusEl = document.getElementById('location-status');
        if (statusEl) {
            statusEl.textContent = data.is_inside ? 'At Store' : 'Away';
            statusEl.className = data.is_inside ? 'badge bg-success' : 'badge bg-warning';
        }
        
        // Update on-site minutes
        const onSiteEl = document.getElementById('on-site-minutes');
        if (onSiteEl) {
            onSiteEl.textContent = data.on_site_minutes || 0;
        }
        
        // Update idle minutes
        const idleEl = document.getElementById('idle-minutes');
        if (idleEl) {
            idleEl.textContent = data.idle_minutes || 0;
        }
        
        // Update bonus/penalty display
        const bonusEl = document.getElementById('bonus-amount');
        if (bonusEl) {
            bonusEl.textContent = this.formatCurrency(data.bonus_amount || 0);
        }
        
        const penaltyEl = document.getElementById('penalty-amount');
        if (penaltyEl) {
            penaltyEl.textContent = this.formatCurrency(data.penalty_amount || 0);
        }
        
        // Emit custom event for other components to listen to
        document.dispatchEvent(new CustomEvent('locationPingUpdated', {
            detail: data
        }));
    },
    
    /**
     * Format currency (MWK).
     * @param {Number|String} amount
     * @returns {String}
     */
    formatCurrency(amount) {
        return new Intl.NumberFormat('en-MW', {
            style: 'currency',
            currency: 'MWK',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(amount);
    },
    
    /**
     * Get CSRF token from cookie.
     * @returns {String}
     */
    getCsrfToken() {
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
};

// Auto-start tracking on agent dashboard pages
document.addEventListener('DOMContentLoaded', () => {
    // Check if this is an agent dashboard page
    const isDashboard = document.body.classList.contains('agent-dashboard') ||
                       document.getElementById('agent-dashboard-container');
    
    if (isDashboard) {
        LocationTracking.startPeriodicPings();
    }
    
    // Stop pings when page is hidden (to save battery)
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            LocationTracking.stopPeriodicPings();
        } else if (isDashboard) {
            LocationTracking.startPeriodicPings();
        }
    });
});

// Export for use in other scripts
window.LocationTracking = LocationTracking;

