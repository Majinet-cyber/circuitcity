# HQ Staff Onboarding Guide

Welcome to the **Emajinet HQ Admin Portal** – your command center for platform administration!

## What is the HQ Portal?

The HQ portal provides superuser capabilities to manage the entire Emajinet platform. As HQ staff, you have visibility across all businesses, subscriptions, agents, and system-wide analytics.

---

## Getting Started

### 1. Accessing HQ

1. Log in with your HQ staff credentials
2. Navigate to `/hq/` or click **HQ Admin** in the main menu
3. You'll see the HQ Dashboard with platform-wide metrics

**Security Note:** HQ access is restricted. Never share HQ credentials.

### 2. HQ Dashboard Overview

The HQ Dashboard shows:
- **Total Businesses**: All registered merchants
- **Active Subscriptions**: Paying customers
- **Monthly Revenue**: Platform subscription income
- **Total Agents**: All users across all businesses
- **System Health**: Performance and uptime metrics

---

## Core HQ Functions

### 🏢 Business Management

**Purpose:** Oversee all merchant accounts on the platform.

**View:** `/hq/businesses/`

**Key Information:**
- Business name and contact
- Business vertical (phones, pharmacy, liquor, etc.)
- Status (Pending, Active, Suspended)
- Subscription tier
- Contract status (signed/not signed)
- Created date and activity

**Actions:**
1. **Approve New Businesses**: Review and activate pending businesses
2. **View Business Details**: Click on any business to see:
   - All locations
   - Team members (managers, agents)
   - Subscription history
   - Sales and inventory summary
   - Audit logs
3. **Suspend Businesses**: Temporarily disable access for non-payment or violations
4. **Manage Contracts**: Upload signed merchant agreements

**Best Practice:** Review new business applications within 24 hours.

---

### 📄 Merchant Contracts

**Purpose:** Store and manage signed contracts with merchants.

**View:** `/hq/contracts/`

**Workflow:**

1. **Download Template**:
   - Go to Contracts → Template
   - Download the standard merchant contract PDF
   - Customize for specific business if needed

2. **Send to Merchant**:
   - Email the contract to the business owner
   - Request signature (digital or physical)

3. **Upload Signed Contract**:
   - Click on business name in Contracts list
   - Upload the signed PDF file
   - Add notes (e.g., "Signed on Dec 5, 2025, via DocuSign")

4. **Track Status**:
   - **Signed**: Green badge, contract file available
   - **Not Signed**: Red badge, pending action

**Legal Note:** Ensure all active paying customers have signed contracts on file.

---

### 💳 Subscription Management

**Purpose:** Manage platform subscriptions and billing.

**View:** `/hq/subscriptions/`

**Subscription Tiers:**
- **Trial**: 14-day free trial (new businesses)
- **Basic**: Limited features
- **Pro**: Full features
- **Enterprise**: Custom pricing and features

**Actions:**

1. **Extend Trial**:
   - Select subscription → Extend
   - Set new trial end date
   - Useful for onboarding issues or goodwill

2. **Activate Subscription**:
   - For businesses that have paid
   - Select tier (Basic/Pro/Enterprise)
   - Set start and end dates

3. **Revoke/Suspend**:
   - For non-payment or violations
   - Business loses access immediately
   - Data is preserved for 30 days

4. **Change Plan**:
   - Upgrade or downgrade tiers
   - Pro-rate billing if applicable

**Best Practice:** Set up automated renewal reminders 7 days before expiration.

---

### 📊 Analytics & Reporting

**Purpose:** Gain insights into platform usage and performance.

**Available Views:**

1. **Stock Trends**:
   - View top products across all businesses
   - Identify trending categories
   - Spot inventory patterns

2. **Agent Performance**:
   - See all agents across the platform
   - View sales and commission metrics
   - Identify top performers

3. **Revenue Analytics**:
   - Monthly subscription revenue
   - Churn rate
   - Customer lifetime value

4. **Drill-Downs**:
   - Click any metric to see detailed breakdown
   - Filter by vertical, date range, or business

**Use Case:** Identify which verticals are most successful to guide marketing efforts.

---

### 🔍 Audit Logs

**Purpose:** Track all critical actions across the platform.

**What's Logged:**
- User logins and logouts
- Business approvals and suspensions
- Subscription changes
- Contract uploads
- Sale edits and deletions
- Data exports

**Viewing Audit Logs:**
1. Go to Audit → Logs
2. Filter by:
   - Business
   - User
   - Action type
   - Date range
3. Export for compliance or investigations

**Compliance:** Retain audit logs for at least 2 years.

---

### 👥 User & Agent Management

**Purpose:** Oversee all users on the platform.

**View:** `/hq/agents/`

**Information Available:**
- User details (name, email, phone)
- Business affiliations
- Role (owner, manager, agent, viewer)
- Activity status
- Last login
- Total sales and commissions

**Actions:**
1. **Reset Passwords**: For locked-out users
2. **Deactivate Users**: For security or offboarding
3. **Audit User Activity**: Review suspicious behavior

**Security Note:** Investigate multiple failed login attempts immediately.

---

### 📧 Platform Communications

**Purpose:** Send announcements and updates to merchants.

**Channels:**
1. **Email**: System-generated for billing and alerts
2. **WhatsApp**: Notifications for sales, low stock, etc.
3. **In-App Notifications**: Displayed in user dashboards

**Common Communications:**
- New feature announcements
- Scheduled maintenance notices
- Payment reminders
- Subscription renewal reminders
- Training webinar invitations

**Best Practice:** Schedule non-urgent communications during off-peak hours.

---

## Advanced Features

### 🔧 System Configuration

**Purpose:** Configure platform-wide settings.

**Settings:**
- Default subscription tiers and pricing
- Commission rate defaults
- WhatsApp integration settings
- Email templates
- Feature flags (enable/disable features per vertical)

**Caution:** Changes affect all businesses. Test in staging first!

---

### 📦 Data Management

**Purpose:** Export, backup, and restore data.

**Actions:**
1. **Backups**:
   - Automated daily backups
   - On-demand backups before major changes
   - Stored in secure cloud storage

2. **Exports**:
   - Export business data for migration or analysis
   - Formats: CSV, Excel, JSON
   - Anonymize data for privacy compliance

3. **Restorations**:
   - Restore deleted records within 30 days
   - Full system restore from backup (emergency only)

**GDPR Compliance:** Honor data deletion requests within 30 days.

---

## Workflows & Processes

### New Business Onboarding

**Steps:**

1. **Application Received**:
   - Review business details in `/hq/businesses/`
   - Check for completeness and legitimacy

2. **Verification**:
   - Confirm business registration (if applicable)
   - Verify contact information

3. **Contract Preparation**:
   - Download contract template
   - Send to business owner for signature

4. **Approval**:
   - Activate business (status → Active)
   - Assign trial subscription (14 days)
   - Send welcome email with login instructions

5. **Onboarding Call**:
   - Schedule a setup call
   - Walk through dashboard and key features
   - Answer questions

6. **Follow-Up**:
   - Check-in after 7 days
   - Offer training if needed
   - Collect feedback

**SLA:** Complete onboarding within 48 hours of application.

---

### Subscription Renewal

**Process:**

1. **7 Days Before Expiry**:
   - System sends renewal reminder email
   - Highlight benefits of renewal

2. **3 Days Before Expiry**:
   - Send second reminder via email and WhatsApp
   - Offer assistance with payment

3. **On Expiry Day**:
   - If not renewed, move to "grace period" (3 days read-only access)
   - Send final reminder

4. **After Grace Period**:
   - Suspend subscription
   - Disable access (data preserved for 30 days)
   - Offer reactivation options

5. **30 Days Post-Expiry**:
   - Send final reactivation offer
   - After this, data may be archived or deleted per policy

**Retention Strategy:** Offer discount or extended trial for high-value customers.

---

### Handling Support Escalations

**When to Escalate:**
- Technical bugs affecting multiple businesses
- Data corruption or loss
- Security incidents
- Billing disputes

**Steps:**

1. **Acknowledge**: Respond to merchant within 4 hours
2. **Investigate**: Gather details, check logs
3. **Escalate**: Assign to dev team if needed
4. **Communicate**: Keep merchant updated every 24 hours
5. **Resolve**: Apply fix and confirm with merchant
6. **Follow-Up**: Check in 48 hours post-resolution

**SLA:**
- **Critical** (system down): Respond in 1 hour, resolve in 4 hours
- **High** (feature broken): Respond in 4 hours, resolve in 24 hours
- **Medium** (inconvenience): Respond in 12 hours, resolve in 3 days
- **Low** (questions): Respond in 24 hours

---

## Best Practices for HQ Staff

### ✅ Daily Checklist

**Morning:**
- [ ] Review new business applications
- [ ] Check system health dashboard
- [ ] Review overnight support tickets
- [ ] Check subscription expirations for the day

**During Day:**
- [ ] Respond to escalated support tickets
- [ ] Process contract uploads
- [ ] Monitor payment notifications

**Evening:**
- [ ] Review audit log for anomalies
- [ ] Check subscription renewals processed
- [ ] Prepare tomorrow's tasks

### ✅ Weekly Tasks

- [ ] Review analytics and trends
- [ ] Generate platform revenue report
- [ ] Check for stuck or pending approvals
- [ ] Plan outreach to at-risk subscriptions
- [ ] Update documentation (like this guide!)

### ✅ Monthly Tasks

- [ ] Generate monthly platform metrics report
- [ ] Review and optimize subscription tiers
- [ ] Analyze churn and retention
- [ ] Plan feature rollouts
- [ ] Conduct team training/knowledge sharing

---

## Compliance & Security

### Data Protection (GDPR / Data Privacy)

**Requirements:**
- Store only necessary data
- Encrypt sensitive information
- Honor deletion requests within 30 days
- Provide data exports on request
- Maintain audit trails

**Merchant Data Access:**
- HQ can view (for support/analytics)
- HQ should NOT modify merchant data without explicit permission
- All access is logged in audit trails

### Security Protocols

**Access Control:**
- HQ staff use separate credentials (not shared)
- Enable 2FA for all HQ accounts
- Review access logs weekly

**Incident Response:**
- Report security incidents immediately
- Follow incident response playbook
- Notify affected merchants within 72 hours

**Password Policy:**
- Change HQ passwords every 90 days
- Use strong, unique passwords
- Never share credentials

---

## Key Metrics to Track

### Platform Health
- **Uptime**: Target 99.9%
- **Response Time**: <200ms average
- **Error Rate**: <0.1% of requests

### Business Metrics
- **Monthly Active Businesses**: Logged in within 30 days
- **New Signups**: Track growth rate
- **Churn Rate**: Businesses leaving per month

### Financial Metrics
- **MRR** (Monthly Recurring Revenue)
- **ARPU** (Average Revenue Per User)
- **LTV** (Lifetime Value) vs CAC (Customer Acquisition Cost)

### Support Metrics
- **First Response Time**: Target <4 hours
- **Resolution Time**: Average days to close ticket
- **Customer Satisfaction**: Survey score

---

## Tools & Integrations

### Currently Active
- **WhatsApp Business API**: Notifications
- **Email (SMTP)**: Transactional emails
- **Cloud Storage**: Backups and contract files
- **Payment Gateway**: (If applicable) for subscription billing

### Roadmap
- SMS notifications
- Accounting software integration (QuickBooks, Xero)
- Advanced analytics dashboards
- Mobile app for merchants

---

## Getting Help

### Technical Issues
- **Slack Channel**: `#hq-tech-support`
- **Email**: `hq-tech@emajinet.com`
- **Emergency Hotline**: (for critical outages)

### Process Questions
- **Documentation Wiki**: Internal knowledge base
- **Weekly Sync**: Team meetings every Monday
- **Mentor Program**: Pair new HQ staff with veterans

---

## Important Reminders

⚠️ **Merchant Trust**
- Merchants trust us with their business data
- Handle all data with care and professionalism
- Never discuss merchant details publicly

⚠️ **Confidentiality**
- All merchant data is confidential
- Do not share analytics externally
- Follow NDA agreements

⚠️ **Accuracy**
- Double-check before suspending a business
- Verify payment status before revoking access
- Document all major actions

⚠️ **Communication**
- Be responsive and professional
- Set clear expectations
- Follow up on promises

---

## Next Steps

1. **Tour the HQ Dashboard**: Familiarize yourself with all sections
2. **Review Pending Businesses**: Practice approval workflow
3. **Browse Contracts**: Understand the contract process
4. **Explore Analytics**: Generate a sample report
5. **Shadow a Senior HQ Staff Member**: Learn best practices

**Questions?** Reach out to your team lead or refer to the internal wiki!

---

*Version 1.0 – December 2025*  
*Emajinet / Circuit City HQ Team*

