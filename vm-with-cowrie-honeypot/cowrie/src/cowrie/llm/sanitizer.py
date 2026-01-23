# Copyright (c) 2024 Michel Oosterhof <michel@oosterhof.net>
# See the COPYRIGHT file for more information

"""
Input sanitization utilities for LLM prompt injection protection.

This module provides functions to sanitize user commands before sending them
to the LLM, preventing prompt injection attacks and protecting against
malicious input patterns.
"""

from __future__ import annotations

import re
from typing import Tuple

from twisted.python import log

from cowrie.core.config import CowrieConfig


# Common prompt injection patterns
INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above)\s+instructions?",
    r"ignore\s+your\s+\w+",  # ignore your instructions, programming, etc.
    r"disregard\s+(previous|all|above)\s+instructions?",
    r"disregard\s+all\s+\w+",  # disregard all rules, etc.
    r"forget\s+(previous|all|above)\s+instructions?",
    r"forget\s+your\s+\w+",  # forget your programming, etc.
    r"you\s+are\s+(now|a)\s+",
    r"new\s+instructions?:",
    r"system\s+prompt:",
    r"reset\s+context",
    r"your\s+new\s+role",
    r"act\s+as\s+",
    r"pretend\s+(you\s+are|to\s+be)",
]


def sanitize_command(command: str) -> Tuple[str, bool]:
    """
    Sanitize a command before sending it to the LLM.
    
    This function performs multiple sanitization steps:
    1. Removes ANSI escape sequences
    2. Checks for prompt injection patterns
    3. Limits command length
    4. Strips excessive whitespace
    
    Args:
        command: The raw command string from the user
        
    Returns:
        A tuple of (sanitized_command, was_modified) where was_modified
        indicates if any sanitization was performed
    """
    original = command
    modified = False
    
    # Get configuration options
    max_length = CowrieConfig.getint("llm", "max_command_length", fallback=1000)
    log_sanitization = CowrieConfig.getboolean(
        "llm", "log_sanitization", fallback=True
    )
    
    # Step 1: Remove ANSI escape sequences
    # Pattern matches ESC[ followed by any number of parameters and command char
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
    cleaned = ansi_pattern.sub('', command)
    if cleaned != command:
        modified = True
        if log_sanitization:
            log.msg(
                eventid="cowrie.llm.sanitizer.ansi_removed",
                format="Removed ANSI escape sequences from command"
            )
    
    # Step 2: Check for prompt injection patterns
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            # Replace the entire command with a safe version that preserves
            # the basic structure but removes injection content
            cleaned = _neutralize_injection(cleaned)
            modified = True
            if log_sanitization:
                log.msg(
                    eventid="cowrie.llm.sanitizer.injection_detected",
                    format="Detected potential prompt injection pattern: %(pattern)s",
                    pattern=pattern,
                    original_command=command
                )
            break
    
    # Step 3: Limit command length
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
        modified = True
        if log_sanitization:
            log.msg(
                eventid="cowrie.llm.sanitizer.length_limited",
                format="Command truncated from %(original)d to %(max)d characters",
                original=len(command),
                max=max_length
            )
    
    # Step 4: Strip excessive whitespace (normalize spaces)
    # Preserve single spaces but remove multiple consecutive spaces
    cleaned = ' '.join(cleaned.split())
    if cleaned != original and not modified:
        modified = True
    
    return cleaned, modified


def _neutralize_injection(command: str) -> str:
    """
    Neutralize a command containing prompt injection patterns.
    
    Instead of blocking entirely, we preserve the command structure but
    escape or remove the dangerous parts. This maintains the honeypot
    illusion while protecting the LLM.
    
    Args:
        command: Command with injection patterns
        
    Returns:
        Neutralized version of the command
    """
    # Replace common instruction words with safe alternatives
    neutralized = command
    
    replacements = {
        r'\bignore\b': 'show',
        r'\bdisregard\b': 'display',
        r'\bforget\b': 'remember',
        r'\breset\b': 'check',
        r'\bnew instructions\b': 'parameters',
        r'\bsystem prompt\b': 'system info',
        r'\byour role\b': 'the role',
        r'\bact as\b': 'show',
        r'\bpretend\b': 'display',
    }
    
    for pattern, replacement in replacements.items():
        neutralized = re.sub(pattern, replacement, neutralized, flags=re.IGNORECASE)
    
    return neutralized


def strip_ansi_sequences(text: str) -> str:
    """
    Strip ANSI escape sequences from text.
    
    This is a utility function that can be used independently
    of the main sanitization flow.
    
    Args:
        text: Text that may contain ANSI sequences
        
    Returns:
        Text with ANSI sequences removed
    """
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
    return ansi_pattern.sub('', text)


def is_safe_command(command: str) -> bool:
    """
    Quick check if a command appears safe (no obvious injection patterns).
    
    This is a fast pre-check that can be used before more expensive
    sanitization operations.
    
    Args:
        command: Command to check
        
    Returns:
        True if command appears safe, False if suspicious patterns detected
    """
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False
    return True
