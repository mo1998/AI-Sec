# app.py
from flask import Flask, render_template, request, jsonify
from clickhouse_driver import Client
import json
from datetime import datetime

# --- Configuration ---
CLICKHOUSE_HOST = 'localhost'
FLASK_PORT = 5000

# Initialize Flask App
app = Flask(__name__)

# Initialize ClickHouse Client
try:
    client = Client(host=CLICKHOUSE_HOST)
    client.execute('SELECT 1') # Test connection
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
    """API endpoint to fetch alerts for the UI."""
    try:
        # Fetch the 50 most recent alerts
        query = "SELECT * FROM alerts ORDER BY alert_timestamp DESC LIMIT 50"
        alerts = client.execute(query)
        
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
        return jsonify({"error": str(e)}), 500

@app.route('/ingest', methods=['POST'])
def ingest_log():
    """Receives log data from an agent and inserts it into ClickHouse."""
    try:
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
        insert_query = """
        INSERT INTO logs (timestamp, hostname, event_type, user, source_ip) 
        VALUES
        """
        client.execute(insert_query, [(timestamp, hostname, event_type, user, source_ip)])

        return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"[APP] Error during ingestion: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Running in debug mode is not recommended for production
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=True)