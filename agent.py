# agent.py
import time
import random
from datetime import datetime, timezone
import requests # Use requests library for HTTP

# --- Configuration ---
INGESTION_URL = "http://127.0.0.1:5000/ingest" # The new ingestion endpoint

# Normal behavior patterns
NORMAL_USERS = ['ubuntu', 'ec2-user', 'admin', 'deploy']
NORMAL_SOURCE_IPS = ['192.168.1.10', '10.0.0.5', '8.8.8.8']
NORMAL_HOURS = range(9, 18) # 9 AM to 5 PM

def generate_log_event():
    """Generates a single, realistic log event. Sometimes it's anomalous."""
    event_type = 'ssh_login_success'
    timestamp = datetime.now(timezone.utc).isoformat()

    # 90% chance of generating a normal event
    is_anomalous = random.random() < 0.1

    if is_anomalous:
        # --- Anomalous Event ---
        print("[AGENT] Generating ANOMALOUS event...")
        # Pick a rare user or a normal user at a weird time
        user = random.choice(['root', 'guest', 'testuser'] + NORMAL_USERS)
        hour = random.choice([h for h in range(24) if h not in NORMAL_HOURS])
        source_ip = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
    else:
        # --- Normal Event ---
        user = random.choice(NORMAL_USERS)
        hour = random.choice(NORMAL_HOURS)
        source_ip = random.choice(NORMAL_SOURCE_IPS)

    # Simulate the event happening at the chosen hour
    now = datetime.now()
    event_time = now.replace(hour=hour, minute=random.randint(0,59), second=0, microsecond=0)
    timestamp = event_time.isoformat()

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
    while True:
        try:
            event = generate_log_event()
            
            # Use requests.post to send data to the Flask app
            response = requests.post(INGESTION_URL, json=event, timeout=5)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            
            print(f"[AGENT] Sent event for user '{event['details']['user']}' from IP '{event['details']['source_ip']}'")
            
            time.sleep(random.randint(1, 5))

        except requests.exceptions.ConnectionError:
            print(f"[AGENT] Connection refused. Is the Flask app running at {INGESTION_URL}? Retrying in 5s...")
            time.sleep(5)
        except Exception as e:
            print(f"[AGENT] An error occurred: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()