        # POLISH: Check for reload-once guard (prevent loops)
        assert "cc_sw_reloaded" in content, \
            "Must have reload guard sessionStorage key to prevent loops"
        assert "reloadOnce" in content, \
            "Must have reloadOnce() function to prevent reload loops"
        assert "sessionStorage.getItem" in content, \
            "Must check sessionStorage before reloading"

    def test_base_template_has_single_sw_registration(self):
        """
        CRITICAL: Must register service worker exactly once, no duplicates.
        Must use /sw.js (dynamic endpoint), not static/sw.js.
        """
        from django.contrib.auth import get_user_model
        from tenants.models import Business, Membership
        from circuitcity.accounts.models import Profile
        from inventory.business_kinds import BusinessKind
        
        User = get_user_model()
        client = Client()
        user = User.objects.create_user(username="testuser", password="testpass123")
        Profile.objects.get_or_create(user=user, defaults={"display_name": "Test User"})
        
        business = Business.objects.create(
            name="Test Business",
            kind=BusinessKind.PHONES,
            owner=user,
            status="ACTIVE"
        )
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE"
        )
        
        client.login(username="testuser", password="testpass123")
        session = client.session
        session['active_business_id'] = business.id
        session.save()
        
        response = client.get("/dashboard/")
        assert response.status_code == 200
        
        content = response.content.decode("utf-8")
        
        # Count serviceWorker.register calls (should be exactly 1)
        register_count = content.count("navigator.serviceWorker.register")
        assert register_count == 1, \
            f"Must have exactly 1 SW registration, found {register_count}"
        
        # Must register /sw.js (dynamic endpoint)
        assert "register('/sw.js'" in content or 'register("/sw.js"' in content, \
            "Must register /sw.js (dynamic endpoint)"
        
        # Must NOT register static/sw.js
        assert "static/sw.js" not in content, \
            "Must NOT register static/sw.js (use dynamic /sw.js instead)"

    def test_sw_headers_complete(self):
        """
        Verify /sw.js has ALL required headers for proper caching and scope.
        """
        client = Client()
        response = client.get("/sw.js")
        
        assert response.status_code == 200
        
        # Cache control headers
        cache_control = response.get("Cache-Control", "").lower()
        assert "no-cache" in cache_control or "no-store" in cache_control
        
        # Pragma and Expires (polish)
        pragma = response.get("Pragma", "").lower()
        assert pragma == "no-cache", "Should have Pragma: no-cache"
        
        expires = response.get("Expires", "")
        assert expires == "0", "Should have Expires: 0"
        
        # Service worker scope
        sw_allowed = response.get("Service-Worker-Allowed", "")
        assert sw_allowed == "/", "Service-Worker-Allowed must be /"

