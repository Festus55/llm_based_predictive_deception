## Workflow

1. `parse_dataset.py`: stream raw Cowrie JSON logs, sort events by time, and extract a simple "history + next command" relationship.
2. `process_sessions.py`: Reads the output of the parser and reconstructs the longest unique sequence for every session ID. 
3. `mk_sliding_windows.py`:Takes reconstructed sessions and creates a "Sliding Window" dataset. Instead of predicting just 1 command, it attempts to predict the next 6 commands (defined by WINDOW_SIZE).
