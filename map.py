import os
import math

def get_approx_coordinates(place_name):
    """
    Returns rough latitude and longitude for common AP/Telangana regions 
    to enable distance estimation.
    """
    coords = {
        "Machilipatnam": (16.1809, 81.1303),
        "Bhimavaram": (16.5448, 81.5212),
        "Vijayawada": (16.5062, 80.6480),
        "Hyderabad": (17.3850, 78.4867),
        "Guntur": (16.3067, 80.4365),
        "Eluru": (16.7107, 81.0952),
        "Kakinada": (16.9891, 82.2475),
        "Rajahmundry": (17.0005, 81.7777),
        "Visakhapatnam": (17.6868, 83.2185)
    }
    # Default fallback near Machilipatnam if not found
    return coords.get(place_name.strip().title(), (16.1809, 81.1303))

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates the great-circle distance between two points on the earth."""
    R = 6371.0 # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def analyze_traffic(origin, destination):
    origin = origin.strip().title()
    destination = destination.strip().title()

    lat1, lon1 = get_approx_coordinates(origin)
    lat2, lon2 = get_approx_coordinates(destination)

    # Calculate straight-line distance and multiply by a road circuity factor (~1.25) for realistic driving distance
    straight_dist = calculate_haversine_distance(lat1, lon1, lat2, lon2)
    driving_distance = round(straight_dist * 1.25, 1)
    
    # Estimate time assuming average speed of 45 km/h
    est_hours = driving_distance / 45.0
    est_minutes = int(est_hours * 60)
    if est_minutes < 10:
        est_minutes = 15

    # Determine mock congestion based on distance block
    congestion = "Smooth Flow"
    if driving_distance > 50:
        congestion = "Moderate Congestion"
    if driving_distance > 100:
        congestion = "High Congestion"

    return {
        "origin": origin,
        "destination": destination,
        "distance": f"{driving_distance} km",
        "duration_in_traffic": f"{est_minutes} mins",
        "congestion_status": congestion
    }