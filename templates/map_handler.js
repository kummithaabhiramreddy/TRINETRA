// Stores existing map markers so we can clear/refresh them cleanly
let hazardMarkers = [];

function getSeverityColor(severity) {
    const s = (severity || "").toUpperCase();
    if (s === "CRITICAL") return "#ff3333";    // Bright Red
    if (s === "MODERATE") return "#ffcc00";    // Yellow
    return "#33cc33";                         // Green / Minor
}

async function updateLiveMap(mapInstance) {
    if (!mapInstance) return;

    try {
        const response = await fetch('/api/logs');
        if (!response.ok) return;

        const data = await response.json();
        const logs = data.logs || [];

        // Clear existing markers
        hazardMarkers.forEach(marker => mapInstance.removeLayer(marker));
        hazardMarkers = [];

        // Plot detected potholes and hazards
        logs.forEach(item => {
            const lat = parseFloat(item.Latitude);
            const lon = parseFloat(item.Longitude);

            if (!isNaN(lat) && !isNaN(lon)) {
                const color = getSeverityColor(item.Severity);
                const marker = L.circleMarker([lat, lon], {
                    radius: 8,
                    fillColor: color,
                    color: "#ffffff",
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.85
                });

                const popupContent = `
                    <div style="font-family: sans-serif; font-size: 13px;">
                        <b>Hazard:</b> ${item.Hazard_Type}<br>
                        <b>Severity:</b> <span style="color:${color}; font-weight:bold;">${item.Severity}</span><br>
                        <b>Confidence:</b> ${item.Confidence}<br>
                        <b>Time:</b> ${item.Timestamp}
                    </div>
                `;

                marker.bindPopup(popupContent);
                marker.addTo(mapInstance);
                hazardMarkers.push(marker);
            }
        });
    } catch (err) {
        console.error("Failed to update map markers:", err);
    }
}