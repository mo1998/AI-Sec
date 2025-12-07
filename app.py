# app.py
from flask import Flask, render_template, request, jsonify, g
from clickhouse_driver import Client
import json
from datetime import datetime
import math

# --- Configuration ---
CLICKHOUSE_HOST = 'localhost'
FLASK_PORT = 5000

# Initialize Flask App
app = Flask(__name__)

# --- Database Connection Management ---
def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        try:
            g.db = Client(host=CLICKHOUSE_HOST)
            g.db.execute('SELECT 1') # Test connection
            print("[APP] New ClickHouse connection established.")
        except Exception as e:
            # This will be caught by the error handler in the route
            raise Exception(f"FATAL: Could not connect to ClickHouse at {CLICKHOUSE_HOST}. Is Docker running? Error: {e}")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    """Closes the database connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.disconnect()
        print("[APP] ClickHouse connection closed.")

# --- Routes ---
@app.route('/')
def index():
    """Renders the main dashboard page."""
    return render_template('index.html')

@app.route('/api/alerts')
def get_alerts():
    """API endpoint to fetch alerts for the UI."""
    try:
        db = get_db()
        # Fetch the 50 most recent alerts
        query = "SELECT * FROM alerts ORDER BY alert_timestamp DESC LIMIT 50"
        alerts = db.execute(query)
        
        # Convert to a list of dicts for JSON serialization
        alerts_list = [
            {
                "alert_timestamp": str(alert[0]),
                "event_timestamp": str(alert[1]),
                "hostname": alert[2],
                "user": alert[3],
                "source_ip": alert[4],
                "anomaly_score": alert[5],
                "reason": alert[6],
                "event_details": alert[7]
            } for alert in alerts
        ]
        return jsonify(alerts_list)
    except Exception as e:
        print(f"[APP] Error in /api/alerts: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/ingest', methods=['POST'])
def ingest_log():
    """Receives log data from an agent and inserts it into ClickHouse."""
    try:
        db = get_db()
        log_data = request.json
        if not log_data:
            return jsonify({"status": "error", "message": "No JSON data received"}), 400

        # Extract data from the structured log
        timestamp = datetime.fromisoformat(log_data['timestamp'])
        hostname = log_data['hostname']
        event_type = log_data['event_type']
        details = log_data['details']
        user = details.get('user', 'N/A')
        source_ip = details.get('source_ip', 'N/A')

        # Insert into the 'logs' table
        insert_query = "INSERT INTO logs (timestamp, hostname, event_type, user, source_ip) VALUES"
        db.execute(insert_query, [(timestamp, hostname, event_type, user, source_ip)])

        return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"[APP] Error during ingestion: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/metrics')
def get_metrics():
    """API endpoint to fetch real-time metrics for the dashboard."""
    try:
        db = get_db()
        # --- Summary Cards ---
        total_events = db.execute("SELECT count() FROM logs")[0][0]
        anomalies_detected = db.execute("SELECT count() FROM alerts")[0][0]
        
        threats_mitigated = db.execute("SELECT count() FROM alerts WHERE reason LIKE '%%Blocked%%' OR reason LIKE '%%Mitigated%%'")[0][0]
        
        active_threats = db.execute("SELECT count() FROM alerts WHERE alert_timestamp >= now() - INTERVAL 1 HOUR")[0][0]
        
        avg_latency_sec = db.execute("SELECT avg(toUInt64(alert_timestamp) - toUInt64(event_timestamp)) FROM alerts WHERE alert_timestamp >= event_timestamp")[0][0]
        avg_latency_ms = 0
        if avg_latency_sec is not None and not math.isnan(avg_latency_sec):
            avg_latency_ms = avg_latency_sec * 1000

        # --- Charts ---
        severity_query = """
        SELECT
            CASE
                WHEN anomaly_score > 0.9 THEN 'Critical'
                WHEN anomaly_score > 0.7 THEN 'High'
                WHEN anomaly_score > 0.5 THEN 'Medium'
                ELSE 'Low'
            END AS severity,
            count()
        FROM alerts
        GROUP BY severity
        """
        severity_results = db.execute(severity_query)
        severity_data = {row[0]: row[1] for row in severity_results}
        
        event_type_query = "SELECT event_type, count() FROM logs GROUP BY event_type"
        event_type_results = db.execute(event_type_query)
        event_type_data = {row[0]: row[1] for row in event_type_results}

        recent_events_query = """
        SELECT
            toStartOfSecond(CAST(timestamp AS DateTime64(3))) AS event_time,
            count()
        FROM logs
        WHERE timestamp >= now() - INTERVAL 30 SECOND
        GROUP BY event_time
        ORDER BY event_time
        """
        recent_events = db.execute(recent_events_query)

        metrics = {
            "total_events": total_events,
            "anomalies_detected": anomalies_detected,
            "threats_mitigated": threats_mitigated,
            "active_threats": active_threats,
            "avg_latency": round(avg_latency_ms),
            "system_status": "Online",
            "severity_distribution": {
                "Critical": severity_data.get('Critical', 0),
                "High": severity_data.get('High', 0),
                "Medium": severity_data.get('Medium', 0),
                "Low": severity_data.get('Low', 0),
            },
            "event_type_distribution": event_type_data,
            "recent_events": [{"time": str(row[0]), "count": row[1]} for row in recent_events]
        }
        return jsonify(metrics)

    except Exception as e:
        print(f"[APP] Error fetching metrics: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # For production, run with a proper WSGI server like Gunicorn or uWSGI
    # Example: gunicorn --workers 4 --bind 0.0.0.0:5000 app:app
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=True)