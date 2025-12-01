# ai_engine.py
import time
import json
import numpy as np
from datetime import datetime, timedelta
from clickhouse_driver import Client
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import requests

# --- Configuration ---
CLICKHOUSE_HOST = 'localhost'
DETECTION_INTERVAL_SECONDS = 1
TRAINING_DATA_SIZE = 50
MODEL_RETRAIN_LOG_COUNT = 50 # Retrain after this many new logs are processed
FLASK_NOTIFY_URL = "http://127.0.0.1:5000/notify_new_alert"

# --- State ---
model = None
scaler = None
last_model_train_time = None

# Initialize ClickHouse Client
try:
    client = Client(host=CLICKHOUSE_HOST)
    client.execute('SELECT 1')
    print("[AI_ENGINE] Successfully connected to ClickHouse.")
except Exception as e:
    print(f"[AI_ENGINE] FATAL: Could not connect to ClickHouse. Error: {e}")
    exit()

def get_training_data():
    """Fetches a large batch of recent historical data for training."""
    print("[AI_ENGINE] Fetching training data...")
    # Use an f-string to insert the limit directly into the query string.
    # We order by DESC to get the most recent logs for more relevant training.
    query = f"SELECT timestamp, hostname, user, source_ip FROM logs ORDER BY timestamp DESC LIMIT {TRAINING_DATA_SIZE}"
    logs = client.execute(query)
    return logs

def get_new_logs(last_processed_timestamp):
    
    """Fetches logs that have arrived since the last check."""
    # --- FIX IS HERE ---
    # Convert the datetime object to a string and insert it using an f-string.
    # The single quotes around {timestamp_str} are required for the SQL query.
    timestamp_str = last_processed_timestamp.isoformat()
    query = f"SELECT timestamp, hostname, user, source_ip FROM logs WHERE timestamp > '{timestamp_str}' ORDER BY timestamp ASC"
    logs = client.execute(query)
    return logs

def extract_features(log_batch):
    """Converts a batch of logs into a numerical feature matrix."""
    features = []
    for log in log_batch:
        # log format: (timestamp, hostname, user, source_ip)
        timestamp, _, user, source_ip = log
        
        dt = timestamp
        hour_of_day = dt.hour
        is_weekend = 1 if dt.weekday() >= 5 else 0
        
        # This is a simplified feature. In a real system, you'd have more complex logic.
        # For example, checking if the IP is new for this user, or if the user is admin.
        user_is_rare = 1 if user in ['root', 'guest'] else 0
        
        features.append([hour_of_day, is_weekend, user_is_rare])
        
    return np.array(features)

def train_model():
    """Trains the Isolation Forest model."""
    global model, scaler, last_model_train_time
    
    logs = get_training_data()
    if len(logs) < TRAINING_DATA_SIZE:
        print(f"[AI_ENGINE] Not enough data to train. Need {TRAINING_DATA_SIZE}, have {len(logs)}. Waiting...")
        return False

    print(f"[AI_ENGINE] Training model on {len(logs)} logs...")
    feature_matrix = extract_features(logs)
    
    scaler = StandardScaler().fit(feature_matrix)
    scaled_features = scaler.transform(feature_matrix)
    
    model = IsolationForest(n_estimators=100, contamination='auto', random_state=42)
    model.fit(scaled_features)
    
    last_model_train_time = datetime.utcnow()
    print("[AI_ENGINE] Model training complete.")
    return True

def detect_and_alert(new_logs):
    """Detects anomalies in new logs, writes them to the DB, and notifies the Flask app."""
    if not model or not scaler:
        print("[AI_ENGINE] Model not available for detection.")
        return

    if not new_logs:
        return
        
    print(f"[AI_ENGINE] Scanning {len(new_logs)} new logs for anomalies...")
    feature_matrix = extract_features(new_logs)
    scaled_features = scaler.transform(feature_matrix)
    
    predictions = model.predict(scaled_features)
    anomaly_scores = model.decision_function(scaled_features)

    alerts_to_insert = []
    for i, log in enumerate(new_logs):
        if predictions[i] == -1:
            timestamp, hostname, user, source_ip = log
            reason = "Anomalous login time or user type."
            
            # Format the alert data for both the database and the notification
            alert_details = {
                "user": user, 
                "source_ip": source_ip
            }
            alert_for_db = (
                datetime.utcnow(),
                timestamp,
                hostname,
                user,
                source_ip,
                float(anomaly_scores[i]),
                reason,
                json.dumps(alert_details)
            )
            alerts_to_insert.append(alert_for_db)

            # --- NEW: Notify the Flask app in real-time ---
            try:
                alert_payload = {
                    "alert_timestamp": str(datetime.utcnow()),
                    "event_timestamp": str(timestamp),
                    "hostname": hostname,
                    "user": user,
                    "source_ip": source_ip,
                    "anomaly_score": float(anomaly_scores[i]),
                    "reason": reason,
                    "event_details": json.dumps(alert_details)
                }
                requests.post(FLASK_NOTIFY_URL, json=alert_payload, timeout=2)
            except requests.exceptions.RequestException as e:
                print(f"[AI_ENGINE] Could not notify Flask app: {e}")


    if alerts_to_insert:
        print(f"🚨 Found {len(alerts_to_insert)} anomalies! Writing to database.")
        insert_query = """
        INSERT INTO alerts (alert_timestamp, event_timestamp, hostname, user, source_ip, anomaly_score, reason, event_details) 
        VALUES
        """
        client.execute(insert_query, alerts_to_insert)

def main_loop():
    """The main loop for the AI engine."""
    last_processed_timestamp = datetime(1970, 1, 1)
    logs_processed_since_retrain = 0

    while True:
        time.sleep(DETECTION_INTERVAL_SECONDS)

        if model is None:
            print("[AI_ENGINE] Model is not trained. Attempting to train...")
            train_model()
            continue

        # Check if it's time to retrain based on log count
        if logs_processed_since_retrain >= MODEL_RETRAIN_LOG_COUNT:
            print(f"[AI_ENGINE] Processed {logs_processed_since_retrain} logs since last train. Retraining model...")
            train_model()
            # Reset counter after any training attempt to wait for more new logs.
            logs_processed_since_retrain = 0
            # Continue to next loop to not detect on the same logs that were just used for training
            continue

        new_logs = get_new_logs(last_processed_timestamp)

        print(f"[AI_ENGINE] Retrieved {len(new_logs)} new logs since {last_processed_timestamp.isoformat()}.")
        if new_logs:
            detect_and_alert(new_logs)
            last_processed_timestamp = new_logs[-1][0]
            logs_processed_since_retrain += len(new_logs)
        else:
            print("[AI_ENGINE] No new logs to process.")

if __name__ == "__main__":
    main_loop()