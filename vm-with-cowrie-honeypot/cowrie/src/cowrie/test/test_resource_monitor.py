# Copyright (c) 2024 Michel Oosterhof <michel@oosterhof.net>
# See LICENSE for details.

"""
Tests for the resource monitor module.
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from cowrie.core.resource_monitor import ResourceMonitor, get_monitor


class ResourceMonitorTests(unittest.TestCase):
    """Test resource monitor functionality."""

    def test_monitor_initialization_disabled(self) -> None:
        """Test that monitor can be initialized in disabled state."""
        monitor = ResourceMonitor(enabled=False)
        self.assertFalse(monitor.enabled)
        self.assertIsNone(monitor.process)
    
    def test_monitor_initialization_enabled(self) -> None:
        """Test that monitor can be initialized in enabled state."""
        monitor = ResourceMonitor(enabled=True, interval=60)
        self.assertTrue(monitor.enabled)
        self.assertEqual(monitor.interval, 60)
        self.assertIsNotNone(monitor.process)
        self.assertIsNotNone(monitor.initial_stats)
    
    def test_gather_stats(self) -> None:
        """Test that stats gathering returns expected keys."""
        monitor = ResourceMonitor(enabled=True)
        stats = monitor._gather_stats()
        
        # Should have all expected keys
        expected_keys = ['rss_mb', 'vms_mb', 'threads', 'open_fds', 'connections', 'cpu_percent']
        for key in expected_keys:
            self.assertIn(key, stats)
        
        # Memory values should be positive
        self.assertGreater(stats['rss_mb'], 0)
        self.assertGreater(stats['vms_mb'], 0)
        
        # Thread count should be at least 1 (this thread)
        self.assertGreaterEqual(stats['threads'], 1)
    
    def test_get_current_stats(self) -> None:
        """Test the get_current_stats public method."""
        monitor = ResourceMonitor(enabled=True)
        stats = monitor.get_current_stats()
        
        self.assertIsInstance(stats, dict)
        self.assertIn('rss_mb', stats)
        self.assertIn('threads', stats)
    
    def test_start_disabled_monitor(self) -> None:
        """Test that starting a disabled monitor does nothing."""
        monitor = ResourceMonitor(enabled=False)
        monitor.start()
        
        # Should not have started a monitoring task
        self.assertIsNone(monitor.monitoring_task)
    
    def test_stop_not_started(self) -> None:
        """Test that stopping a non-started monitor is safe."""
        monitor = ResourceMonitor(enabled=True)
        monitor.stop()  # Should not raise an exception
        self.assertIsNone(monitor.monitoring_task)
    
    @patch('cowrie.core.resource_monitor.log')
    def test_log_resources(self, mock_log) -> None:
        """Test that resource logging calls log.msg."""
        monitor = ResourceMonitor(enabled=True)
        monitor._log_resources()
        
        # Should have logged something
        self.assertTrue(mock_log.msg.called)
        
        # Check that the log message contains expected info
        call_kwargs = mock_log.msg.call_args[1]
        self.assertIn('eventid', call_kwargs)
        self.assertEqual(call_kwargs['eventid'], 'cowrie.resource_monitor.stats')
        self.assertIn('rss', call_kwargs)
        self.assertIn('threads', call_kwargs)
    
    def test_global_instance(self) -> None:
        """Test that get_monitor returns a singleton."""
        monitor1 = get_monitor()
        monitor2 = get_monitor()
        
        # Should be the same instance
        self.assertIs(monitor1, monitor2)
    
    def test_stats_format(self) -> None:
        """Test that stats are in the expected format."""
        monitor = ResourceMonitor(enabled=True)
        stats = monitor._gather_stats()
        
        # Memory should be in MB (reasonable range)
        self.assertGreater(stats['rss_mb'], 0)
        self.assertLess(stats['rss_mb'], 100000)  # Less than 100GB
        
        # Threads should be a reasonable number
        self.assertGreater(stats['threads'], 0)
        self.assertLess(stats['threads'], 10000)
    
    def test_disabled_monitor_no_stats(self) -> None:
        """Test that disabled monitor returns empty stats."""
        monitor = ResourceMonitor(enabled=False)
        # Even if called, should handle gracefully
        if monitor.process is None:
            stats = monitor._gather_stats()
            self.assertEqual(stats, {})


if __name__ == "__main__":
    unittest.main()
