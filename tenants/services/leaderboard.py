# tenants/services/leaderboard.py
"""
Agent leaderboard service for multi-tenant businesses.
"""
from __future__ import annotations

from django.db.models import Count, Sum, Q
from typing import List, Dict, Any, Optional


def get_agent_leaderboard(
    business,
    start,
    end,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get top agents ranked by sales performance.
    
    Args:
        business: Business instance
        start: Start date for filtering sales
        end: End date for filtering sales
        limit: Max number of agents to return (default 10)
    
    Returns:
        List of dicts with agent stats:
            - user: User instance
            - user_id: User ID
            - name: Agent full name
            - location: Location name
            - devices_sold: Number of devices sold
            - total_sales_amount: Total revenue from sales
            - total_commission_amount: Total commission earned
            - rank: Position in leaderboard (1-indexed)
    """
    from tenants.models import Membership
    from sales.models import Sale
    from wallet.models import WalletTransaction
    
    try:
        # Get all active agent memberships for this business
        agent_memberships = (
            Membership.objects.filter(
                business=business,
                role='AGENT',
                status='ACTIVE'
            )
            .select_related('user', 'location')
        )
        
        leaderboard = []
        
        for membership in agent_memberships:
            # Count devices sold (via Sale model)
            devices_sold = Sale.objects.filter(
                agent=membership.user,
                location__business=business,
                sold_at__gte=start,
                sold_at__lte=end
            ).count()
            
            # Sum total sales amount
            total_sales = Sale.objects.filter(
                agent=membership.user,
                location__business=business,
                sold_at__gte=start,
                sold_at__lte=end
            ).aggregate(total=Sum('price'))['total'] or 0
            
            # Sum total commission earned (from wallet transactions)
            total_commission = WalletTransaction.objects.filter(
                agent=membership.user,
                business=business,
                type='commission',
                effective_date__gte=start,
                effective_date__lte=end
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            leaderboard.append({
                'user': membership.user,
                'user_id': membership.user.id,
                'name': membership.user.get_full_name() or membership.user.username,
                'location': membership.location.name if membership.location else '',
                'devices_sold': devices_sold,
                'total_sales_amount': float(total_sales),
                'total_commission_amount': float(total_commission),
            })
        
        # Sort by devices sold (primary), then by sales amount (secondary)
        leaderboard.sort(
            key=lambda x: (x['devices_sold'], x['total_sales_amount']),
            reverse=True
        )
        
        # Add rank and limit to top N
        ranked = []
        for idx, agent in enumerate(leaderboard[:limit], start=1):
            agent['rank'] = idx
            ranked.append(agent)
        
        return ranked
        
    except Exception as e:
        # Fail gracefully
        return []


def get_current_agent_rank(
    business,
    user,
    start,
    end
) -> Optional[Dict[str, Any]]:
    """
    Get the current logged-in agent's rank and gap to leader.
    
    Args:
        business: Business instance
        user: Current user
        start: Start date
        end: End date
    
    Returns:
        Dict with:
            - rank: Current rank (1-indexed) or None
            - gap: Number of sales behind #1, or None
            - gap_formatted: Formatted gap message
    """
    try:
        from sales.models import Sale
        
        # Get full leaderboard (no limit)
        full_leaderboard = get_agent_leaderboard(business, start, end, limit=999)
        
        if not full_leaderboard:
            return {'rank': None, 'gap': None, 'gap_formatted': None}
        
        # Find current user's position
        for agent in full_leaderboard:
            if agent['user_id'] == user.id:
                rank = agent['rank']
                gap = None
                gap_formatted = None
                
                if rank > 1:
                    # Calculate gap to #1
                    leader = full_leaderboard[0]
                    gap = leader['devices_sold'] - agent['devices_sold']
                    if gap > 0:
                        gap_formatted = f"Only {gap} sale{'s' if gap != 1 else ''} behind #1"
                
                return {
                    'rank': rank,
                    'gap': gap,
                    'gap_formatted': gap_formatted
                }
        
        # User not in leaderboard (no sales)
        return {'rank': None, 'gap': None, 'gap_formatted': None}
        
    except Exception:
        return {'rank': None, 'gap': None, 'gap_formatted': None}

