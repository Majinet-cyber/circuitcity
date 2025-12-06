# Agent Invite Location Fix - Implementation Summary

## Overview
Fixed the AGENT invite accept flow so that agents are ALWAYS tied to a default location for their business without requiring managers to pick a location in the invite UI.

## Problem Fixed
When accepting an invite, user creation succeeded but membership creation failed with:
```
django.core.exceptions.ValidationError: {'location': ['Agents must be assigned to a location.']}
```

## Solution Implemented

### 1. Default Location Helper Function
**File:** `tenants/services/invites.py`

Created `get_default_location_for_business(business)` that:
- Returns a location with name matching business.name (case-insensitive)
- OR returns the first location for the business (stable order by ID)
- OR creates a new location with sensible defaults (name=business.name)
- **Never returns None** (guaranteed to provide a valid location)

### 2. Updated Invite Accept Service
**File:** `tenants/services/invites.py` - `accept_invite_by_token()`

- For AGENT role, automatically assigns default location if invite doesn't specify one
- Ensures membership always has a non-null location before saving
- Idempotent: handles existing memberships without location by updating them

### 3. Updated AgentInvite Model Method
**File:** `tenants/models.py` - `AgentInvite.attach_user_as_agent()`

- Uses the same default location helper
- Ensures location is set before creating membership
- Updates invite's location field for consistency

### 4. Fixed Template Context Warnings
**File:** `tenants/views_invites.py` - `accept_invite()`

- Added `active_tab`, `show_search`, and `error` to all context dictionaries
- Eliminates VariableDoesNotExist warnings when rendering invite templates

### 5. Comprehensive Tests
**File:** `tests/test_agents_and_invites.py`

Added new test class `AgentDefaultLocationTestCase` with tests for:
- Business with no locations → creates default location
- Business with existing locations → uses first location
- Business with location matching name → uses matching location
- Helper function behavior (direct testing)
- Membership validation passes WITH location
- Membership validation fails WITHOUT location

## Verification Results

All core logic verified working:
- ✅ Default location creation when business has none
- ✅ Location selection based on matching name
- ✅ Fallback to first location when no match
- ✅ Agent membership validation passes with location
- ✅ Validation correctly fails without location (enforcement still active)

## Business Rules Maintained

1. **Managers**: location remains NULL (business-wide access)
2. **Agents**: location is ALWAYS set (scoped to that store/branch)
3. **Validation**: The existing rule "Agents must be assigned to a location" remains enforced
4. **Multiple memberships**: An agent can have multiple memberships (one per location)

## Impact

### Before
- Agent invite acceptance failed with ValidationError
- Membership creation was blocked
- Agents couldn't join via invite flow

### After
- Agent invite acceptance works automatically
- Every agent gets a valid default location
- Managers can transfer agents later using existing UI
- No changes needed to invite creation forms

## Files Modified

1. `tenants/services/invites.py` - Added helper + updated accept logic
2. `tenants/models.py` - Updated AgentInvite.attach_user_as_agent()
3. `tenants/views_invites.py` - Fixed template context warnings
4. `tests/test_agents_and_invites.py` - Added comprehensive tests

## Key Improvements

1. **Automatic**: No manager action required
2. **Safe**: Never breaks validation rules
3. **Idempotent**: Works on repeat calls
4. **Smart**: Prefers location matching business name
5. **Fallback**: Creates location if none exists
6. **Tested**: Comprehensive test coverage

## Migration Notes

- No database migrations required
- No changes to existing data
- Backward compatible with existing invites
- Works with both new and existing businesses

## Next Steps (Optional)

- Managers can use existing transfer UI to reassign agents
- No changes needed to invite creation process
- The fix is transparent to end users

