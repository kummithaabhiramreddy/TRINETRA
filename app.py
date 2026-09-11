import os
import re
import csv
import json
import time
import random
import logging
import threading
import urllib
import urllib.parse
import urllib.request
import urllib.error
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    pd = None
    HAS_PANDAS = False
from datetime import datetime
from flask import Flask, render_template, Response, jsonify, send_file, redirect, url_for, request

# Optional computer vision & edge AI dependencies (for serverless cloud compatibility)
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    cv2 = None
    np = None
    HAS_CV2 = False

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    YOLO = None
    HAS_YOLO = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=ASSETS_DIR,
    static_url_path="/assets"
)

# Test writability for serverless environments like Vercel (read-only filesystem)
LOG_FILE = os.path.join(BASE_DIR, "hazard_logs.csv")
try:
    test_file = os.path.join(BASE_DIR, ".write_test")
    with open(test_file, "w") as f:
        f.write("1")
    os.remove(test_file)
except Exception:
    LOG_FILE = os.path.join("/tmp", "hazard_logs.csv")

# Initial baseline counts
BASE_POTHOLES = 42
BASE_GARBAGE = 19

import socket

# Cache resolved IPs for Neon to bypass faulty or restricted local network DNS
_NEON_IP_CACHE = {}
_orig_getaddrinfo = socket.getaddrinfo

def _resilient_getaddrinfo(host, port, *args, **kwargs):
    try:
        return _orig_getaddrinfo(host, port, *args, **kwargs)
    except socket.gaierror:
        if isinstance(host, str) and ("neon.tech" in host or "aws.neon" in host):
            if host in _NEON_IP_CACHE:
                try:
                    return _orig_getaddrinfo(_NEON_IP_CACHE[host], port, *args, **kwargs)
                except Exception:
                    pass
            for doh_url in [
                f"https://dns.google/resolve?name={host}&type=A",
                f"https://cloudflare-dns.com/dns-query?name={host}&type=A"
            ]:
                try:
                    req = urllib.request.Request(doh_url, headers={"Accept": "application/dns-json", "User-Agent": "TRINETRA/1.0"})
                    with urllib.request.urlopen(req, timeout=4) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        ips = [ans["data"] for ans in data.get("Answer", []) if ans.get("type") == 1]
                        if ips:
                            _NEON_IP_CACHE[host] = ips[0]
                            return _orig_getaddrinfo(ips[0], port, *args, **kwargs)
                except Exception:
                    continue
        raise

socket.getaddrinfo = _resilient_getaddrinfo

# Neon Database Configuration (supports Vercel env vars like DATABASE_URL or POSTGRES_URL)
NEON_CONN_STRING = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("NEON_DATABASE_URL")
    or os.environ.get("POSTGRES_URL")
    or os.environ.get("NEON_CONN_STRING")
    or "postgresql://neondb_owner:npg_kCrMU0l9LViJ@ep-rapid-sunset-a54uayxa-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

def _derive_neon_sql_endpoint(conn_str):
    try:
        parsed = urllib.parse.urlparse(conn_str)
        if parsed.hostname and ("neon.tech" in parsed.hostname or "aws.neon" in parsed.hostname):
            base_host = parsed.hostname.replace("-pooler", "")
            return f"https://{base_host}/sql"
    except Exception:
        pass
    return "https://ep-rapid-sunset-a54uayxa.us-east-2.aws.neon.tech/sql"

NEON_SQL_ENDPOINT = os.environ.get("NEON_SQL_ENDPOINT") or _derive_neon_sql_endpoint(NEON_CONN_STRING)

def execute_neon_query(query, params=None, array_mode=False):
    """Execute raw SQL query over Neon serverless HTTP endpoint with automatic DNS fallback and retries."""
    body = {"query": query.strip()}
    if params is not None:
        body["params"] = [str(p) if p is not None else None for p in params]
    
    req_data = json.dumps(body).encode("utf-8")
    headers = {
        "Neon-Connection-String": NEON_CONN_STRING,
        "Content-Type": "application/json"
    }
    if array_mode:
        headers["Neon-Array-Mode"] = "true"
        headers["Neon-Raw-Text-Output"] = "true"

    for attempt in range(3):
        try:
            neon_req = urllib.request.Request(
                NEON_SQL_ENDPOINT,
                data=req_data,
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(neon_req, timeout=12) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="ignore")
            print(f"Neon HTTP Error {he.code}: {err_body}")
            try:
                return json.loads(err_body)
            except Exception:
                return {"message": err_body}
        except Exception as e:
            if attempt == 2:
                print(f"Neon Query Error (attempt {attempt + 1}): {e}")
            time.sleep(0.3 * (attempt + 1))
    return None

def async_log_hazard_to_neon(hazard_data):
    """Fire-and-forget background worker to log detection to Neon DB without delaying streaming FPS."""
    def _worker():
        try:
            query = """
            INSERT INTO hazards (
                id, bus_id, camera_channel, type, category, title, problem_description,
                confidence, severity, latitude, longitude, address, google_maps_url,
                depth_mm, width_mm, length_mm, distance_m, solution_action, work_order_id, status, detected_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, CURRENT_TIMESTAMP
            );
            """
            params = [
                hazard_data.get("id"),
                hazard_data.get("bus_id", "BMTC-KA-01-F-4021"),
                hazard_data.get("camera_channel", "Front Optical 4K AI"),
                hazard_data.get("type", "ROAD_DEFECT"),
                hazard_data.get("category", "CIVIC_INFRASTRUCTURE"),
                hazard_data.get("title", "Road Surface Anomaly"),
                hazard_data.get("problem_description", "Detected via Edge AI Vision Model"),
                hazard_data.get("confidence", 95.0),
                hazard_data.get("severity", 3),
                hazard_data.get("latitude", 12.9716),
                hazard_data.get("longitude", 77.5946),
                hazard_data.get("address", "Bengaluru Urban Corridor"),
                hazard_data.get("google_maps_url", f"https://www.google.com/maps?q={hazard_data.get('latitude', 12.9716)},{hazard_data.get('longitude', 77.5946)}"),
                hazard_data.get("depth_mm", 45),
                hazard_data.get("width_mm", 300),
                hazard_data.get("length_mm", 300),
                hazard_data.get("distance_m", 3.5),
                hazard_data.get("solution_action", "Civic inspection ticket auto-dispatched"),
                hazard_data.get("work_order_id", f"WO-{random.randint(1000, 9999)}"),
                hazard_data.get("status", "active")
            ]
            execute_neon_query(query, params)
        except Exception as e:
            print(f"Error async logging to Neon: {e}")

    threading.Thread(target=_worker, daemon=True).start()

# 1. Initialize Log File (Safe for serverless read-only environments)
try:
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Hazard_Type", "Severity", "Confidence", "Latitude", "Longitude"])
except Exception as e:
    print(f"Notice: Local CSV write skipped: {e}")

# 2. Camera Streaming Thread (Safe fallback when hardware webcam is absent)
class FastWebcamStream:
    def __init__(self, src=0):
        if not HAS_CV2:
            self.stream = None
            self.grabbed = False
            self.frame = None
            self.stopped = True
            return
        try:
            self.stream = cv2.VideoCapture(src)
            self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            (self.grabbed, self.frame) = self.stream.read()
            self.stopped = False
        except Exception:
            self.stream = None
            self.grabbed = False
            self.frame = None
            self.stopped = True

    def start(self):
        if not HAS_CV2 or self.stopped or not self.stream:
            return self
        threading.Thread(target=self.update, daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            if not self.grabbed:
                self.stop()
            else:
                (self.grabbed, self.frame) = self.stream.read()
            time.sleep(0.01)

    def read(self):
        return self.frame

    def stop(self):
        self.stopped = True
        if self.stream:
            try:
                self.stream.release()
            except Exception:
                pass

camera_stream = None
if HAS_CV2:
    try:
        camera_stream = FastWebcamStream(src=0).start()
    except Exception as e:
        print(f"Notice: Webcam stream init notice: {e}")
        camera_stream = None

# 3. Model Initializations (Safe fallback when running in cloud serverless mode)
pothole_model = None
garbage_model = None
base_model = None

if HAS_YOLO:
    POTHOLE_WEIGHT_FILE = os.path.join(BASE_DIR, "best.pt")
    GARBAGE_WEIGHT_FILE = os.path.join(BASE_DIR, "garbage_best.pt")

    try:
        if os.path.exists(POTHOLE_WEIGHT_FILE) and os.path.getsize(POTHOLE_WEIGHT_FILE) > 1024:
            pothole_model = YOLO(POTHOLE_WEIGHT_FILE)
            print("✅ Loaded Custom Pothole Weights (best.pt)")
        elif os.path.exists("yolov8n.pt"):
            pothole_model = YOLO("yolov8n.pt")
    except Exception as e:
        print(f"⚠️ Pothole model load notice: {e}")

    try:
        if os.path.exists(GARBAGE_WEIGHT_FILE) and os.path.getsize(GARBAGE_WEIGHT_FILE) > 1024:
            garbage_model = YOLO(GARBAGE_WEIGHT_FILE)
            print("✅ Loaded Custom Garbage Weights (garbage_best.pt)")
        elif os.path.exists("yolov8n.pt"):
            garbage_model = YOLO("yolov8n.pt")
    except Exception as e:
        print(f"⚠️ Garbage model load notice: {e}")

    try:
        if os.path.exists("yolov8n.pt"):
            base_model = YOLO("yolov8n.pt")
    except Exception:
        pass

BASE_LAT, BASE_LON = 12.9716, 77.5946
last_logged_time = 0

def generate_frames():
    global last_logged_time

    # Serverless cloud fallback when OpenCV or webcam hardware is not available
    if not HAS_CV2 or camera_stream is None or not HAS_YOLO or pothole_model is None:
        blank_jpeg = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
        )
        for _ in range(2):
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + blank_jpeg + b"\r\n")
            time.sleep(1.0)
        return

    while True:
        frame = camera_stream.read()
        if frame is None:
            time.sleep(0.05)
            continue

        h_frame, w_frame, _ = frame.shape
        annotated_frame = frame.copy()
        current_time = time.time()
        detected_hazards = []

        # --- A. DETECT OPERATOR / PERSON TO PREVENT FALSE ALARMS ---
        person_boxes = []
        if base_model is not None:
            try:
                base_results = base_model(frame, conf=0.35, imgsz=320, verbose=False)
                for box in base_results[0].boxes:
                    cls_name = base_model.names[int(box.cls[0])].lower()
                    if cls_name == "person":
                        person_boxes.append(list(map(int, box.xyxy[0])))
            except Exception:
                pass

        def inside_person(box_coords):
            bx1, by1, bx2, by2 = box_coords
            bcx, bcy = (bx1 + bx2) // 2, (by1 + by2) // 2
            for px1, py1, px2, py2 in person_boxes:
                if px1 <= bcx <= px2 and py1 <= bcy <= py2:
                    return True
            return False

        # --- B. HIGH-ACCURACY POTHOLE DETECTION ---
        if pothole_model is not None:
            try:
                p_res = pothole_model(frame, conf=0.42, imgsz=416, verbose=False)
                is_fallback_model = (pothole_model.model.names.get(0) == "person")

                for box in p_res[0].boxes:
                    cls_id = int(box.cls[0])
                    if is_fallback_model and cls_id == 0:
                        continue

                    coords = list(map(int, box.xyxy[0]))
                    x1, y1, x2, y2 = coords
                    box_w = x2 - x1
                    box_h = y2 - y1

                    if y1 < int(h_frame * 0.35):
                        continue
                    if box_h > (box_w * 2.2):
                        continue
                    if inside_person(coords):
                        continue

                    conf = float(box.conf[0])
                    area = box_w * box_h
                    detected_hazards.append({
                        "type": "Pothole",
                        "bbox": coords,
                        "conf": conf,
                        "area": area
                    })
            except Exception:
                pass

        # --- C. CUSTOM GARBAGE PILE DETECTION ---
        if garbage_model is not None:
            try:
                g_res = garbage_model(frame, conf=0.48, imgsz=640, verbose=False)
                for box in g_res[0].boxes:
                    coords = list(map(int, box.xyxy[0]))
                    if inside_person(coords):
                        continue

                    x1, y1, x2, y2 = coords
                    box_width = x2 - x1
                    box_height = y2 - y1
                    area = box_width * box_height

                    if y1 < int(h_frame * 0.25):
                        continue

                    conf = float(box.conf[0])
                    detected_hazards.append({
                        "type": "Garbage Pile",
                        "bbox": coords,
                        "conf": conf,
                        "area": area
                    })
            except Exception:
                pass

        # --- D. DRAW ANNOTATIONS ---
        for hazard in detected_hazards:
            h_type = hazard["type"]
            conf = hazard["conf"]
            x1, y1, x2, y2 = hazard["bbox"]

            color = (0, 0, 255) if h_type == "Pothole" else (0, 165, 255)

            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
            label_text = f"{h_type} {conf:.2f}"
            (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(annotated_frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
            cv2.putText(annotated_frame, label_text, (x1 + 3, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

        # --- E. NEON DATABASE & CSV TELEMETRY LOGGING ---
        if detected_hazards and (current_time - last_logged_time > 1.5):
            top = max(detected_hazards, key=lambda x: x["conf"])
            area = top["area"]
            conf = top["conf"]

            h_type_raw = top["type"]
            h_type = "POTHOLE" if "POTHOLE" in h_type_raw.upper() else "GARBAGE"
            h_title = "ASPHALT POTHOLE CRATER" if h_type == "POTHOLE" else "OVERFLOWING GARBAGE PILE"
            severity_str = "CRITICAL" if (area > 20000 or conf > 0.70) else ("MODERATE" if area > 8000 else "MINOR")
            severity_num = 5 if severity_str == "CRITICAL" else (3 if severity_str == "MODERATE" else 2)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            lat = round(BASE_LAT + random.uniform(-0.0008, 0.0008), 6)
            lon = round(BASE_LON + random.uniform(-0.0008, 0.0008), 6)
            haz_id = f"HAZ-{datetime.now().strftime('%m%d%H%M%S')}-{random.randint(10,99)}"

            # 1. Local CSV Backup
            try:
                with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([timestamp, top["type"], severity_str, f"{conf:.2f}", lat, lon])
            except Exception:
                pass

            # 2. Store in Neon Database Cloud
            async_log_hazard_to_neon({
                "id": haz_id,
                "bus_id": "BMTC-KA-01-F-4021",
                "camera_channel": "Front Optical 4K AI",
                "type": h_type,
                "category": "CIVIC_INFRASTRUCTURE",
                "title": h_title,
                "problem_description": f"Auto-detected {top['type']} via YOLOv8 model (Bounding Area: {area}px)",
                "confidence": round(float(conf) * 100, 1),
                "severity": severity_num,
                "latitude": lat,
                "longitude": lon,
                "address": "BMTC Route Corridor, Bengaluru",
                "status": "active"
            })

            last_logged_time = current_time

        ret, buffer = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
        if not ret:
            continue

        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")

# --- Routes ---

@app.route("/")
@app.route("/index")
@app.route("/index.html")
@app.route("/api/index")
@app.route("/api/index.py")
@app.route("/api")
@app.route("/api/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
@app.route("/login.html", methods=["GET", "POST"])
@app.route("/register", methods=["GET", "POST"])
@app.route("/register.html", methods=["GET", "POST"])
@app.route("/api/login", methods=["GET", "POST"])
@app.route("/api/index/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        return redirect(url_for("dashboard_view"))
    return render_template("login.html")

@app.route("/dashboard")
@app.route("/dashboard.html")
@app.route("/api/dashboard")
@app.route("/api/index/dashboard")
def dashboard_view():
    return render_template("dashboard.html")

@app.route("/camera")
@app.route("/camera.html")
@app.route("/api/camera")
@app.route("/api/index/camera")
def camera_view():
    return render_template("camera.html")

@app.route("/forgot-password")
@app.route("/forgot-password.html")
@app.route("/api/forgot-password")
@app.route("/api/index/forgot-password")
def forgot_password_view():
    return render_template("forgot-password.html")

@app.route("/report")
@app.route("/report.html")
@app.route("/api/report")
@app.route("/api/index/report")
def report_view():
    return render_template("report.html")

@app.route("/reports")
@app.route("/reports.html")
@app.route("/api/reports")
@app.route("/api/index/reports")
def reports_view():
    return render_template("reports.html")

@app.route("/video_feed")
def video_feed():
    # If no webcam or YOLO available (serverless/cloud), return 503 immediately
    # so the camera.html onerror handler fires and activates the browser camera fallback
    if not HAS_CV2 or camera_stream is None or not HAS_YOLO or pothole_model is None:
        return Response(
            "Camera hardware not available in this deployment environment.",
            status=503,
            mimetype="text/plain"
        )
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

# --- API Endpoints ---

@app.route("/api/detect_frame", methods=["POST", "OPTIONS"])
def detect_frame():
    """Analyze a single camera frame from browser and return detected bounding boxes and metrics."""
    if request.method == "OPTIONS":
        res = Response()
        res.headers["Access-Control-Allow-Origin"] = "*"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type"
        res.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        return res

    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image", "")
        detections = []

        if HAS_CV2 and HAS_YOLO and (pothole_model or garbage_model) and img_b64:
            import base64
            if "," in img_b64:
                img_b64 = img_b64.split(",", 1)[1]
            img_bytes = base64.b64decode(img_b64)
            nparr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is not None:
                h, w = frame.shape[:2]
                if pothole_model:
                    p_results = pothole_model.predict(frame, conf=0.35, verbose=False)
                    for r in p_results:
                        for box in r.boxes:
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            conf = float(box.conf[0])
                            detections.append({
                                "type": "POTHOLE",
                                "label": "POTHOLE (CRATER)",
                                "confidence": round(conf * 100, 1),
                                "severity": 4 if conf > 0.6 else 3,
                                "x": round(x1 / w, 4),
                                "y": round(y1 / h, 4),
                                "w": round((x2 - x1) / w, 4),
                                "h": round((y2 - y1) / h, 4),
                                "color": "#EF4444"
                            })
                if garbage_model:
                    g_results = garbage_model.predict(frame, conf=0.35, verbose=False)
                    for r in g_results:
                        for box in r.boxes:
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            conf = float(box.conf[0])
                            detections.append({
                                "type": "GARBAGE",
                                "label": "GARBAGE DUMP",
                                "confidence": round(conf * 100, 1),
                                "severity": 3 if conf > 0.6 else 2,
                                "x": round(x1 / w, 4),
                                "y": round(y1 / h, 4),
                                "w": round((x2 - x1) / w, 4),
                                "h": round((y2 - y1) / h, 4),
                                "color": "#00E5FF"
                            })

        flask_res = jsonify({
            "status": "success",
            "server_yolo_active": bool(HAS_CV2 and HAS_YOLO and (pothole_model or garbage_model)),
            "detections": detections
        })
        flask_res.headers["Access-Control-Allow-Origin"] = "*"
        return flask_res
    except Exception as e:
        flask_res = jsonify({"status": "error", "message": str(e), "detections": []})
        flask_res.headers["Access-Control-Allow-Origin"] = "*"
        return flask_res

@app.route("/api/metrics")
def get_metrics():
    """Return live metric counters directly from the Neon PostgreSQL Cloud database."""
    try:
        query = """
        SELECT 
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE UPPER(type) LIKE '%POTHOLE%' OR UPPER(title) LIKE '%POTHOLE%' OR UPPER(category) LIKE '%ROAD%') as potholes,
            COUNT(*) FILTER (WHERE UPPER(type) LIKE '%GARBAGE%' OR UPPER(title) LIKE '%GARBAGE%' OR UPPER(category) LIKE '%WASTE%') as garbage,
            COUNT(*) FILTER (WHERE severity >= 4) as critical
        FROM hazards;
        """
        res = execute_neon_query(query)
        if res and res.get("rows"):
            r = res["rows"][0]
            flask_res = jsonify({
                "total": int(r.get("total") or 0),
                "potholes": int(r.get("potholes") or 0),
                "garbage": int(r.get("garbage") or 0),
                "critical": int(r.get("critical") or 0),
                "source": "neon_database"
            })
            flask_res.headers["Access-Control-Allow-Origin"] = "*"
            return flask_res
    except Exception as e:
        print(f"Error reading metrics from Neon DB: {e}")

    # Fallback to local CSV
    pothole_detected = 0
    garbage_detected = 0
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                reader = list(csv.DictReader(f))
                pothole_detected = sum(1 for r in reader if str(r.get("Hazard_Type", "")).upper() == "POTHOLE")
                garbage_detected = sum(1 for r in reader if "GARBAGE" in str(r.get("Hazard_Type", "")).upper())
        except Exception as e:
            print(f"Error reading CSV: {e}")

    flask_res = jsonify({
        "total": BASE_POTHOLES + pothole_detected + BASE_GARBAGE + garbage_detected,
        "potholes": BASE_POTHOLES + pothole_detected,
        "garbage": BASE_GARBAGE + garbage_detected,
        "critical": 0,
        "source": "local_csv_fallback"
    })
    flask_res.headers["Access-Control-Allow-Origin"] = "*"
    return flask_res

@app.route("/api/hazards", methods=["GET", "POST", "OPTIONS"])
def handle_hazards():
    """Store or query detected hazards in Neon PostgreSQL Cloud."""
    if request.method == "OPTIONS":
        res = Response()
        res.headers["Access-Control-Allow-Origin"] = "*"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return res

    if request.method == "POST":
        try:
            data = request.get_json(force=True, silent=True) or {}
            haz_id = data.get("id") or f"HAZ-{datetime.now().strftime('%m%d%H%M%S')}-{random.randint(10,99)}"
            h_type = (data.get("type") or "POTHOLE").upper()
            h_title = data.get("title") or ("ASPHALT POTHOLE CRATER" if "POTHOLE" in h_type else "CIVIC HAZARD DETECTED")
            lat = float(data.get("latitude") or 12.9716)
            lng = float(data.get("longitude") or 77.5946)
            conf = float(data.get("confidence") or 96.5)
            severity = int(data.get("severity") or 4)
            bus_id = data.get("bus_id") or "BMTC-KA-01-F-4021"

            query = """
            INSERT INTO hazards (
                id, bus_id, camera_channel, type, category, title, problem_description,
                confidence, severity, latitude, longitude, address, google_maps_url,
                depth_mm, width_mm, length_mm, distance_m, solution_action, work_order_id, status, detected_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, CURRENT_TIMESTAMP
            ) RETURNING id, bus_id, type, title, confidence, severity, latitude, longitude, status, detected_at;
            """
            params = [
                haz_id, bus_id, "Front Optical 4K AI", h_type, "CIVIC_INFRASTRUCTURE",
                h_title, data.get("problem_description", "Manual / Edge trigger detection logged via Dashboard"),
                conf, severity, lat, lng, data.get("address", "Bengaluru Central Corridor"),
                f"https://www.google.com/maps?q={lat},{lng}",
                int(data.get("depth_mm") or 45), int(data.get("width_mm") or 300), int(data.get("length_mm") or 300),
                float(data.get("distance_m") or 3.5), "Civic action dispatched", f"WO-{random.randint(1000, 9999)}", "active"
            ]
            res = execute_neon_query(query, params)

            # Local CSV backup
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([timestamp, h_type, "CRITICAL" if severity >= 4 else "MODERATE", f"{conf/100:.2f}", lat, lng])
            except Exception:
                pass

            out = res.get("rows", [{}])[0] if (res and res.get("rows")) else {
                "id": haz_id,
                "type": h_type,
                "title": h_title,
                "confidence": conf,
                "severity": severity,
                "latitude": lat,
                "longitude": lng,
                "status": "active",
                "detected_at": datetime.now().isoformat()
            }
            flask_res = jsonify({"status": "success", "hazard": out})
            flask_res.headers["Access-Control-Allow-Origin"] = "*"
            return flask_res
        except Exception as e:
            flask_res = jsonify({"status": "error", "message": str(e)})
            flask_res.headers["Access-Control-Allow-Origin"] = "*"
            return flask_res, 500

    # GET: Return recent hazards
    limit = int(request.args.get("limit", 60))
    query = """
    SELECT id, bus_id, camera_channel, type, category, title, problem_description,
           confidence, severity, latitude, longitude, address, google_maps_url,
           status, detected_at
    FROM hazards
    ORDER BY detected_at DESC
    LIMIT $1;
    """
    res = execute_neon_query(query, [limit])
    rows = res.get("rows", []) if res else []
    flask_res = jsonify({"status": "success", "count": len(rows), "hazards": rows})
    flask_res.headers["Access-Control-Allow-Origin"] = "*"
    return flask_res

@app.route("/api/neon-config")
def get_neon_config():
    """Expose Neon SQL endpoint and connection configuration to frontend clients."""
    res = jsonify({
        "sqlEndpoint": NEON_SQL_ENDPOINT,
        "connectionString": NEON_CONN_STRING
    })
    res.headers["Access-Control-Allow-Origin"] = "*"
    return res

@app.route("/api/logs")
def get_logs():
    """Return hazard logs from CSV if available, or fall back to live Neon DB query."""
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                reader = list(csv.DictReader(f))
                if reader:
                    total = len(reader)
                    potholes = sum(1 for r in reader if str(r.get("Hazard_Type", "")).upper() == "POTHOLE")
                    garbage = sum(1 for r in reader if "GARBAGE" in str(r.get("Hazard_Type", "")).upper())
                    critical = sum(1 for r in reader if str(r.get("Severity", "")).upper() == "CRITICAL")
                    flask_res = jsonify({
                        "total_count": total,
                        "pothole_count": potholes,
                        "garbage_count": garbage,
                        "critical_count": critical,
                        "logs": reader[-15:],
                        "source": "local_csv"
                    })
                    flask_res.headers["Access-Control-Allow-Origin"] = "*"
                    return flask_res
        except Exception as e:
            print(f"Error reading CSV: {e}")

    # Fallback to querying live Neon database (critical for serverless Vercel runtime)
    try:
        query = """
        SELECT detected_at as "Timestamp", type as "Hazard_Type", severity as "Severity",
               confidence as "Confidence", latitude as "Latitude", longitude as "Longitude"
        FROM hazards
        ORDER BY detected_at DESC
        LIMIT 15;
        """
        res = execute_neon_query(query)
        if res and res.get("rows"):
            rows = res["rows"]
            total = len(rows)
            potholes = sum(1 for r in rows if "POTHOLE" in str(r.get("Hazard_Type", "")).upper())
            garbage = sum(1 for r in rows if "GARBAGE" in str(r.get("Hazard_Type", "")).upper())
            critical = sum(1 for r in rows if int(r.get("Severity") or 0) >= 4)
            flask_res = jsonify({
                "total_count": total,
                "pothole_count": potholes,
                "garbage_count": garbage,
                "critical_count": critical,
                "logs": rows,
                "source": "neon_database"
            })
            flask_res.headers["Access-Control-Allow-Origin"] = "*"
            return flask_res
    except Exception as err:
        print(f"Error querying logs from Neon DB: {err}")

    flask_res = jsonify({"total_count": 0, "pothole_count": 0, "garbage_count": 0, "critical_count": 0, "logs": [], "source": "none"})
    flask_res.headers["Access-Control-Allow-Origin"] = "*"
    return flask_res

@app.route("/download/csv")
def download_csv():
    """Export live detected hazards from Neon PostgreSQL Cloud to CSV."""
    try:
        query = "SELECT id, bus_id, type, category, title, confidence, severity, latitude, longitude, address, status, detected_at FROM hazards ORDER BY detected_at DESC;"
        res = execute_neon_query(query)
        if res and res.get("rows"):
            rows = res["rows"]
            csv_path = os.path.join(BASE_DIR, "neon_hazards_export.csv")
            # If BASE_DIR is read-only (e.g. Vercel lambda), write to /tmp
            if not os.access(BASE_DIR, os.W_OK):
                csv_path = os.path.join("/tmp", "neon_hazards_export.csv")

            fields = list(rows[0].keys()) if rows else []
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            return send_file(csv_path, as_attachment=True, download_name=f"neon_hazards_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    except Exception as e:
        print(f"Error exporting from Neon: {e}")

    if os.path.exists(LOG_FILE):
        return send_file(LOG_FILE, as_attachment=True)
    return "No CSV found", 404

@app.route("/logo-lockup.png")
def serve_logo_lockup():
    target = os.path.join(BASE_DIR, "logo-lockup.png")
    if os.path.exists(target):
        return send_file(target, mimetype="image/png")
    return send_file(os.path.join(TEMPLATES_DIR, "logo-lockup.png"), mimetype="image/png")

@app.route("/logo.png")
def serve_logo():
    target = os.path.join(BASE_DIR, "logo.png")
    if os.path.exists(target):
        return send_file(target, mimetype="image/png")
    return send_file(os.path.join(TEMPLATES_DIR, "logo.png"), mimetype="image/png")

@app.route("/api/neon-sql", methods=["POST", "OPTIONS"])
def proxy_neon_sql():
    if request.method == "OPTIONS":
        res = Response()
        res.headers["Access-Control-Allow-Origin"] = "*"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type, Neon-Connection-String, Neon-Raw-Text-Output, Neon-Array-Mode"
        res.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        return res

    try:
        data = request.get_json(force=True, silent=True) or {}
        query = data.get("query", "").strip()
        params = data.get("params", [])

        if not query:
            flask_res = jsonify({"error": "No query provided"})
            flask_res.headers["Access-Control-Allow-Origin"] = "*"
            return flask_res, 400

        res_data = execute_neon_query(query, params, array_mode=True)
        if res_data is None:
            flask_res = jsonify({"message": "Neon database query failed"})
            flask_res.headers["Access-Control-Allow-Origin"] = "*"
            return flask_res, 502

        flask_res = jsonify(res_data)
        flask_res.headers["Access-Control-Allow-Origin"] = "*"
        return flask_res
    except Exception as e:
        flask_res = jsonify({"error": str(e)})
        flask_res.headers["Access-Control-Allow-Origin"] = "*"
        return flask_res, 500

@app.route("/<path:filename>")
def serve_static_asset(filename):
    clean = filename.strip("/")
    if clean.startswith("api/index.py/"):
        clean = clean[len("api/index.py/"):]
    elif clean.startswith("api/index/"):
        clean = clean[len("api/index/"):]
    elif clean in ("api/index", "api/index.py", "api"):
        return render_template("index.html")

    if clean in ("dashboard", "dashboard.html"):
        return render_template("dashboard.html")
    if clean in ("login", "login.html", "register", "register.html", "signup", "signup.html"):
        return render_template("login.html")
    if clean in ("camera", "camera.html"):
        return render_template("camera.html")
    if clean in ("forgot-password", "forgot-password.html"):
        return render_template("forgot-password.html")
    if clean in ("report", "report.html"):
        return render_template("report.html")
    if clean in ("reports", "reports.html"):
        return render_template("reports.html")
    if clean in ("dummy", "dummy.html"):
        return render_template("dummy.html")
    if clean in ("index", "index.html"):
        return render_template("index.html")

    for folder in [BASE_DIR, TEMPLATES_DIR, ASSETS_DIR]:
        path = os.path.join(folder, clean)
        if os.path.isfile(path):
            return send_file(path)
        if clean.startswith("assets/"):
            sub_path = os.path.join(folder, clean[7:])
            if os.path.isfile(sub_path):
                return send_file(sub_path)
    return "Not Found", 404

class VercelPathMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        resolved_path = None
        qs = environ.get("QUERY_STRING", "")
        if qs and ("path=" in qs or "__path__=" in qs):
            try:
                params = urllib.parse.parse_qs(qs)
                raw = params.get("path", [""])[0] or params.get("__path__", [""])[0]
                clean = urllib.parse.unquote(raw).split("?")[0].strip()
                if clean and not any(ch in clean for ch in ("$", "(", ")", "*")):
                    resolved_path = "/" + clean.lstrip("/")
                elif clean == "" or clean == "/":
                    resolved_path = "/"

                modified = False
                if "path" in params:
                    del params["path"]
                    modified = True
                if "__path__" in params:
                    del params["__path__"]
                    modified = True
                if modified:
                    environ["QUERY_STRING"] = urllib.parse.urlencode(params, doseq=True)
            except Exception:
                pass

        if not resolved_path:
            for h in (
                "HTTP_X_FORWARDED_PATH",
                "HTTP_X_FORWARDED_URI",
                "HTTP_X_MATCHED_PATH",
                "RAW_URI",
                "REQUEST_URI",
            ):
                val = environ.get(h, "")
                if (
                    val
                    and not val.startswith("/api/index")
                    and not any(ch in val for ch in ("$", "(", ")", "*"))
                ):
                    resolved_path = "/" + val.split("?")[0].lstrip("/")
                    break

        if not resolved_path:
            route_matches = environ.get("HTTP_X_NOW_ROUTE_MATCHES", "")
            if route_matches:
                try:
                    params = urllib.parse.parse_qs(route_matches)
                    match_val = params.get("1", [""])[0] or params.get("path", [""])[0]
                    if match_val and not any(ch in match_val for ch in ("$", "(", ")", "*")):
                        resolved_path = "/" + match_val.split("?")[0].lstrip("/")
                except Exception:
                    pass

        if resolved_path:
            environ["PATH_INFO"] = resolved_path
        else:
            path_info = environ.get("PATH_INFO", "")
            if path_info in ("/api/index", "/api/index.py", "/api/", "/api", ""):
                environ["PATH_INFO"] = "/"

        return self.wsgi_app(environ, start_response)

if not getattr(app, "_vercel_middleware_applied", False):
    app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
    app._vercel_middleware_applied = True

if __name__ == "__main__":
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)