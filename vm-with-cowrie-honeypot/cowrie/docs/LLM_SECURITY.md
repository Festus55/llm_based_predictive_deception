# LLM Security and Resource Monitoring

This document describes the security and monitoring features added to the LLM-based Cowrie honeypot for safe long-running deployments.

## Input Sanitization

To protect against LLM prompt injection attacks, Cowrie now includes automatic input sanitization before commands are sent to the LLM.

### Features

- **ANSI Escape Sequence Removal**: Strips terminal escape sequences that could be used to manipulate responses
- **Prompt Injection Detection**: Identifies and neutralizes common prompt injection patterns like:
  - "Ignore previous instructions..."
  - "Disregard all rules..."
  - "You are now..."
  - "Forget your programming..."
  - And more
- **Command Length Limiting**: Prevents token exhaustion attacks by limiting command length
- **Sanitization Logging**: Optionally logs all sanitization actions for security analysis

### Configuration

Add the following to your `cowrie.cfg` under the `[llm]` section:

```ini
[llm]
# Maximum command length to send to LLM (prevents token exhaustion)
# Commands longer than this will be truncated
# (default: 1000)
max_command_length = 1000

# Log sanitization actions (ANSI removal, injection detection, etc.)
# Useful for security analysis and tuning
# (default: true)
log_sanitization = true
```

### How It Works

The sanitization happens transparently in `protocol.py`:

1. User enters a command
2. Command is sanitized before being sent to LLM:
   - ANSI sequences are stripped
   - Prompt injection patterns are detected
   - If injection is detected, dangerous words are replaced with safe alternatives
   - Command is truncated if too long
3. Sanitized command is sent to LLM
4. Response is returned to user

This maintains the honeypot illusion while protecting the LLM from manipulation.

## Resource Monitoring

For long-running deployments (multiple days), Cowrie now includes optional resource monitoring to detect memory leaks, thread accumulation, and other issues.

### Features

- **Memory Tracking**: Monitors RSS (Resident Set Size) and VMS (Virtual Memory Size)
- **Thread Count**: Tracks active thread count
- **Open File Descriptors**: Monitors file handle usage
- **Connection Tracking**: Counts active network connections
- **CPU Usage**: Tracks CPU percentage
- **Delta Reporting**: Shows changes from initial state
- **Configurable Interval**: Set monitoring frequency

### Configuration

Add the following to your `cowrie.cfg`:

```ini
[resource_monitor]
# Enable periodic resource monitoring
# Logs memory usage, thread count, open file descriptors at regular intervals
# Useful for detecting leaks during long-running deployments
# (default: false)
enabled = true

# Monitoring interval in seconds
# How often to log resource statistics
# (default: 300 - 5 minutes)
interval = 300
```

### Using Resource Monitoring

#### Enable via Configuration

The simplest way is to set `enabled = true` in your `cowrie.cfg` as shown above.

#### Programmatic Control

You can also control monitoring programmatically:

```python
from cowrie.core.resource_monitor import start_monitoring, stop_monitoring

# Start monitoring
start_monitoring()

# Stop monitoring
stop_monitoring()
```

#### Getting Current Stats

To get current resource statistics without logging:

```python
from cowrie.core.resource_monitor import get_monitor

monitor = get_monitor()
stats = monitor.get_current_stats()

print(f"RSS Memory: {stats['rss_mb']:.2f} MB")
print(f"Threads: {stats['threads']}")
print(f"Open FDs: {stats['open_fds']}")
```

### Example Output

When enabled, you'll see periodic log entries like:

```
Resource Monitor - Uptime: 24.5h, RSS: 156.32MB, VMS: 892.41MB, 
Threads: 12, Open FDs: 45, Connections: 3, CPU: 2.3% (RSS Δ: +12.50MB, Threads Δ: +2)
```

This helps you:
- Detect memory leaks (increasing RSS over time)
- Monitor thread accumulation
- Track file descriptor usage
- Spot connection issues

## Security Best Practices

1. **Always enable sanitization logging** in production to track potential attack patterns
2. **Monitor sanitization logs** regularly for unusual patterns
3. **Enable resource monitoring** for long-running deployments (>24 hours)
4. **Review resource deltas** to catch leaks early
5. **Set appropriate command length limits** based on your LLM's token limits

## Backward Compatibility

Both features are:
- **Optional**: Sanitization is always active, but monitoring is off by default
- **Non-breaking**: Existing configurations continue to work
- **Low overhead**: Minimal performance impact

## Testing

The implementation includes comprehensive test coverage:
- 11 unit tests for sanitization
- 10 unit tests for resource monitoring
- All tests follow Cowrie conventions

Run tests with:
```bash
python -m unittest src.cowrie.test.test_sanitizer
python -m unittest src.cowrie.test.test_resource_monitor
```

## Dependencies

The resource monitor requires `psutil>=5.9.0`, which is added to `requirements.txt`.

Install with:
```bash
pip install -r requirements.txt
```
