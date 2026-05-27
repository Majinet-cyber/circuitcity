# inventory/services_car_hire_emails.py
"""
PART 6: Car Hire Email Notification Service

Sends manager notifications for:
- New booking created
- Payment received (with invoice PDF)
- Booking overdue/unpaid reminder
- Vehicle maintenance reminder

Uses Django's email infrastructure.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from typing import List, Optional

from django.conf import settings
from django.core.mail import EmailMessage, send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


class CarHireEmailService:
    """
    Handles all email notifications for Car Hire vertical.
    """
    
    def __init__(self, business):
        """
        Initialize the service.
        
        Args:
            business: The Business instance
        """
        self.business = business
        self.from_email = getattr(
            settings,
            'DEFAULT_FROM_EMAIL',
            'noreply@emajinet.com'
        )
    
    def _get_manager_emails(self) -> List[str]:
        """Get list of manager email addresses for this business."""
        emails = []
        
        # Try to get from Membership
        try:
            from tenants.models import Membership
            memberships = Membership.objects.filter(
                business=self.business,
                role__in=('MANAGER', 'BAR_MANAGER'),
                status='ACTIVE',
            ).select_related('user')
            
            for m in memberships:
                if m.user and m.user.email:
                    emails.append(m.user.email)
        except Exception as e:
            logger.warning(f"Could not fetch manager emails: {e}")
        
        # Fallback to business creator email if no managers found
        if not emails and self.business.created_by_id:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                creator = User.objects.get(pk=self.business.created_by_id)
                if creator.email:
                    emails.append(creator.email)
            except Exception:
                pass
        
        return list(set(emails))  # Remove duplicates
    
    def send_new_booking_notification(self, trip) -> bool:
        """
        Send notification when a new booking is created.
        
        Args:
            trip: The Trip instance
            
        Returns:
            True if email was sent successfully
        """
        try:
            manager_emails = self._get_manager_emails()
            if not manager_emails:
                logger.warning(
                    f"No manager emails found for business {self.business.pk}"
                )
                return False
            
            subject = f"[{self.business.name}] New Car Hire Booking - {trip.customer_name}"
            
            # Build email context
            context = {
                'business': self.business,
                'trip': trip,
                'vehicle': trip.vehicle,
                'customer_name': trip.customer_name,
                'customer_phone': trip.customer_phone,
                'destination': trip.destination,
                'start_datetime': trip.start_datetime,
                'end_datetime': trip.end_datetime,
                'price_total': trip.price_total,
                'deposit_paid': trip.deposit_paid,
                'balance_due': trip.balance_due,
                'trip_type': trip.get_trip_type_display(),
                'created_at': trip.created_at,
            }
            
            # Try to render HTML template, fallback to plain text
            try:
                html_content = render_to_string(
                    'emails/car_hire/new_booking.html',
                    context
                )
                plain_content = strip_tags(html_content)
            except Exception:
                # Fallback to plain text
                plain_content = self._build_new_booking_plain_text(trip)
                html_content = None
            
            # Send email
            email = EmailMessage(
                subject=subject,
                body=plain_content,
                from_email=self.from_email,
                to=manager_emails,
            )
            
            if html_content:
                email.content_subtype = 'html'
                email.body = html_content
            
            email.send(fail_silently=False)
            
            logger.info(
                f"Sent new booking notification for trip {trip.pk} to {manager_emails}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to send new booking notification: {e}")
            return False
    
    def _build_new_booking_plain_text(self, trip) -> str:
        """Build plain text email for new booking."""
        return f"""
NEW CAR HIRE BOOKING

Customer: {trip.customer_name}
Phone: {trip.customer_phone or 'N/A'}
Vehicle: {trip.vehicle.name} ({trip.vehicle.plate_number})
Destination: {trip.destination}
Trip Type: {trip.get_trip_type_display()}

Start: {trip.start_datetime.strftime('%d %b %Y %H:%M')}
End: {trip.end_datetime.strftime('%d %b %Y %H:%M') if trip.end_datetime else 'TBD'}

Total: MWK {trip.price_total:,.0f}
Deposit Paid: MWK {trip.deposit_paid:,.0f}
Balance Due: MWK {trip.balance_due:,.0f}

---
{self.business.name}
"""
    
    def send_payment_received_notification(
        self,
        trip,
        amount_paid: Decimal,
        invoice_pdf: Optional[bytes] = None
    ) -> bool:
        """
        Send notification when payment is received.
        
        Args:
            trip: The Trip instance
            amount_paid: Amount that was just paid
            invoice_pdf: Optional invoice PDF bytes to attach
            
        Returns:
            True if email was sent successfully
        """
        try:
            manager_emails = self._get_manager_emails()
            if not manager_emails:
                logger.warning(
                    f"No manager emails found for business {self.business.pk}"
                )
                return False
            
            subject = f"[{self.business.name}] Payment Received - {trip.customer_name}"
            
            # Build email content
            context = {
                'business': self.business,
                'trip': trip,
                'vehicle': trip.vehicle,
                'customer_name': trip.customer_name,
                'amount_paid': amount_paid,
                'total_deposit': trip.deposit_paid,
                'price_total': trip.price_total,
                'balance_due': trip.balance_due,
            }
            
            # Try to render HTML template, fallback to plain text
            try:
                html_content = render_to_string(
                    'emails/car_hire/payment_received.html',
                    context
                )
                plain_content = strip_tags(html_content)
            except Exception:
                plain_content = self._build_payment_received_plain_text(
                    trip, amount_paid
                )
                html_content = None
            
            # Send email
            email = EmailMessage(
                subject=subject,
                body=plain_content if not html_content else html_content,
                from_email=self.from_email,
                to=manager_emails,
            )
            
            if html_content:
                email.content_subtype = 'html'
            
            # Attach invoice PDF if provided
            if invoice_pdf:
                email.attach(
                    f'invoice_{trip.pk}.pdf',
                    invoice_pdf,
                    'application/pdf'
                )
            
            email.send(fail_silently=False)
            
            logger.info(
                f"Sent payment notification for trip {trip.pk} to {manager_emails}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to send payment notification: {e}")
            return False
    
    def _build_payment_received_plain_text(
        self,
        trip,
        amount_paid: Decimal
    ) -> str:
        """Build plain text email for payment received."""
        return f"""
PAYMENT RECEIVED

Customer: {trip.customer_name}
Vehicle: {trip.vehicle.name} ({trip.vehicle.plate_number})

Amount Paid Now: MWK {amount_paid:,.0f}
Total Deposit: MWK {trip.deposit_paid:,.0f}
Trip Total: MWK {trip.price_total:,.0f}
Balance Due: MWK {trip.balance_due:,.0f}

---
{self.business.name}
"""
    
    def send_overdue_reminder(self, trip) -> bool:
        """
        Send reminder for overdue/unpaid booking.
        
        Args:
            trip: The Trip instance that is overdue
            
        Returns:
            True if email was sent successfully
        """
        try:
            manager_emails = self._get_manager_emails()
            if not manager_emails:
                return False
            
            subject = f"[{self.business.name}] OVERDUE: {trip.customer_name} - MWK {trip.balance_due:,.0f}"
            
            plain_content = f"""
OVERDUE BOOKING REMINDER

Customer: {trip.customer_name}
Phone: {trip.customer_phone or 'N/A'}
Vehicle: {trip.vehicle.name} ({trip.vehicle.plate_number})
Destination: {trip.destination}

Trip Ended: {trip.end_datetime.strftime('%d %b %Y') if trip.end_datetime else 'N/A'}

Trip Total: MWK {trip.price_total:,.0f}
Amount Paid: MWK {trip.deposit_paid:,.0f}
BALANCE DUE: MWK {trip.balance_due:,.0f}

Please follow up with the customer to collect the outstanding balance.

---
{self.business.name}
"""
            
            send_mail(
                subject=subject,
                message=plain_content,
                from_email=self.from_email,
                recipient_list=manager_emails,
                fail_silently=False,
            )
            
            logger.info(
                f"Sent overdue reminder for trip {trip.pk} to {manager_emails}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to send overdue reminder: {e}")
            return False
    
    def send_maintenance_reminder(self, vehicle) -> bool:
        """
        Send reminder when vehicle maintenance is due.
        
        Args:
            vehicle: The Vehicle instance needing maintenance
            
        Returns:
            True if email was sent successfully
        """
        try:
            manager_emails = self._get_manager_emails()
            if not manager_emails:
                return False
            
            subject = f"[{self.business.name}] Maintenance Due: {vehicle.name}"
            
            km_info = ""
            if vehicle.current_odometer and vehicle.next_maintenance_km:
                if vehicle.current_odometer >= vehicle.next_maintenance_km:
                    km_info = f"\nMAINTENANCE OVERDUE by {vehicle.current_odometer - vehicle.next_maintenance_km:,} km"
                else:
                    km_info = f"\n{vehicle.km_until_maintenance:,} km until service"
            
            plain_content = f"""
VEHICLE MAINTENANCE REMINDER

Vehicle: {vehicle.name}
Plate: {vehicle.plate_number}
Make/Model: {vehicle.get_make_display()} {vehicle.model}

Current Odometer: {vehicle.current_odometer:,} km
Next Service At: {vehicle.next_maintenance_km:,} km{km_info}

Please schedule maintenance soon to keep the vehicle in good condition.

---
{self.business.name}
"""
            
            send_mail(
                subject=subject,
                message=plain_content,
                from_email=self.from_email,
                recipient_list=manager_emails,
                fail_silently=False,
            )
            
            logger.info(
                f"Sent maintenance reminder for vehicle {vehicle.pk} to {manager_emails}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to send maintenance reminder: {e}")
            return False
    
    @classmethod
    def check_and_send_overdue_reminders(cls, business) -> int:
        """
        Check for overdue trips and send reminders.
        
        Args:
            business: The Business to check
            
        Returns:
            Number of reminders sent
        """
        from inventory.models_car_hire import Trip, TripStatus
        
        service = cls(business)
        sent_count = 0
        
        # Find completed trips with balance due
        now = timezone.now()
        cutoff = now - timedelta(days=1)  # 1 day grace period
        
        overdue_trips = Trip.objects.filter(
            business=business,
            status=TripStatus.COMPLETED,
            deposit_paid__lt=models.F('price_total'),
            end_datetime__lt=cutoff,
        )
        
        for trip in overdue_trips:
            if trip.balance_due > 0:
                if service.send_overdue_reminder(trip):
                    sent_count += 1
        
        return sent_count
    
    @classmethod
    def check_and_send_maintenance_reminders(cls, business) -> int:
        """
        Check for vehicles needing maintenance and send reminders.
        
        Args:
            business: The Business to check
            
        Returns:
            Number of reminders sent
        """
        from inventory.models_car_hire import Vehicle
        
        service = cls(business)
        sent_count = 0
        
        # Find vehicles with maintenance due
        vehicles = Vehicle.objects.filter(
            business=business,
            is_active=True,
            next_maintenance_km__isnull=False,
        )
        
        for vehicle in vehicles:
            if vehicle.is_maintenance_due:
                if service.send_maintenance_reminder(vehicle):
                    sent_count += 1
        
        return sent_count


# Import models for F expression
from django.db import models

__all__ = ['CarHireEmailService']

