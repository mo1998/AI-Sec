# ai_engine.py
import time
import json
import numpy as np
from datetime import datetime, timedelta
from clickhouse_driver import Client
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# --- Configuration ---
CLICKHOUSE_HOST = 'localhost'
DETECTION_INTERVAL_SECONDS = 10
TRAINING_DATA_SIZE = 100
MODEL_RETRAIN_INTERVAL_HOURS = 6

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
    """Fetches a large batch of historical data for training."""
    print("[AI_ENGINE] Fetching training data...")
    # Use an f-string to insert the limit directly into the query string.
    query = f"SELECT timestamp, hostname, user, source_ip FROM logs ORDER BY timestamp ASC LIMIT {TRAINING_DATA_SIZE}"
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
    """Detects anomalies in new logs and writes them to the alerts table."""
    if not model or not scaler:
        print("[AI_ENGINE] Model not available for detection.")
        return

    if not new_logs:
        return
        
    print(f"[AI_ENGINE] Scanning {len(new_logs)} new logs for anomalies...")
    feature_matrix = extract_features(new_logs)
    scaled_features = scaler.transform(feature_matrix)
    
    # The model returns 1 for inliers (normal) and -1 for outliers (anomalies)
    predictions = model.predict(scaled_features)
    anomaly_scores = model.decision_function(scaled_features)

    alerts_to_insert = []
    for i, log in enumerate(new_logs):
        if predictions[i] == -1:
            timestamp, hostname, user, source_ip = log
            reason = "Anomalous login time or user type."
            alert = (
                datetime.utcnow(),  # alert_timestamp
                timestamp,         # event_timestamp
                hostname,
                user,
                source_ip,
                float(anomaly_scores[i]),
                reason,
                json.dumps({"user": user, "source_ip": source_ip}) # event_details
            )
            alerts_to_insert.append(alert)

    if alerts_to_insert:
        print(f"🚨 Found {len(alerts_to_insert)} anomalies! Writing to database.")
        insert_query = """
        INSERT INTO alerts (alert_timestamp, event_timestamp, hostname, user, source_ip, anomaly_score, reason, event_details) 
        VALUES
        """
        client.execute(insert_query, alerts_to_insert)

def main_loop():
    """The main loop for the AI engine."""
    last_processed_timestamp = datetime(1970, 1, 1) # Start from the beginning
    
    # Initial model training
    if not train_model():
        print("[AI_ENGINE] Initial model training failed. Will retry.")
        # We don't exit, we'll just try again on the next loop

    while True:
        print(f"[AI_ENGINE] Sleeping for {DETECTION_INTERVAL_SECONDS} seconds...")
        time.sleep(DETECTION_INTERVAL_SECONDS)
        
        # Check if it's time to retrain the model
        if last_model_train_time and (datetime.utcnow() - last_model_train_time) > timedelta(hours=MODEL_RETRAIN_INTERVAL_HOURS):
            print("[AI_ENGINE] Model retrain interval reached. Retraining...")
            train_model()

        # Fetch and process new logs
        new_logs = get_new_logs(last_processed_timestamp)
        
        if new_logs:
            detect_and_alert(new_logs)
            # Update the timestamp to the latest one we've seen
            last_processed_timestamp = new_logs[-1][0]
        else:
            print("[AI_ENGINE] No new logs to process.")

if __name__ == "__main__":
    main_loop()