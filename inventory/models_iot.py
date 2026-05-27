# inventory/models_iot.py
"""
IoT monitoring models for Emajinet.
Supports ESP32-based devices sending readings via webhook.
"""
from __future__ import annotations

import secrets
from decimal import Decimal

from django.db import models
from django.utils import timezone

from tenants.models import Business


class IoTDeviceStatus(models.TextChoices):
    ONLINE = "online", "Online"
    OFFLINE = "offline", "Offline"
    WARNING = "warning", "Warning"


class IoTDeviceType(models.TextChoices):
    ENERGY = "energy", "Energy Monitor"
    WEATHER = "weather", "Weather Station"
    WATER = "water", "Water Sensor"
    MOTION = "motion", "Motion Sensor"
    GPS = "gps", "GPS Tracker"
    CUSTOM = "custom", "Custom Device"


class IoTDevice(models.Model):
    """Represents a registered ESP32/IoT device."""

    business = models.ForeignKey(
        Business,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="iot_devices",
    )
    device_id = models.CharField(
        max_length=100, unique=True, db_index=True, help_text="Unique device identifier (e.g. esp32-energy-001)"
    )
    name = models.CharField(max_length=150, help_text="Human-friendly name")
    device_type = models.CharField(
        max_length=30, choices=IoTDeviceType.choices, default=IoTDeviceType.ENERGY
    )
    vertical = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Associated vertical (e.g. energy, farm)",
    )
    api_key = models.CharField(
        max_length=64,
        unique=True,
        help_text="Secret token used by device in Authorization header",
    )
    status = models.CharField(
        max_length=20, choices=IoTDeviceStatus.choices, default=IoTDeviceStatus.OFFLINE
    )
    last_seen = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True, help_text="Device metadata (firmware, location, etc.)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_seen"]

    def __str__(self):
        return f"{self.name} ({self.device_id}) [{self.status}]"

    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def mark_online(self):
        self.status = IoTDeviceStatus.ONLINE
        self.last_seen = timezone.now()
        self.save(update_fields=["status", "last_seen"])


class IoTReading(models.Model):
    """A single sensor reading from an IoT device."""

    device = models.ForeignKey(IoTDevice, on_delete=models.CASCADE, related_name="readings")
    reading_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="e.g. voltage, current, power, temperature, humidity",
    )
    value = models.FloatField()
    unit = models.CharField(max_length=20, blank=True, default="", help_text="e.g. V, A, W, °C, %")
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["device", "reading_type", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.device.device_id} / {self.reading_type}: {self.value} {self.unit}"
