# main.py
import threading
import socket
import json
import time
import numpy as np
from datetime import datetime
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# --- Configuration ---
HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 9999
DETECTION_INTERVAL_SECONDS = 15  # How often the AI engine checks for new logs
TRAINING_DATA_SIZE = 100  # How many logs are needed to train the initial model

# --- Shared State (Accessible by both threads) ---
log_data_store = []
lock = threading.Lock()
model = None
scaler = None
seen_ips = set()
frequent_users = {'ubuntu', 'ec2-user', 'admin', 'deploy'}

# ==============================================================================
# AI ENGINE FUNCTIONS
# ==============================================================================

def extract_features(event):
    """Converts a log event dictionary into a numerical feature vector."""
    global seen_ips

    details = event.get('details', {})
    user = details.get('user', 'unknown')
    source_ip = details.get('source_ip', '0.0.0.0')
    
    # Parse timestamp
    try:
        dt = datetime.fromisoformat(event['timestamp'])
        hour_of_day = dt.hour
        day_of_week = dt.weekday() # Monday=0, Sunday=6
        is_weekend = 1 if day_of_week >= 5 else 0
    except (ValueError, TypeError):
        hour_of_day, day_of_week, is_weekend = 12, 0, 0 # Default to a normal time

    # Behavioral features
    ip_is_new = 0
    if source_ip not in seen_ips:
        ip_is_new = 1
        seen_ips.add(source_ip)
        
    user_is_rare = 0
    if user not in frequent_users:
        user_is_rare = 1

    # The order of features is critical and must be consistent
    features = [
        hour_of_day,
        is_weekend,
        ip_is_new,
        user_is_rare,
    ]
    return np.array(features).reshape(1, -1)

def train_model(logs):
    """Trains the Isolation Forest model on a batch of logs."""
    global model, scaler
    print("[AI_ENGINE] Training new model...")
    
    # Extract features from all logs
    all_features = np.vstack([extract_features(log) for log in logs])
    
    # Standardize features
    scaler = StandardScaler().fit(all_features)
    scaled_features = scaler.transform(all_features)
    
    # Train the model
    # 'contamination' is the expected proportion of outliers.
    model = IsolationForest(n_estimators=100, contamination=0.1, random_state=42)
    model.fit(scaled_features)
    print("[AI_ENGINE] Model training complete.")

def detect_anomalies(new_logs):
    """Detects anomalies in new logs using the trained model."""
    global model, scaler
    if not model or not scaler:
        return

    print(f"[AI_ENGINE] Scanning {len(new_logs)} new events for anomalies...")
    for log in new_logs:
        features = extract_features(log)
        scaled_features = scaler.transform(features)
        
        # The model returns 1 for inliers (normal) and -1 for outliers (anomalies)
        prediction = model.predict(scaled_features)
        
        if prediction == -1:
            # Anomaly detected!
            print("\n" + "="*40)
            print("🚨 [ALERT] ANOMALY DETECTED! 🚨")
            print(json.dumps(log, indent=2))
            print("="*40 + "\n")

def ai_engine_loop():
    """The main loop for the AI engine, running in a thread."""
    print("[AI_ENGINE] Starting AI engine thread...")
    processed_log_count = 0
    
    while True:
        time.sleep(DETECTION_INTERVAL_SECONDS)
        
        # Safely get a copy of the logs
        with lock:
            all_logs = list(log_data_store)
            new_logs = all_logs[processed_log_count:]
        
        if len(new_logs) > 0:
            print(f"[AI_ENGINE] Fetched {len(new_logs)} new log events.")
            
            # If we don't have a model yet and have enough data, train one
            if model is None and len(all_logs) >= TRAINING_DATA_SIZE:
                train_model(all_logs)
                processed_log_count = len(all_logs)
            # If we have a model, use it to detect anomalies in new logs
            elif model is not None:
                detect_anomalies(new_logs)
                processed_log_count = len(all_logs)
        
        print(f"[AI_ENGINE] Total logs: {len(all_logs)}, Processed logs: {processed_log_count}")


# ==============================================================================
# SERVER FUNCTIONS
# ==============================================================================

def handle_client_connection(conn, addr):
    """Handles a single client connection."""
    print(f"[SERVER] Connected by {addr}")
    with conn:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            try:
                event_str = data.decode('utf-8')
                event = json.loads(event_str)
                # Safely append the event to the shared list
                with lock:
                    log_data_store.append(event)
            except json.JSONDecodeError:
                print(f"[SERVER] Failed to decode JSON from {addr}")
            except Exception as e:
                print(f"[SERVER] An error occurred: {e}")
    print(f"[SERVER] Connection with {addr} closed.")

def server_start():
    """Starts the TCP server, running in a thread."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"[SERVER] Server is listening on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            # Handle each client in a new thread
            client_thread = threading.Thread(target=handle_client_connection, args=(conn, addr))
            client_thread.start()


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    # Create and start the server in a background thread
    server_thread = threading.Thread(target=server_start, daemon=True)
    server_thread.start()

    # The AI engine will run in the main thread
    ai_engine_loop()