# run.py
import subprocess
import sys
import time
import signal
import os

# --- Configuration ---
# Define the commands to run each part of the application.
# Using a list is safer than a single string to prevent shell injection.
COMMANDS = {
    "Flask App": [sys.executable, "app.py"],
    "AI Engine": [sys.executable, "ai_engine.py"],
    "Agent": [sys.executable, "agent.py"]
}

# A list to keep track of the child processes
processes = []

def signal_handler(sig, frame):
    """Handles Ctrl+C to gracefully shut down all child processes."""
    print("\n[ORCHESTRATOR] Shutdown signal received. Terminating all processes...")
    for p in processes:
        if p.poll() is None:  # Check if the process is still running
            print(f"[ORCHESTRATOR] Terminating {p.args[1]} (PID: {p.pid})...")
            p.terminate() # Send SIGTERM

    # Give processes a moment to terminate gracefully
    time.sleep(2)

    # Force kill any processes that are still running
    for p in processes:
        if p.poll() is None:
            print(f"[ORCHESTRATOR] Force killing {p.args[1]} (PID: {p.pid})...")
            p.kill() # Send SIGKILL
    
    print("[ORCHESTRATOR] All processes terminated. Exiting.")
    sys.exit(0)

def run_command(name, command):
    """Runs a command as a subprocess and prints its output in real-time."""
    print(f"[ORCHESTRATOR] Starting {name}...")
    try:
        # Start the process
        # stdout and stderr are piped so we can capture and print them
        process = subprocess.Popen(
            command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            universal_newlines=True,
            bufsize=1
        )
        processes.append(process)

        # Stream the output
        for line in iter(process.stdout.readline, ''):
            print(f"[{name}] {line.strip()}")
        
        process.stdout.close()
        return_code = process.wait()

        if return_code:
            print(f"[ORCHESTRATOR] {name} exited with error code {return_code}")
        else:
            print(f"[ORCHESTRATOR] {name} finished successfully.")

    except FileNotFoundError:
        print(f"[ORCHESTRATOR] ERROR: Command not found - {command[0]}. Is it in your PATH?")
    except Exception as e:
        print(f"[ORCHESTRATOR] An unexpected error occurred while running {name}: {e}")

def main():
    """Main function to start all services."""
    # Register the signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    print("--- AI-SEC Application Orchestrator ---")
    print("Press Ctrl+C to stop all services.")
    print("--------------------------------------\n")

    # Check if ClickHouse is running by trying to connect to its port
    print("[ORCHESTRATOR] Checking for ClickHouse connection...")
    try:
        # This is a simple check. A real app might have a more robust health check.
        # We use the clickhouse-driver to perform a simple query.
        from clickhouse_driver import Client
        client = Client(host='localhost')
        client.execute('SELECT 1')
        print("[ORCHESTRATOR] ClickHouse is running.")
    except Exception as e:
        print(f"[ORCHESTRATOR] FATAL: Could not connect to ClickHouse. Please ensure it is running with 'docker-compose up -d'.")
        print(f"ClickHouse Error: {e}")
        sys.exit(1)

    # Start each service in its own thread to allow for concurrent execution
    # and real-time output streaming.
    import threading
    threads = []
    for name, command in COMMANDS.items():
        # We add a delay to give the previous service time to start up
        # (e.g., Flask needs to bind to the port before the agent tries to connect)
        time.sleep(0.1) 
        thread = threading.Thread(target=run_command, args=(name, command))
        threads.append(thread)
        thread.start()

    # Wait for all threads to complete (which they won't, unless a process crashes)
    for thread in threads:
        thread.join()

if __name__ == "__main__":
    main()