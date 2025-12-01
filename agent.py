# agent.py
import time
import random
from datetime import datetime, timezone, timedelta
import requests # Use requests library for HTTP

# --- Configuration ---
INGESTION_URL = "http://127.0.0.1:5000/ingest" # The new ingestion endpoint

# Normal behavior patterns
NORMAL_USERS = ['ubuntu', 'ec2-user', 'admin', 'deploy']
NORMAL_SOURCE_IPS = ['192.168.1.10', '10.0.0.5', '8.8.8.8']
NORMAL_HOURS = range(9, 18) # 9 AM to 5 PM

def generate_log_event(event_time):
    """Generates a single, realistic log event based on a given timestamp."""
    event_type = 'ssh_login_success'
    timestamp = event_time.isoformat()
    hour = event_time.hour

    is_time_anomalous = hour not in NORMAL_HOURS
    # Keep the 10% random anomaly for user/IP, independent of time
    is_user_ip_anomalous = random.random() < 0.1

    if is_time_anomalous or is_user_ip_anomalous:
        # --- Anomalous Event ---
        print(f"[AGENT] Generating ANOMALOUS event (time: {is_time_anomalous}, user/ip: {is_user_ip_anomalous})...")
        if is_user_ip_anomalous:
            # If user/IP is anomalous, generate anomalous details
            user = random.choice(['root', 'guest', 'testuser'] + NORMAL_USERS)
            source_ip = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
        else:
            # If only time is anomalous, user/IP can be normal
            user = random.choice(NORMAL_USERS)
            source_ip = random.choice(NORMAL_SOURCE_IPS)
    else:
        # --- Normal Event ---
        user = random.choice(NORMAL_USERS)
        source_ip = random.choice(NORMAL_SOURCE_IPS)

    event = {
        "timestamp": timestamp,
        "hostname": "web-server-01",
        "event_type": event_type,
        "details": {
            "user": user,
            "source_ip": source_ip,
            "authentication_method": "publickey"
        }
    }
    return event

def main():
    """Main loop for the agent."""
    print(f"[AGENT] Starting agent, sending data to {INGESTION_URL}")

    # --- Simulation Time ---
    # We start from the current time and move forward in simulated steps.
    simulated_time = datetime.now(timezone.utc)

    while True:
        try:
            # Generate event for the current simulated time
            event = generate_log_event(simulated_time)

            # Use requests.post to send data to the Flask app
            response = requests.post(INGESTION_URL, json=event, timeout=5)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

            print(f"[AGENT] Sent event for user '{event['details']['user']}' at {event['timestamp']}'")

            # --- Advance Simulation Time ---
            # Move simulated time forward by a random amount (e.g., 5 to 30 minutes)
            # This allows us to simulate a full day of logs in a shorter real-time period.
            time_increment_minutes = random.randint(5, 30)
            simulated_time += timedelta(minutes=time_increment_minutes)

            # Real-time sleep to control how fast we send events to the server
            time.sleep(0.5)

        except requests.exceptions.ConnectionError:
            print(f"[AGENT] Connection refused. Is the Flask app running at {INGESTION_URL}? Retrying in 5s...")
            time.sleep(5)
        except Exception as e:
            print(f"[AGENT] An error occurred: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()