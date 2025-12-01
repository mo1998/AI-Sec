# app.py
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from clickhouse_driver import Client
import json
from datetime import datetime, timedelta

# --- Configuration ---
CLICKHOUSE_HOST = 'localhost'
FLASK_PORT = 5000

# Initialize Flask App and SocketIO
app = Flask(__name__)
# Set a secret key for Flask-SocketIO
app.config['SECRET_KEY'] = 'your_secret_key_here!' 
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Initialize ClickHouse Client
try:
    client = Client(host=CLICKHOUSE_HOST)
    client.execute('SELECT 1')
    print("[APP] Successfully connected to ClickHouse.")
except Exception as e:
    print(f"[APP] FATAL: Could not connect to ClickHouse at {CLICKHOUSE_HOST}. Is Docker running? Error: {e}")
    exit()

@app.route('/')
def index():
    """Renders the main dashboard page."""
    return render_template('index.html')

@app.route('/api/alerts')
def get_alerts():
    """API endpoint to fetch the latest 50 alerts for the UI table."""
    try:
        query = "SELECT * FROM alerts ORDER BY alert_timestamp DESC LIMIT 50"
        alerts = client.execute(query)
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
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """API endpoint for dashboard statistics."""
    try:
        # Total alerts in the last 24 hours
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        query_total = f"SELECT count() FROM alerts WHERE alert_timestamp > '{one_day_ago.isoformat()}'"
        total_alerts = client.execute(query_total)[0][0]

        # Top 5 users with the most alerts
        query_top_users = """
        SELECT user, count() as count 
        FROM alerts 
        WHERE alert_timestamp > now() - INTERVAL 1 DAY 
        GROUP BY user 
        ORDER BY count DESC 
        LIMIT 5
        """
        top_users = client.execute(query_top_users)

        return jsonify({
            "total_alerts_24h": total_alerts,
            "top_users": [{"user": user, "count": count} for user, count in top_users]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/alerts/timeline')
def get_alerts_timeline():
    """API endpoint for the alerts timeline chart."""
    try:
        # Get alert counts per hour for the last 24 hours
        query_timeline = """
        SELECT 
            toStartOfHour(alert_timestamp) as hour, 
            count() as count 
        FROM alerts 
        WHERE alert_timestamp > now() - INTERVAL 1 DAY
        GROUP BY hour 
        ORDER BY hour ASC
        """
        timeline_data = client.execute(query_timeline)
        return jsonify([{"hour": str(hour), "count": count} for hour, count in timeline_data])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/ingest', methods=['POST'])
def ingest_log():
    """Receives log data from an agent and inserts it into ClickHouse."""
    # ... (This function remains the same as before) ...
    try:
        log_data = request.json
        if not log_data:
            return jsonify({"status": "error", "message": "No JSON data received"}), 400

        timestamp = datetime.fromisoformat(log_data['timestamp'])
        hostname = log_data['hostname']
        event_type = log_data['event_type']
        details = log_data['details']
        user = details.get('user', 'N/A')
        source_ip = details.get('source_ip', 'N/A')

        insert_query = "INSERT INTO logs (timestamp, hostname, event_type, user, source_ip) VALUES"
        client.execute(insert_query, [(timestamp, hostname, event_type, user, source_ip)])

        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"[APP] Error during ingestion: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/notify_new_alert', methods=['POST'])
def notify_new_alert():
    """Receives a new alert from the AI Engine and broadcasts it via WebSocket."""
    alert_data = request.json
    if alert_data:
        print(f"[APP] Received new alert notification, broadcasting...")
        # Broadcast the new alert to all connected clients
        socketio.emit('new_alert', alert_data)
    return jsonify({"status": "notified"}), 200

if __name__ == '__main__':
    # Use eventlet as the WSGI server
    socketio.run(app, host='0.0.0.0', port=FLASK_PORT, debug=True)