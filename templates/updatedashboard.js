function updateDashboardData() {
    fetch('/api/logs')
      .then(res => res.json())
      .then(response => {
        const pBody = document.getElementById('pothole-table-body');
        const gBody = document.getElementById('garbage-table-body');
        const busBody = document.getElementById('bus-table-body');

        if (pBody) pBody.innerHTML = '';
        if (gBody) gBody.innerHTML = '';

        let pTotalCount = 0;
        let gTotalCount = 0;
        const busStats = {};

        const logs = Array.isArray(response) ? response : (response.logs || []);

        if (logs.length > 0) {
          const recentLogs = [...logs].reverse();
          
          if(typeof map !== 'undefined' && map && typeof hazardMarkers !== 'undefined') {
            hazardMarkers.forEach(m => map.removeLayer(m));
            hazardMarkers = [];
          }

          recentLogs.forEach((log, index) => {
            const hType = log.Hazard_Type ? log.Hazard_Type.trim() : '';
            if (hType.toLowerCase() === 'waterlogging') return;

            const severity = log.Severity;
            const conf = log.Confidence;
            const lat = parseFloat(log.Latitude) || 12.9716;
            const lon = parseFloat(log.Longitude) || 77.5946;
            const timestamp = log.Timestamp;
            const uniqueId = `${timestamp}-${index}`;
            const busId = log.Bus_ID || 'KA-01-F-4021';

            if (typeof hazardStatuses !== 'undefined') {
              if (!hazardStatuses[uniqueId]) {
                hazardStatuses[uniqueId] = 'Pending';
              }
            }
            const currentStatus = (typeof hazardStatuses !== 'undefined') ? hazardStatuses[uniqueId] : 'Pending';
            const isSolved = (currentStatus === 'Solved');
            const statusBtnClass = isSolved ? 'btn-status-solved' : 'btn-status-pending';

            if (!busStats[busId]) {
              busStats[busId] = { total: 0, potholes: 0, garbage: 0, lastTime: timestamp, active: true };
            }
            busStats[busId].total++;
            
            if (hType.toLowerCase() === 'pothole') {
              busStats[busId].potholes++;
              pTotalCount++;
            }
            if (hType.toLowerCase() === 'garbage') {
              busStats[busId].garbage++;
              gTotalCount++;
            }
            
            busStats[busId].lastTime = timestamp;

            let color = '#FF6B35';
            if (hType.toLowerCase() === 'garbage') color = '#00E5FF';

            const rowHtml = `
              <tr>
                <td class="mono" style="font-size:0.78rem;">${timestamp}</td>
                <td><span class="bus-badge">🚌 ${busId}</span></td>
                <td><span style="font-size:0.75rem; font-weight:600;">${severity}</span></td>
                <td>${conf}</td>
                <td class="mono" style="font-size:0.78rem;">${lat.toFixed(4)}, ${lon.toFixed(4)}</td>
                <td>
                  <button class="${statusBtnClass}" onclick="toggleStatus('${uniqueId}')">
                    ${isSolved ? '✔ Solved' : '⏳ Pending'}
                  </button>
                </td>
              </tr>
            `;

            if (hType.toLowerCase() === 'pothole' && pBody) {
              pBody.innerHTML += rowHtml;
            } else if (hType.toLowerCase() === 'garbage' && gBody) {
              gBody.innerHTML += rowHtml;
            }

            if(typeof map !== 'undefined' && map && !isSolved && typeof hazardMarkers !== 'undefined') {
              const customIcon = L.divIcon({
                className: 'custom-marker',
                html: `<div style="background:${color}; width:14px; height:14px; border-radius:50%; border:2px solid #fff; box-shadow:0 0 10px ${color};"></div>`,
                iconSize: [14, 14],
                iconAnchor: [7, 7]
              });
              const marker = L.marker([lat, lon], { icon: customIcon }).addTo(map);
              marker.bindPopup(`<strong>${hType} (${severity})</strong><br>Detected by Bus: <strong>${busId}</strong><br>Status: ${currentStatus}`);
              hazardMarkers.push(marker);
            }
          });

          if (busBody) {
            busBody.innerHTML = '';
            Object.keys(busStats).forEach(bId => {
              const b = busStats[bId];
              busBody.innerHTML += `
                <tr>
                  <td><span class="bus-badge">🚌 ${bId}</span></td>
                  <td class="mono" style="font-weight:600;">${b.total}</td>
                  <td class="mono" style="color:var(--danger);">${b.potholes}</td>
                  <td class="mono" style="color:var(--cyan);">${b.garbage}</td>
                  <td class="mono" style="font-size:0.78rem;">${b.lastTime}</td>
                  <td><span class="badge-smooth" style="color:var(--live);">Active Route</span></td>
                </tr>
              `;
            });
          }
        }

        const elPotholes = document.getElementById('potholes-count') || document.getElementById('stat-potholes');
        const elGarbage = document.getElementById('garbage-count') || document.getElementById('stat-garbage');
        
        if (elPotholes) {
          elPotholes.textContent = response.pothole_count !== undefined ? response.pothole_count : pTotalCount;
        }
        if (elGarbage) {
          elGarbage.textContent = response.garbage_count !== undefined ? response.garbage_count : gTotalCount;
        }

        if (pBody && pBody.innerHTML === '') pBody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-mid);">No potholes recorded.</td></tr>`;
        if (gBody && gBody.innerHTML === '') gBody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-mid);">No garbage dumps recorded.</td></tr>`;
        if (busBody && busBody.innerHTML === '') busBody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-mid);">No bus telemetry available yet.</td></tr>`;
      })
      .catch(err => console.error("Error fetching logs:", err));
}