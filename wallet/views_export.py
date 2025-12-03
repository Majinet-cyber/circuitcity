# wallet/views_export.py
"""
Agent-level data export functionality.
Allows agents to download their own activity data.
"""
from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.db.models import Q

from tenants.utils import get_active_business
from wallet.models import WalletTransaction
from sales.models import Sale
from timelogs.models import AgentWorkLog


@login_required
def agent_export_activity(request: HttpRequest) -> HttpResponse:
    """
    Export an agent's own activity data as CSV.
    
    Includes:
    - Wallet transactions
    - Sales records
    - Work logs / timelogs
    """
    business = get_active_business(request)
    if not business:
        return HttpResponse("No active business", status=400)
    
    agent = request.user
    
    # Create CSV in memory
    output = StringIO()
    
    # Write metadata header
    output.write(f"CircuitCity Agent Activity Export\n")
    output.write(f"Agent: {agent.username} ({agent.get_full_name() or 'N/A'})\n")
    output.write(f"Business: {business.name}\n")
    output.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.write(f"\n")
    
    # ============================================================
    # WALLET TRANSACTIONS
    # ============================================================
    output.write(f"=== WALLET TRANSACTIONS ===\n")
    
    wallet_txns = WalletTransaction.objects.filter(
        agent=agent,
        ledger='agent'
    ).order_by('-created_at')
    
    if wallet_txns.exists():
        writer = csv.writer(output)
        writer.writerow(['Date', 'Type', 'Amount (MWK)', 'Note', 'Reference', 'Balance Impact'])
        
        for txn in wallet_txns:
            writer.writerow([
                txn.effective_date.strftime('%Y-%m-%d'),
                txn.get_type_display(),
                f"{txn.amount:,.2f}",
                txn.note,
                txn.reference,
                'Credit' if txn.amount > 0 else 'Debit'
            ])
        
        output.write(f"\nTotal Transactions: {wallet_txns.count()}\n")
        total_amount = sum(txn.amount for txn in wallet_txns)
        output.write(f"Net Balance: {total_amount:,.2f} MWK\n")
    else:
        output.write("No wallet transactions found.\n")
    
    output.write(f"\n\n")
    
    # ============================================================
    # SALES RECORDS
    # ============================================================
    output.write(f"=== SALES RECORDS ===\n")
    
    sales = Sale.objects.filter(
        agent=agent,
        location__business=business
    ).select_related('item', 'location').order_by('-sold_at')
    
    if sales.exists():
        writer = csv.writer(output)
        writer.writerow(['Date', 'IMEI', 'Brand', 'Model', 'Price (MWK)', 'Commission %', 'Commission Amount', 'Payment Method', 'Location'])
        
        for sale in sales:
            item = sale.item
            writer.writerow([
                sale.sold_at.strftime('%Y-%m-%d'),
                item.imei if item else 'N/A',
                item.brand if item else 'N/A',
                item.model if item else 'N/A',
                f"{sale.price:,.2f}",
                f"{sale.commission_pct:.2f}",
                f"{sale.commission_amount:,.2f}",
                sale.get_payment_method_display(),
                sale.location.name if sale.location else 'N/A'
            ])
        
        output.write(f"\nTotal Sales: {sales.count()}\n")
        total_revenue = sum(sale.price for sale in sales)
        total_commission = sum(sale.commission_amount for sale in sales)
        output.write(f"Total Revenue: {total_revenue:,.2f} MWK\n")
        output.write(f"Total Commission Earned: {total_commission:,.2f} MWK\n")
    else:
        output.write("No sales records found.\n")
    
    output.write(f"\n\n")
    
    # ============================================================
    # WORK LOGS / TIMELOGS
    # ============================================================
    output.write(f"=== WORK LOGS & ATTENDANCE ===\n")
    
    work_logs = AgentWorkLog.objects.filter(
        agent=agent,
        business=business
    ).select_related('location').order_by('-work_date')
    
    if work_logs.exists():
        writer = csv.writer(output)
        writer.writerow([
            'Date', 'Location', 'First Seen', 'Last Seen', 
            'On-Site (mins)', 'Idle (mins)', 'Effective Work (mins)',
            'Early (mins)', 'Late (mins)', 'Bonus (MWK)', 'Penalty (MWK)'
        ])
        
        for log in work_logs:
            writer.writerow([
                log.work_date.strftime('%Y-%m-%d'),
                log.location.name if log.location else 'N/A',
                log.first_seen_at.strftime('%H:%M:%S') if log.first_seen_at else 'N/A',
                log.last_seen_at.strftime('%H:%M:%S') if log.last_seen_at else 'N/A',
                log.total_on_site_minutes,
                log.total_idle_minutes,
                log.effective_work_minutes,
                log.arrived_early_minutes,
                log.arrived_late_minutes,
                f"{log.bonus_amount:,.2f}",
                f"{log.penalty_amount:,.2f}"
            ])
        
        output.write(f"\nTotal Work Days: {work_logs.count()}\n")
        total_on_site = sum(log.total_on_site_minutes for log in work_logs)
        total_bonuses = sum(log.bonus_amount for log in work_logs)
        total_penalties = sum(log.penalty_amount for log in work_logs)
        output.write(f"Total On-Site Time: {total_on_site:,.0f} minutes ({total_on_site/60:.1f} hours)\n")
        output.write(f"Total Bonuses: {total_bonuses:,.2f} MWK\n")
        output.write(f"Total Penalties: {total_penalties:,.2f} MWK\n")
    else:
        output.write("No work logs found.\n")
    
    output.write(f"\n\n")
    output.write(f"=== END OF EXPORT ===\n")
    
    # Prepare response
    csv_content = output.getvalue()
    output.close()
    
    response = HttpResponse(csv_content, content_type='text/csv')
    filename = f"agent_activity_{agent.username}_{datetime.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

