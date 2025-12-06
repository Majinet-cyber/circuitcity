# timelogs/utils_geo.py
"""
Geolocation utilities for calculating distance and determining if agent is within geofence.
"""
from math import radians, cos, sin, asin, sqrt
from decimal import Decimal
from typing import Tuple


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance in meters between two points 
    on the earth (specified in decimal degrees).
    
    Args:
        lat1: Latitude of point 1
        lon1: Longitude of point 1
        lat2: Latitude of point 2
        lon2: Longitude of point 2
        
    Returns:
        Distance in meters
    """
    # Convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    
    # Radius of earth in meters
    r = 6371000
    
    return c * r


def is_within_geofence(
    agent_lat: Decimal,
    agent_lon: Decimal,
    location_lat: Decimal,
    location_lon: Decimal,
    radius_m: int
) -> Tuple[bool, float]:
    """
    Check if agent's location is within the geofence radius of a location.
    
    Args:
        agent_lat: Agent's latitude
        agent_lon: Agent's longitude
        location_lat: Location's latitude
        location_lon: Location's longitude
        radius_m: Geofence radius in meters
        
    Returns:
        Tuple of (is_inside, distance_m)
    """
    if not all([agent_lat, agent_lon, location_lat, location_lon]):
        return False, 0.0
    
    distance = haversine_distance(
        float(agent_lat),
        float(agent_lon),
        float(location_lat),
        float(location_lon)
    )
    
    is_inside = distance <= radius_m
    
    return is_inside, distance


def calculate_30min_slots(minutes: int) -> int:
    """
    Calculate the number of full 30-minute slots in the given minutes.
    
    Args:
        minutes: Total minutes
        
    Returns:
        Number of 30-minute slots
    """
    return max(0, minutes // 30)

