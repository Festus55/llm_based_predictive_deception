# Copyright (c) 2024 Michel Oosterhof <michel@oosterhof.net>
# See the COPYRIGHT file for more information

"""
Resource monitoring utilities for long-running Cowrie deployments.

This module provides periodic logging of system resource usage including
memory, threads, and open file handles. Useful for detecting leaks and
monitoring health during extended honeypot operations.
"""

from __future__ import annotations

import os
import psutil
import threading
import time
from typing import Optional

from twisted.internet import reactor, task
from twisted.python import log

from cowrie.core.config import CowrieConfig


class ResourceMonitor:
    """
    Monitor system resources and log periodically.
    
    Tracks:
    - Memory usage (RSS, VMS)
    - Thread count
    - Open file descriptors
    - Connection count (if available)
    
    Can be configured via cowrie.cfg [resource_monitor] section.
    """
    
    def __init__(self, interval: Optional[int] = None, enabled: Optional[bool] = None):
        """
        Initialize the resource monitor.
        
        Args:
            interval: Monitoring interval in seconds. If None, reads from config
            enabled: Whether monitoring is enabled. If None, reads from config
        """
        # Read configuration
        if enabled is None:
            self.enabled = CowrieConfig.getboolean(
                "resource_monitor", "enabled", fallback=False
            )
        else:
            self.enabled = enabled
            
        if interval is None:
            self.interval = CowrieConfig.getint(
                "resource_monitor", "interval", fallback=300  # 5 minutes default
            )
        else:
            self.interval = interval
        
        self.process: Optional[psutil.Process] = None
        self.monitoring_task: Optional[task.LoopingCall] = None
        self.start_time: float = time.time()
        self.initial_stats: Optional[dict] = None
        
        if self.enabled:
            try:
                self.process = psutil.Process(os.getpid())
                self.initial_stats = self._gather_stats()
            except Exception as e:
                log.err(f"Failed to initialize resource monitor: {e}")
                self.enabled = False
    
    def start(self) -> None:
        """Start periodic resource monitoring."""
        if not self.enabled:
            log.msg("Resource monitoring is disabled")
            return
        
        if self.monitoring_task is not None:
            log.msg("Resource monitoring already started")
            return
        
        log.msg(
            eventid="cowrie.resource_monitor.started",
            format="Starting resource monitoring with interval %(interval)d seconds",
            interval=self.interval
        )
        
        # Log initial state
        self._log_resources()
        
        # Start periodic monitoring
        self.monitoring_task = task.LoopingCall(self._log_resources)
        self.monitoring_task.start(self.interval)
    
    def stop(self) -> None:
        """Stop resource monitoring."""
        if self.monitoring_task is not None and self.monitoring_task.running:
            self.monitoring_task.stop()
            self.monitoring_task = None
            log.msg("Resource monitoring stopped")
    
    def _gather_stats(self) -> dict:
        """
        Gather current resource statistics.
        
        Returns:
            Dictionary with resource usage information
        """
        if self.process is None:
            return {}
        
        try:
            # Memory info
            mem_info = self.process.memory_info()
            
            # Thread count
            try:
                thread_count = self.process.num_threads()
            except (AttributeError, psutil.AccessDenied):
                thread_count = threading.active_count()
            
            # Open file descriptors
            try:
                if hasattr(self.process, 'num_fds'):
                    # Unix/Linux
                    open_fds = self.process.num_fds()
                else:
                    # Windows uses num_handles
                    open_fds = self.process.num_handles()
            except (AttributeError, psutil.AccessDenied):
                open_fds = -1
            
            # Connection count
            try:
                # Use net_connections() instead of deprecated connections()
                connections = len(self.process.net_connections())
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                connections = -1
            
            # CPU usage (percent)
            # Use interval=None for non-blocking call
            try:
                cpu_percent = self.process.cpu_percent(interval=None)
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                cpu_percent = -1
            
            stats = {
                'rss_mb': mem_info.rss / (1024 * 1024),  # Resident Set Size in MB
                'vms_mb': mem_info.vms / (1024 * 1024),  # Virtual Memory Size in MB
                'threads': thread_count,
                'open_fds': open_fds,
                'connections': connections,
                'cpu_percent': cpu_percent,
            }
            
            return stats
            
        except Exception as e:
            log.err(f"Error gathering resource stats: {e}")
            return {}
    
    def _log_resources(self) -> None:
        """Log current resource usage."""
        stats = self._gather_stats()
        
        if not stats:
            return
        
        uptime = time.time() - self.start_time
        uptime_hours = uptime / 3600
        
        # Calculate deltas if we have initial stats
        delta_info = ""
        if self.initial_stats:
            rss_delta = stats['rss_mb'] - self.initial_stats['rss_mb']
            threads_delta = stats['threads'] - self.initial_stats['threads']
            
            delta_info = f" (RSS Δ: {rss_delta:+.2f}MB, Threads Δ: {threads_delta:+d})"
        
        log.msg(
            eventid="cowrie.resource_monitor.stats",
            format="Resource Monitor - Uptime: %(uptime).1fh, "
                   "RSS: %(rss).2fMB, VMS: %(vms).2fMB, "
                   "Threads: %(threads)d, Open FDs: %(fds)d, "
                   "Connections: %(conns)d, CPU: %(cpu).1f%%%(delta)s",
            uptime=uptime_hours,
            rss=stats['rss_mb'],
            vms=stats['vms_mb'],
            threads=stats['threads'],
            fds=stats['open_fds'],
            conns=stats['connections'],
            cpu=stats['cpu_percent'],
            delta=delta_info
        )
    
    def get_current_stats(self) -> dict:
        """
        Get current resource statistics without logging.
        
        Returns:
            Dictionary with current resource usage
        """
        return self._gather_stats()


# Global instance for easy access
_monitor_instance: Optional[ResourceMonitor] = None


def get_monitor() -> ResourceMonitor:
    """
    Get the global ResourceMonitor instance.
    
    Creates one if it doesn't exist yet.
    
    Returns:
        The global ResourceMonitor instance
    """
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = ResourceMonitor()
    return _monitor_instance


def start_monitoring() -> None:
    """
    Start resource monitoring using the global instance.
    
    This is a convenience function that can be called from
    application startup code.
    """
    monitor = get_monitor()
    monitor.start()


def stop_monitoring() -> None:
    """
    Stop resource monitoring using the global instance.
    """
    monitor = get_monitor()
    monitor.stop()
