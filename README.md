
# AI-Sec - Real-Time Anomaly Detection Dashboard

AI-Sec is a proof-of-concept security monitoring tool that uses machine learning to detect anomalies in real-time. It consists of a log generation agent, a data ingestion and visualization dashboard powered by Flask, and an AI engine for anomaly detection, all backed by a ClickHouse database.

## Features

- **Real-Time Log Ingestion:** An agent generates simulated log data and sends it to a Flask application.
- **AI-Powered Anomaly Detection:** An AI engine uses an Isolation Forest model to identify anomalous events in the log stream.
- **Real-Time Dashboard:** A web-based dashboard visualizes key metrics, including total events, anomalies detected, threats mitigated, active threats, and average latency.
- **Interactive Charts:** The dashboard includes charts for event activity over time, threats by severity, and event type distribution, all powered by Chart.js.
- **Scalable Data Store:** Utilizes ClickHouse, a fast, open-source, column-oriented database management system, for storing and querying log data.
- **Containerized Database:** The ClickHouse database runs in a Docker container for easy setup and deployment.

## Architecture

The project is composed of several key components:

- **`agent.py`**: A script that simulates log generation (e.g., SSH logins) and sends them to the Flask application. It's designed to produce both normal and anomalous events.
- **`app.py`**: A Flask web application that serves the main dashboard. It provides the following:
  - An `/ingest` endpoint to receive and store log data from the agent into the ClickHouse database.
  - A real-time dashboard to visualize security metrics.
  - API endpoints (`/api/alerts`, `/api/metrics`) to feed data to the dashboard.
- **`ai_engine.py`**: The core of the anomaly detection system. It periodically fetches new logs from the ClickHouse database, uses a `scikit-learn` Isolation Forest model to detect anomalies, and writes any detected anomalies to an `alerts` table.
- **`run.py`**: An orchestrator script that simplifies starting and stopping all the application's components (`app.py`, `ai_engine.py`, `agent.py`).
- **`docker-compose.yml`**: A Docker Compose file to easily set up and run the ClickHouse database container.
- **`init.sql`**: An SQL script that initializes the necessary database tables when the ClickHouse container is first started.
- **`templates/index.html`**: A single-page HTML file that contains the structure, styling, and JavaScript for the real-time dashboard.

## Getting Started

### Prerequisites

- Python 3.7+
- Docker and Docker Compose
- The Python packages listed in `requirements.txt`

### Installation and Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd AI-Sec
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the ClickHouse database:**
   ```bash
   docker-compose up -d
   ```
   This will start a ClickHouse container in the background and create the necessary tables using `init.sql`.

### Running the Application

To run the entire application, use the `run.py` orchestrator script:

```bash
python run.py
```

This will:
1. Check for a connection to the ClickHouse database.
2. Start the Flask web server.
3. Start the AI engine.
4. Start the log generation agent.

You will see output from all three components in your terminal, prefixed with their respective names (e.g., `[Flask App]`, `[AI Engine]`, `[Agent]`).

To stop all services, press `Ctrl+C` in the terminal where `run.py` is running.

### Accessing the Dashboard

Once the application is running, open your web browser and navigate to:

[http://127.0.0.1:5000](http://127.0.0.1:5000)

You should see the AI-Sec Real-Time Dashboard, which will start populating with data as it's generated and processed.
