/**
 * THRINETHRA - Neon PostgreSQL Database Client
 * Direct serverless HTTP connection to Neon database for user authentication,
 * bus registration, real-time AI hazard logging, GIS telemetry, and audit reporting.
 */

(function (global) {
  'use strict';

  const NEON_CONFIG = {
    connectionString: 'postgresql://neondb_owner:npg_kCrMU0l9LViJ@ep-rapid-sunset-a54uayxa-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require',
    sqlEndpoint: 'https://ep-rapid-sunset-a54uayxa.us-east-2.aws.neon.tech/sql'
  };

  // Default seed accounts for transport command center authority
  const SEED_USERS = [
    {
      id: 'usr_admin_001',
      first_name: 'Thri',
      last_name: 'Nethra',
      name: 'Thri Nethra',
      email: 'admin@thrinethra.gov',
      org: 'Bengaluru Metropolitan Transport Corp. (BMTC)',
      role: 'Chief Traffic Controller',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=160&q=80',
      provider: 'email',
      password_hash: 'Trinetra2026!'
    },
    {
      id: 'usr_admin_002',
      first_name: 'Trinetra',
      last_name: 'Admin',
      name: 'Trinetra Admin',
      email: 'admin@trinetra.gov',
      org: 'Bengaluru Metropolitan Transport Corp. (BMTC)',
      role: 'Chief Traffic Controller',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=160&q=80',
      provider: 'email',
      password_hash: 'Trinetra2026!'
    },
    {
      id: 'usr_demo_002',
      first_name: 'Vikram',
      last_name: 'Rao',
      name: 'Vikram Rao',
      email: 'v.rao@transportauthority.gov',
      org: 'Urban Mobility Command',
      role: 'Fleet Operations Lead',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=160&q=80',
      provider: 'email',
      password_hash: 'Demo1234!'
    }
  ];

  class NeonDBClient {
    constructor() {
      this.endpoint = NEON_CONFIG.sqlEndpoint;
      this.connectionString = NEON_CONFIG.connectionString;
      this._initialized = false;
      this._initPromise = null;
      this._directBlocked = false;
    }

    async _getProxyEndpoint() {
      if (typeof window !== 'undefined') {
        if (window.location.protocol.startsWith('http')) {
          return '/api/neon-sql';
        }
      }
      return null;
    }

    /**
     * Execute SQL query over Neon serverless HTTP endpoint or local proxy
     * @param {string} query - SQL query with optional placeholders ($1, $2)
     * @param {Array} params - Array of parameter values
     * @returns {Promise<Array<Object>>} Array of row objects
     */
    async query(query, params = []) {
      const formattedParams = params.map(p => {
        if (p === null || p === undefined) return null;
        if (typeof p === 'object') return JSON.stringify(p);
        return String(p);
      });

      const body = {
        query: query.trim(),
        params: formattedParams
      };

      try {
        let response = null;

        // Strategy 1: Direct Neon Serverless HTTP API over HTTPS
        // Note: Do NOT include 'Content-Type: application/json' because Neon's CORS
        // Access-Control-Allow-Headers explicitly permits Neon-*, but omitting Content-Type
        // ensures browser CORS preflight passes cleanly.
        if (!this._directBlocked) {
          try {
            const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
            const timeoutId = controller ? setTimeout(() => controller.abort(), 2500) : null;
            const directRes = await fetch(this.endpoint, {
              method: 'POST',
              signal: controller ? controller.signal : undefined,
              headers: {
                'Neon-Connection-String': this.connectionString,
                'Neon-Raw-Text-Output': 'true',
                'Neon-Array-Mode': 'true'
              },
              body: JSON.stringify(body)
            });
            if (timeoutId) clearTimeout(timeoutId);
            if (directRes && directRes.ok) {
              response = directRes;
            } else {
              this._directBlocked = true;
            }
          } catch (directErr) {
            this._directBlocked = true;
            console.warn('Direct Neon connection warning, falling back to local proxy:', directErr.message);
          }
        }

        // Strategy 2: If direct Neon was blocked (e.g. strict firewall), use local server proxy
        if (!response) {
          const proxy = await this._getProxyEndpoint();
          if (proxy) {
            try {
              const res = await fetch(proxy, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
              });
              if (res.ok) {
                response = res;
              }
            } catch (e) {}
          }
        }

        // Strategy 3: Try explicit localhost ports (Flask 5000 / Node 3000)
        if (!response && typeof window !== 'undefined') {
          for (const localHostUrl of ['http://localhost:5000/api/neon-sql', 'http://127.0.0.1:5000/api/neon-sql', 'http://localhost:3000/api/neon-sql']) {
            try {
              const localRes = await fetch(localHostUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
              });
              if (localRes.ok) {
                response = localRes;
                break;
              }
            } catch (localErr) {}
          }
        }

        if (!response || !response.ok) {
          const errData = response ? await response.json().catch(() => ({ message: response.statusText })) : { message: 'Could not connect to Neon database' };
          throw new Error(errData.message || `Neon SQL error (status ${response ? response.status : 'offline'})`);
        }

        const data = await response.json();
        
        if (!data || !data.fields || !data.rows) {
          return [];
        }

        // Map rows to key-value objects (supports both array-mode and object-mode)
        const fields = data.fields ? data.fields.map(f => f.name) : [];
        return (data.rows || []).map(row => {
          if (Array.isArray(row)) {
            const obj = {};
            fields.forEach((field, i) => {
              obj[field] = row[i];
            });
            return obj;
          }
          return row;
        });
      } catch (err) {
        console.error('Neon Database Query Error:', err);
        throw err;
      }
    }

    /**
     * Ensure database schemas exist
     */
    async initSchema() {
      if (this._initialized) return true;
      if (this._initPromise) return this._initPromise;

      this._initPromise = (async () => {
        try {
          // 1. Users Table
          await this.query(`
            CREATE TABLE IF NOT EXISTS users (
              id VARCHAR(100) PRIMARY KEY,
              first_name VARCHAR(100),
              last_name VARCHAR(100),
              name VARCHAR(200) NOT NULL,
              email VARCHAR(255) UNIQUE NOT NULL,
              org VARCHAR(255),
              role VARCHAR(100) DEFAULT 'Command Center Operator',
              avatar TEXT,
              provider VARCHAR(50) DEFAULT 'email',
              password_hash TEXT,
              created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
              last_login TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
          `);

          // 2. Buses Table (Registered Bus Fleet & Attached Cameras)
          await this.query(`
            CREATE TABLE IF NOT EXISTS buses (
              id VARCHAR(100) PRIMARY KEY,
              registration_number VARCHAR(50) UNIQUE NOT NULL,
              model VARCHAR(100),
              depot VARCHAR(100),
              route_id VARCHAR(50),
              route_name VARCHAR(150),
              driver_name VARCHAR(100),
              driver_phone VARCHAR(50),
              driver_badge VARCHAR(50),
              driver_license VARCHAR(100),
              current_lat DOUBLE PRECISION DEFAULT 12.9716,
              current_lng DOUBLE PRECISION DEFAULT 77.5946,
              speed DOUBLE PRECISION DEFAULT 35.0,
              bearing DOUBLE PRECISION DEFAULT 90.0,
              status VARCHAR(50) DEFAULT 'Active',
              camera_front_status VARCHAR(50) DEFAULT 'Online',
              camera_rear_status VARCHAR(50) DEFAULT 'Online',
              camera_side_status VARCHAR(50) DEFAULT 'Online',
              camera_cabin_status VARCHAR(50) DEFAULT 'Online',
              created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
          `);

          // 3. Hazards Table (Real-Time AI Detections & Problem Reports)
          await this.query(`
            CREATE TABLE IF NOT EXISTS hazards (
              id VARCHAR(100) PRIMARY KEY,
              bus_id VARCHAR(100),
              camera_channel VARCHAR(50) DEFAULT 'Front AI',
              type VARCHAR(50) NOT NULL,
              category VARCHAR(100) NOT NULL,
              title VARCHAR(200),
              problem_description TEXT,
              confidence DOUBLE PRECISION DEFAULT 95.0,
              severity INT DEFAULT 3,
              latitude DOUBLE PRECISION NOT NULL,
              longitude DOUBLE PRECISION NOT NULL,
              address TEXT,
              google_maps_url TEXT,
              depth_mm INT DEFAULT 0,
              width_mm INT DEFAULT 0,
              length_mm INT DEFAULT 0,
              distance_m DOUBLE PRECISION DEFAULT 0.0,
              offending_plate VARCHAR(50),
              screenshot_base64 TEXT,
              solution_action TEXT,
              work_order_id VARCHAR(50),
              status VARCHAR(50) DEFAULT 'Reported',
              detected_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
          `);

          // 4. Traffic Telemetry Table
          await this.query(`
            CREATE TABLE IF NOT EXISTS traffic_telemetry (
              id VARCHAR(100) PRIMARY KEY,
              bus_id VARCHAR(100),
              latitude DOUBLE PRECISION,
              longitude DOUBLE PRECISION,
              vehicle_count INT DEFAULT 0,
              cars_count INT DEFAULT 0,
              buses_count INT DEFAULT 0,
              trucks_count INT DEFAULT 0,
              two_wheelers_count INT DEFAULT 0,
              pedestrians_count INT DEFAULT 0,
              bottleneck_level VARCHAR(50) DEFAULT 'Normal',
              recorded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
          `);

          // Seed default authority demo accounts if not already present
          for (const u of SEED_USERS) {
            const existing = await this.query(
              `SELECT id FROM users WHERE LOWER(email) = $1 LIMIT 1;`,
              [u.email.toLowerCase()]
            );
            if (existing.length === 0) {
              await this.query(
                `INSERT INTO users (id, first_name, last_name, name, email, org, role, avatar, provider, password_hash)
                 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                 ON CONFLICT (email) DO NOTHING;`,
                [u.id, u.first_name, u.last_name, u.name, u.email, u.org, u.role, u.avatar, u.provider, u.password_hash]
              );
            }
          }

          this._initialized = true;
          return true;
        } catch (err) {
          console.warn('Neon DB schema initialization warning:', err);
          return false;
        }
      })();

      return this._initPromise;
    }

    // ==========================================
    // USER AUTHENTICATION METHODS
    // ==========================================

    async findUserByEmail(email) {
      await this.initSchema();
      const cleanEmail = (email || '').trim().toLowerCase();
      if (!cleanEmail) return null;

      // Support common authority aliases (trinetra / thrinethra)
      const emailsToCheck = [cleanEmail];
      if (cleanEmail === 'admin@trinetra.gov') emailsToCheck.push('admin@thrinethra.gov');
      if (cleanEmail === 'admin@thrinethra.gov') emailsToCheck.push('admin@trinetra.gov');

      for (const targetEmail of emailsToCheck) {
        try {
          const rows = await this.query(
            `SELECT id, first_name, last_name, name, email, org, role, avatar, provider, password_hash, created_at, last_login 
             FROM users 
             WHERE LOWER(email) = $1 
             LIMIT 1;`,
            [targetEmail]
          );

          if (rows && rows.length > 0) {
            const r = rows[0];
            return {
              id: r.id,
              firstName: r.first_name,
              lastName: r.last_name,
              name: r.name,
              email: r.email,
              org: r.org,
              role: r.role,
              avatar: r.avatar,
              provider: r.provider,
              passwordHash: r.password_hash,
              createdAt: r.created_at,
              lastLogin: r.last_login
            };
          }
        } catch (err) {
          console.warn('findUserByEmail query error for', targetEmail, err);
        }
      }

      return null;
    }

    async createUser(u) {
      await this.initSchema();
      const cleanEmail = (u.email || '').trim().toLowerCase();
      const firstName = (u.firstName || '').trim();
      const lastName = (u.lastName || '').trim();
      const name = (u.name || `${firstName} ${lastName}`.trim() || 'Officer').trim();
      const id = u.id || ('usr_' + Date.now().toString(36) + Math.random().toString(36).substring(2, 6));
      const org = (u.org || 'City Transport Department').trim();
      const role = (u.role || 'Command Center Operator').trim();
      const avatar = u.avatar || `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(name)}&backgroundColor=1B2129&textColor=FF7A45`;
      const provider = u.provider || 'email';
      const passwordHash = u.passwordHash || u.password || null;

      await this.query(
        `INSERT INTO users (id, first_name, last_name, name, email, org, role, avatar, provider, password_hash, created_at, last_login)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);`,
        [id, firstName, lastName, name, cleanEmail, org, role, avatar, provider, passwordHash]
      );

      return {
        id,
        firstName,
        lastName,
        name,
        email: cleanEmail,
        org,
        role,
        avatar,
        provider,
        createdAt: new Date().toISOString(),
        lastLogin: new Date().toISOString()
      };
    }

    async updateLastLogin(userId) {
      try {
        await this.query(`UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = $1;`, [userId]);
      } catch (e) {
        console.warn('Failed to update last_login timestamp:', e);
      }
    }

    async updatePassword(email, newPassword) {
      await this.initSchema();
      const cleanEmail = (email || '').trim().toLowerCase();
      const user = await this.findUserByEmail(cleanEmail);
      if (!user) throw new Error('No registered account found with email ' + cleanEmail);

      await this.query(`UPDATE users SET password_hash = $1 WHERE LOWER(email) = $2;`, [newPassword, cleanEmail]);
      return true;
    }

    // ==========================================
    // BUS FLEET REGISTRATION & TELEMETRY METHODS
    // ==========================================

    /**
     * Register a new bus unit account in Neon DB
     */
    async registerBus(bus) {
      await this.initSchema();
      const id = bus.id || bus.registration_number || ('BUS-' + Date.now().toString(36).toUpperCase());
      const reg = (bus.registration_number || id).trim().toUpperCase();

      await this.query(`
        INSERT INTO buses (
          id, registration_number, model, depot, route_id, route_name,
          driver_name, driver_phone, driver_badge, driver_license,
          current_lat, current_lng, speed, bearing, status,
          camera_front_status, camera_rear_status, camera_side_status, camera_cabin_status
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
        ON CONFLICT (registration_number) DO UPDATE SET
          model = EXCLUDED.model,
          depot = EXCLUDED.depot,
          route_id = EXCLUDED.route_id,
          route_name = EXCLUDED.route_name,
          driver_name = EXCLUDED.driver_name,
          driver_phone = EXCLUDED.driver_phone,
          driver_badge = EXCLUDED.driver_badge,
          driver_license = EXCLUDED.driver_license,
          current_lat = EXCLUDED.current_lat,
          current_lng = EXCLUDED.current_lng,
          updated_at = CURRENT_TIMESTAMP;
      `, [
        id, reg, bus.model || 'Electric Low Floor Transit 12M', bus.depot || 'Central Transport Depot',
        bus.route_id || 'Route 1', bus.route_name || 'Corridor Transit Express',
        bus.driver_name || 'Assigned Operator', bus.driver_phone || '+91 90000 00000',
        bus.driver_badge || 'DRV-1001', bus.driver_license || 'DL-KA-2020-001',
        bus.current_lat || 12.9716, bus.current_lng || 77.5946,
        bus.speed || 35.0, bus.bearing || 90.0, bus.status || 'Active',
        bus.camera_front_status || 'Online', bus.camera_rear_status || 'Online',
        bus.camera_side_status || 'Online', bus.camera_cabin_status || 'Online'
      ]);

      return await this.getBusById(id);
    }

    /**
     * Retrieve all registered buses from Neon DB
     */
    async getAllBuses() {
      await this.initSchema();
      const rows = await this.query(`
        SELECT id, registration_number, model, depot, route_id, route_name,
               driver_name, driver_phone, driver_badge, driver_license,
               current_lat, current_lng, speed, bearing, status,
               camera_front_status, camera_rear_status, camera_side_status, camera_cabin_status,
               created_at, updated_at
        FROM buses
        ORDER BY registration_number ASC;
      `);

      return rows.map(r => ({
        id: r.id,
        registrationNumber: r.registration_number,
        model: r.model,
        depot: r.depot,
        routeId: r.route_id,
        routeName: r.route_name,
        driver: {
          name: r.driver_name,
          phone: r.driver_phone,
          badge: r.driver_badge,
          license: r.driver_license
        },
        lat: parseFloat(r.current_lat) || 12.9716,
        lng: parseFloat(r.current_lng) || 77.5946,
        speed: parseFloat(r.speed) || 35.0,
        bearing: parseFloat(r.bearing) || 90.0,
        status: r.status,
        cameras: {
          front: r.camera_front_status,
          rear: r.camera_rear_status,
          side: r.camera_side_status,
          cabin: r.camera_cabin_status
        },
        createdAt: r.created_at,
        updatedAt: r.updated_at
      }));
    }

    /**
     * Get a specific registered bus by ID
     */
    async getBusById(id) {
      await this.initSchema();
      const rows = await this.query(`
        SELECT * FROM buses WHERE id = $1 OR registration_number = $1 LIMIT 1;
      `, [id]);
      if (rows.length === 0) return null;
      const r = rows[0];
      return {
        id: r.id,
        registrationNumber: r.registration_number,
        model: r.model,
        depot: r.depot,
        routeId: r.route_id,
        routeName: r.route_name,
        driver: {
          name: r.driver_name,
          phone: r.driver_phone,
          badge: r.driver_badge,
          license: r.driver_license
        },
        lat: parseFloat(r.current_lat),
        lng: parseFloat(r.current_lng),
        speed: parseFloat(r.speed),
        bearing: parseFloat(r.bearing),
        status: r.status,
        cameras: {
          front: r.camera_front_status,
          rear: r.camera_rear_status,
          side: r.camera_side_status,
          cabin: r.camera_cabin_status
        }
      };
    }

    /**
     * Update bus GPS position and kinematic telemetry in Neon DB
     */
    async updateBusLocation(id, lat, lng, speed = 35.0, bearing = 90.0) {
      try {
        await this.query(`
          UPDATE buses SET current_lat = $1, current_lng = $2, speed = $3, bearing = $4, updated_at = CURRENT_TIMESTAMP
          WHERE id = $5 OR registration_number = $5;
        `, [lat, lng, speed, bearing, id]);
      } catch (e) {
        // Non-blocking telemetry warning
      }
    }

    // ==========================================
    // REAL-TIME AI HAZARD & DETECTION METHODS
    // ==========================================

    /**
     * Record a genuine AI detected road hazard or incident into Neon DB
     */
    async recordHazard(h) {
      await this.initSchema();
      const id = h.id || ('HAZ-' + Date.now().toString(36).toUpperCase() + Math.random().toString(36).substring(2, 5).toUpperCase());
      const gmapsUrl = h.google_maps_url || `https://www.google.com/maps?q=${h.latitude},${h.longitude}`;

      await this.query(`
        INSERT INTO hazards (
          id, bus_id, camera_channel, type, category, title, problem_description,
          confidence, severity, latitude, longitude, address, google_maps_url,
          depth_mm, width_mm, length_mm, distance_m, offending_plate, screenshot_base64,
          solution_action, work_order_id, status, detected_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, CURRENT_TIMESTAMP);
      `, [
        id, h.bus_id || 'KA-05-AB-1147', h.camera_channel || 'Front Optical 4K AI',
        h.type || 'ROAD_DEFECT', h.category || 'Road Anomaly',
        h.title || 'Road Hazard Detected', h.problem_description || 'Surface defect identified by AI',
        h.confidence || 95.0, h.severity || 3,
        h.latitude, h.longitude, h.address || 'Corridor GPS Fix', gmapsUrl,
        h.depth_mm || 0, h.width_mm || 0, h.length_mm || 0, h.distance_m || 0.0,
        h.offending_plate || null, h.screenshot_base64 || null,
        h.solution_action || 'Inspection dispatched', h.work_order_id || ('WO-' + Math.floor(1000 + Math.random() * 9000)),
        h.status || 'Reported'
      ]);

      return {
        id,
        ...h,
        google_maps_url: gmapsUrl,
        detected_at: new Date().toISOString()
      };
    }

    /**
     * Get all detected hazards from Neon DB
     */
    async getAllHazards(limit = 60) {
      await this.initSchema();
      const rows = await this.query(`
        SELECT id, bus_id, camera_channel, type, category, title, problem_description,
               confidence, severity, latitude, longitude, address, google_maps_url,
               depth_mm, width_mm, length_mm, distance_m, offending_plate, screenshot_base64,
               solution_action, work_order_id, status, detected_at
        FROM hazards
        ORDER BY detected_at DESC
        LIMIT $1;
      `, [limit]);

      return rows.map(r => ({
        id: r.id,
        busId: r.bus_id,
        camera: r.camera_channel,
        type: r.type,
        category: r.category,
        title: r.title,
        problem: r.problem_description,
        conf: parseFloat(r.confidence) || 95.0,
        severity: parseInt(r.severity) || 3,
        lat: parseFloat(r.latitude),
        lng: parseFloat(r.longitude),
        location: r.address,
        googleMapsUrl: r.google_maps_url || `https://www.google.com/maps?q=${r.latitude},${r.longitude}`,
        dimensions: {
          depthMm: parseInt(r.depth_mm) || 0,
          widthMm: parseInt(r.width_mm) || 0,
          lengthMm: parseInt(r.length_mm) || 0,
          distanceM: parseFloat(r.distance_m) || 0.0
        },
        plate: r.offending_plate,
        snapshot: r.screenshot_base64,
        solution: {
          action: r.solution_action,
          workOrder: r.work_order_id,
          status: r.status
        },
        status: r.status,
        detectedAt: r.detected_at,
        time: new Date(r.detected_at).toLocaleTimeString()
      }));
    }

    /**
     * Update hazard resolution status in Neon DB
     */
    async updateHazardStatus(hazardId, status) {
      await this.initSchema();
      await this.query(`UPDATE hazards SET status = $1 WHERE id = $2;`, [status, hazardId]);
      return true;
    }

    /**
     * Record live vehicle traffic telemetry
     */
    async recordTrafficTelemetry(t) {
      try {
        const id = 'TEL-' + Date.now().toString(36);
        await this.query(`
          INSERT INTO traffic_telemetry (
            id, bus_id, latitude, longitude, vehicle_count,
            cars_count, buses_count, trucks_count, two_wheelers_count, pedestrians_count,
            bottleneck_level, recorded_at
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, CURRENT_TIMESTAMP);
        `, [
          id, t.bus_id, t.latitude, t.longitude, t.vehicle_count || 0,
          t.cars_count || 0, t.buses_count || 0, t.trucks_count || 0,
          t.two_wheelers_count || 0, t.pedestrians_count || 0,
          t.bottleneck_level || 'Normal'
        ]);
      } catch (e) {
        // Non-blocking telemetry
      }
    }

    /**
     * Fetch real-time aggregate counts directly from Neon DB
     */
    async getHazardCounts() {
      try {
        const rows = await this.query(`
          SELECT 
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE UPPER(type) LIKE '%POTHOLE%' OR UPPER(title) LIKE '%POTHOLE%' OR UPPER(category) LIKE '%ROAD%') as potholes,
            COUNT(*) FILTER (WHERE UPPER(type) LIKE '%GARBAGE%' OR UPPER(title) LIKE '%GARBAGE%' OR UPPER(category) LIKE '%WASTE%') as garbage,
            COUNT(*) FILTER (WHERE severity >= 4) as critical
          FROM hazards;
        `);
        if (rows && rows.length > 0) {
          return {
            total: parseInt(rows[0].total) || 0,
            potholes: parseInt(rows[0].potholes) || 0,
            garbage: parseInt(rows[0].garbage) || 0,
            critical: parseInt(rows[0].critical) || 0
          };
        }
      } catch (e) {
        console.warn('Failed to fetch hazard counts from Neon DB:', e);
      }
      return null;
    }

    async testConnection() {
      try {
        const res = await this.query('SELECT 1 as connected;');
        return res && res.length > 0 && String(res[0].connected) === '1';
      } catch (e) {
        return false;
      }
    }
  }

  // Export singleton to global namespace
  global.NeonDB = new NeonDBClient();

  if (typeof window !== 'undefined') {
    global.NeonDB.initSchema().catch(err => {
      console.warn('Neon initial sync:', err.message);
    });
  }

})(typeof window !== 'undefined' ? window : this);
