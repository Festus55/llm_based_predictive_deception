# Copyright (c) 2009-2014 Upi Tamminen <desaster@gmail.com>
# See the COPYRIGHT file for more information


from __future__ import annotations

import time

import copy
import os
import re
import shlex

from typing import Any

from twisted.internet import error
from twisted.python import failure, log
from twisted.python.compat import iterbytes

#%+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# custom imports 
import treq
import json
from twisted.internet import defer, reactor

from cowrie.core.config import CowrieConfig
from cowrie.shell import fs
from cowrie.shell.parser import CommandParser
from cowrie.shell.pipe import PipeProtocol
import tempfile

import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import pikepdf

import random
import time

import signal
from contextlib import contextmanager

# NEVER USE import requests IN A TWISTED ENV

# global static vars
# LLM API URL
URL = "http://192.168.122.1:8000/v1/chat/completions"

# canarytoken api url
API_URL = "http://192.168.122.1:8082/generate"

# canary server external ip
WEBHOOK_IP = "35.208.122.89"

#replace r"{{command_history}}" with the actual cmd hist
TEMPLATE_PROMPT= r"Role: Predictive Honeypot. Analyze SSH. Predict 3 unique high-value Canarytoken trap commands. Sort by probability.\n\nSSH observed command:\n{{command_history}}\n\nReturn exactly 3 items as a JSON array of objects. Each object must have keys: predicted_cmd, trap_path, trap_template. Sort most likely first. Output only valid JSON (no markdown, no backticks, no extra text)."

CMD_BETWEEN_LLM_CALLS=2 # one call every three commands

#average delay = 2.1 s, covers approx 1 call every 3
BASE_DELAY= 1.7
MAX_JITTER= 0.8

#%++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

# Pre-compiled regexes for environment variable expansion
_ENV_BRACE_RE = re.compile(r"^\${([_a-zA-Z0-9]+)}$")
_ENV_SIMPLE_RE = re.compile(r"^\$([_a-zA-Z0-9]+)$")


class HoneyPotShell:
    def __init__(
        self, protocol: Any, interactive: bool = True, redirect: bool = False
    ) -> None:
        self.protocol = protocol
        self.interactive: bool = interactive
        self.redirect: bool = redirect  # to support output redirection
        self.cmdpending: list[list[str]] = []
        self.environ: dict[str, str] = copy.copy(protocol.environ)
        if hasattr(protocol.user, "windowSize"):
            self.environ["COLUMNS"] = str(protocol.user.windowSize[1])
            self.environ["LINES"] = str(protocol.user.windowSize[0])
        self.lexer: shlex.shlex | None = None
        self.parser = CommandParser()

        #%++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        #command history initialisation
        self.cmd_history=""
        
        # http file subs queue init
        self.protocol.ai_prediction_queue = []

        # session id readability initialisation
        term = getattr(self.protocol, "terminal", None)
        self.protocol.sess_id = getattr(getattr(getattr(term, "transport", None), "session", None), "id", None)
         
        #counter init
        self.call_counter=1 #setting it to 1 so that we try the inference at the second input line and the every CMD_BETWEEN_LLM_CALLS+1
        #template loading
        with open("/home/cowrie/cowrie/src/cowrie/shell/templates/template.json", "r", encoding="utf-8") as f:  # relative file path to honeypot.py, which is inside of src/cowrie/shell
            text = f.read().strip()
        if not text:
            print("CRITICAL ERROR: JSON template file not present into ./templates/template.json")
        else:
            try:
                templates_json = json.loads(text)
            except json.JSONDecodeError:
                print("CRITICAL ERROR: impossible template JSON conversion")
            # quick accessible lookup table through tags
            self.templates = {}
            self.templates = {item["tag"]: item for item in templates_json}

            # user information loading, necessary to ensure coherence while 
            # assigning file ownership
            self.user_db_cache = {} 
            self._load_passwd_database()

            # leak files lookup table initialisation
            self.lookup_files={}
            self.lookup_files: dict[str, tuple[str, str]]

        #%++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        # this is the first prompt after starting
        self.showPrompt()


    #%++++++++++++++++++++++++++++++++++++++++++++++++++++
    @defer.inlineCallbacks
    def lineReceived(self, line: str) -> None:
        """
        Intercepts the command, consults the AI, mutates the FS, 
        THEN executes the original command.
        """
        line = line.strip()
        if not line:
            self.showPrompt()
            return
        # update command history (necessary for prediction) 
        self.cmd_history = f"{self.cmd_history}, {line}" if self.cmd_history else line
    
        try:
            d = self.consult_orchestrator()
            if isinstance(d, defer.Deferred):
                d.addErrback(lambda f: log.msg(f"Ignored AI Error: {f}"))
        except Exception as e:
            log.msg(f"Ignored AI setup error: {e}")
        #injected delay
        delay = BASE_DELAY + random.uniform(0, MAX_JITTER)
        d_delay = defer.Deferred()
        reactor.callLater(delay, d_delay.callback, None)
        yield d_delay

        # Check if session survived the delay fixing an error that occurred when attacker disconnected during the delay
        if not self._session_alive():
            log.msg("Session closed during AI delay, aborting command execution")
            return

        # Resume Standard Execution
        self._execute_standard_command(line)
   

    #%+++ Renamed to _execute_standard_command (called by consult_orchestrator)
    def _execute_standard_command(self, line: str) -> None:
        #%++++++++++++++++++++++++++++++++++++++++++++++++++++
        # hook section: here there will be the control of the input lines to implement the
        # leak txt file and the file substitution traps AFTER the orchestrator launched the 
        # LLM API call asynchronously
        self.check_leak_file(line)
        #%++++++++++++++++++++++++++++++++++++++++++++++++++++

        log.msg(eventid="cowrie.command.input", input=line, format="CMD: %(input)s")
        self.lexer = shlex.shlex(instream=line, punctuation_chars=True, posix=True)
        # Special characters that are not in the default lexer
        self.lexer.wordchars += "@%{}=$:+^,()`"

        tokens: list[str] = []

        while True:
            try:
                tokkie: str | None = self.lexer.get_token()
                # log.msg("tok: %s" % (repr(tok)))

                if tokkie is None:  # self.lexer.eof put None for mypy
                    if tokens:
                        self.cmdpending.append(tokens)
                    break
                else:
                    tok: str = tokkie

                # For now, treat && and || same as ;, just execute without checking return code
                if tok == "&&" or tok == "||":
                    if tokens:
                        self.cmdpending.append(tokens)
                        tokens = []
                        continue
                    else:
                        self.protocol.terminal.write(
                            f"-bash: syntax error near unexpected token `{tok}'\n".encode()
                        )
                        break
                elif tok == ";":
                    if tokens:
                        self.cmdpending.append(tokens)
                        tokens = []
                    continue
                elif tok == "$?":
                    tok = "0"
                elif tok == "(" or (tok.startswith("(") and not tok.startswith("$(")):
                    # Parentheses can only appear at the start of a command, not in the middle
                    if tokens:
                        # Parentheses in the middle of a command line is a syntax error
                        self.protocol.terminal.write(
                            f"-bash: syntax error near unexpected token `{tok}'\\n".encode()
                        )
                        break
                    if tok == "(":
                        self.do_subshell_execution_from_lexer()
                    else:
                        self.do_subshell_execution(tok)
                    continue
                elif "$(" in tok or "`" in tok:
                    tok = self.do_command_substitution(tok)
                elif tok.startswith("${"):
                    envSearch = _ENV_BRACE_RE.search(tok)
                    if envSearch is not None:
                        envMatch = envSearch.group(1)
                        if envMatch in self.environ:
                            tok = self.environ[envMatch]
                        else:
                            continue
                elif tok.startswith("$"):
                    envSearch = _ENV_SIMPLE_RE.search(tok)
                    if envSearch is not None:
                        envMatch = envSearch.group(1)
                        if envMatch in self.environ:
                            tok = self.environ[envMatch]
                        else:
                            continue

                tokens.append(tok)
            except Exception as e:
                self.protocol.terminal.write(
                    b"-bash: syntax error: unexpected end of file\n"
                )
                # Could run runCommand here, but i'll just clear the list instead
                log.msg(f"exception: {e}")
                self.cmdpending = []
                self.showPrompt()
                return

        if self.cmdpending:
            # Coalesce fd redirection tokens so we don't treat `2` as a command
            self.cmdpending = [
                self.parser.merge_redirection_tokens(tokens)
                for tokens in self.cmdpending
            ]
            # if we have a complete command, go and run it
            self.runCommand()
        else:
            # if there's no command, display a prompt again
            self.showPrompt()
   
    def _session_alive(self) -> bool:
        return bool(getattr(self.protocol, "fs", None)) and bool(getattr(self.protocol, "terminal", None))
    
    @defer.inlineCallbacks
    def consult_orchestrator(self):
        if not self._session_alive():
            return
        if self.call_counter == 0:
            try:
                # LLM API call 
                message = TEMPLATE_PROMPT.replace(r"{{command_history}}", self.cmd_history)

                payload = {
                    "model": "honeypot",
                    "messages": [{"role": "user", "content": message}],
                    "max_tokens": 450,
                    "temperature": 1.0,
                    "top_p": 0.95,
                    "top_k": 64,
                } #recommended temperature setup for gemma
                response = yield treq.post(URL, json=payload, timeout=600)
                data = yield response.json()
                content = data["choices"][0]["message"]["content"]
                predictions = yield json.loads(content)

                
                # Task assignement (Fan-Out)
                tasks = []
                for pred in predictions:
                    d = self.apply_strategy(pred)
                    if isinstance(d, defer.Deferred):
                        tasks.append(d)

                # Fan-In
                if tasks:
                    yield defer.gatherResults(tasks, consumeErrors=True)
                    
            except Exception as e:
                log.msg(f"AI/Strategy Error: {e}") 
            self.call_counter= CMD_BETWEEN_LLM_CALLS  
        else: 
            self.call_counter= self.call_counter - 1

    #%++++++++++++++++++++++++++++++++++++++++++++++++++++++

    def do_subshell_execution_from_lexer(self) -> None:
        """
        Execute a subshell command reading tokens from the lexer until matching closing parenthesis.
        Output goes directly to the terminal.
        """
        cmd_tokens = []
        opening_count = 1
        closing_count = 0

        while opening_count > closing_count:
            if self.lexer is None:
                break
            tok = self.lexer.get_token()
            if tok is None:
                break

            if tok == ")":
                closing_count += 1
                if opening_count == closing_count:
                    break
                else:
                    cmd_tokens.append(tok)
            elif tok == "(":
                opening_count += 1
                cmd_tokens.append(tok)
            else:
                cmd_tokens.append(tok)

        # execute the command and print to terminal
        cmd_str = " ".join(cmd_tokens)
        self.protocol.terminal.write(self.run_subshell_command(f"({cmd_str})").encode())

    def do_subshell_execution(self, start_tok: str) -> None:
        """
        Execute a subshell command (command) without output substitution.
        Output goes directly to the terminal.
        """
        if start_tok[0] == "(":
            cmd_expr = start_tok
            pos = 1
            opening_count = 1
            closing_count = 0

            # parse the remaining tokens to find the matching closing parenthesis
            while opening_count > closing_count:
                if cmd_expr[pos] == ")":
                    closing_count += 1
                    if opening_count == closing_count:
                        # execute the command in () and print to terminal
                        self.protocol.terminal.write(
                            self.run_subshell_command(cmd_expr[: pos + 1]).encode()
                        )
                        break
                    else:
                        pos += 1
                elif cmd_expr[pos] == "(":
                    opening_count += 1
                    pos += 1
                else:
                    if opening_count > closing_count and pos == len(cmd_expr) - 1:
                        if self.lexer:
                            tokkie = self.lexer.get_token()
                            if tokkie is None:  # self.lexer.eof put None for mypy
                                break
                            else:
                                cmd_expr = cmd_expr + " " + tokkie
                    pos += 1

    def do_command_substitution(self, start_tok: str) -> str:
        """
        Perform command substitution, replacing $(cmd) or `cmd` with output.
        """
        result = ""
        if start_tok[0] == "(":
            cmd_expr = start_tok
            pos = 1
        elif "$(" in start_tok:
            dollar_pos = start_tok.index("$(")
            result = start_tok[:dollar_pos]
            cmd_expr = start_tok[dollar_pos:]
            pos = 2
        elif "`" in start_tok:
            backtick_pos = start_tok.index("`")
            result = start_tok[:backtick_pos]
            cmd_expr = start_tok[backtick_pos:]
            pos = 1
        else:
            log.msg(f"failed command substitution: {start_tok}")
            return start_tok

        opening_count = 1
        closing_count = 0

        while opening_count > closing_count:
            if cmd_expr[pos] in (")", "`"):
                closing_count += 1
                if opening_count == closing_count:
                    if cmd_expr[0] == "(":
                        self.protocol.terminal.write(
                            self.run_subshell_command(cmd_expr[: pos + 1]).encode()
                        )
                    else:
                        result += self.run_subshell_command(cmd_expr[: pos + 1])

                    if pos < len(cmd_expr) - 1:
                        remainder = cmd_expr[pos + 1 :]
                        if "$(" in remainder or "`" in remainder:
                            result = self.do_command_substitution(result + remainder)
                        else:
                            result += remainder
                else:
                    pos += 1
            elif cmd_expr[pos : pos + 2] == "$(":
                opening_count += 1
                pos += 2
            else:
                if opening_count > closing_count and pos == len(cmd_expr) - 1:
                    if self.lexer:
                        tokkie = self.lexer.get_token()
                        if tokkie is None:
                            break
                        else:
                            cmd_expr = cmd_expr + " " + tokkie
                pos += 1

        return result

    def run_subshell_command(self, cmd_expr: str) -> str:
        # extract the command from $(...) or `...` or (...) expression
        if cmd_expr.startswith("$("):
            cmd = cmd_expr[2:-1]
        else:
            cmd = cmd_expr[1:-1]

        # For subshells with multiple commands, we need to capture all output
        # Create a custom output accumulator
        if cmd_expr.startswith("("):
            return self._execute_subshell_with_full_output(cmd)
        else:
            # Command substitution - use existing method
            return self._execute_command_substitution(cmd)

    def _execute_subshell_with_full_output(self, cmd: str) -> str:
        """Execute subshell commands and capture ALL output, not just the last command."""
        # Split commands by separators and execute each one
        lexer = shlex.shlex(instream=cmd, punctuation_chars=True, posix=True)
        lexer.wordchars += "@%{}=$:+^,()`"

        accumulated_output = ""
        current_cmd_tokens: list[str] = []

        while True:
            tok = lexer.get_token()
            if tok is None:
                # Process final command
                if current_cmd_tokens:
                    cmd_str = " ".join(current_cmd_tokens)
                    output = self._execute_single_command_with_redirect(cmd_str)
                    accumulated_output += output
                break
            elif tok in (";", "&&", "||"):
                # Process current command and start new one
                if current_cmd_tokens:
                    cmd_str = " ".join(current_cmd_tokens)
                    output = self._execute_single_command_with_redirect(cmd_str)
                    accumulated_output += output
                    current_cmd_tokens = []
                # Note: We're ignoring && and || conditional logic for now
            else:
                current_cmd_tokens.append(tok)

        return accumulated_output

    def _execute_command_substitution(self, cmd: str) -> str:
        """Execute command substitution - should capture all output."""
        # Command substitution should also capture all output from multiple commands
        output = self._execute_subshell_with_full_output(cmd)
        # trailing newlines are stripped for command substitution
        return output.rstrip("\n")

    def _execute_single_command_with_redirect(self, cmd: str) -> str:
        """Execute a single command and return its output."""
        # instantiate new shell with redirect output
        self.protocol.cmdstack.append(
            HoneyPotShell(self.protocol, interactive=False, redirect=True)
        )
        # call lineReceived method that indicates that we have some commands to parse
        self.protocol.cmdstack[-1].lineReceived(cmd)
        # and remove the shell
        res = self.protocol.cmdstack.pop()

        try:
            output: str = res.protocol.pp.redirected_data.decode()
        except AttributeError:
            return ""
        else:
            return output

    def runCommand(self):
        pp = None

        def runOrPrompt() -> None:
            if self.cmdpending:
                self.runCommand()
            else:
                self.showPrompt()

        if not self.cmdpending:
            if self.protocol.pp.next_command is None:  # command dont have pipe(s)
                if self.interactive:
                    self.showPrompt()
                else:
                    # when commands passed to a shell via PIPE, we spawn a HoneyPotShell in none interactive mode
                    # if there are another shells on stack (cmdstack), let's just exit our new shell
                    # else close connection
                    if len(self.protocol.cmdstack) == 1:
                        ret = failure.Failure(error.ProcessDone(status=""))
                        self.protocol.terminal.transport.processEnded(ret)
                    else:
                        return
            else:
                pass  # command with pipes
            return

        cmdAndArgs = self.cmdpending.pop(0)

        # Probably no reason to be this comprehensive for just PATH...
        environ = copy.copy(self.environ)
        cmd_tokens: list[str] = []
        cmd_array: list[dict[str, Any]] = []
        while cmdAndArgs:
            piece = cmdAndArgs.pop(0)
            if piece.count("="):
                key, val = piece.split("=", 1)
                environ[key] = val
                continue
            cmd_tokens = [piece, *cmdAndArgs]
            break

        if not cmd_tokens:
            runOrPrompt()
            return

        pipe_indices = [i for i, x in enumerate(cmd_tokens) if x == "|"]
        multipleCmdArgs: list[list[str]] = []
        pipe_indices.append(len(cmd_tokens))
        start = 0

        # Gather all arguments with pipes

        for _index, pipe_indice in enumerate(pipe_indices):
            multipleCmdArgs.append(cmd_tokens[start:pipe_indice])
            start = pipe_indice + 1

        first_args, first_ops = self.parser.parse_redirections(multipleCmdArgs.pop(0))
        if not first_args:
            if first_ops:
                # Handle redirection without command (e.g. > file)
                pp = PipeProtocol(
                    self.protocol,
                    None,
                    [],
                    None,
                    None,
                    self.redirect,
                    first_ops,
                )
                # This triggers _setup_redirections which creates files
            runOrPrompt()
            return

        cmd_array.append(
            {
                "command": first_args.pop(0),
                "rargs": first_args,
                "redirects": first_ops,
            }
        )

        for cmd_args in multipleCmdArgs:
            args, ops = self.parser.parse_redirections(cmd_args)
            if not args:
                continue
            cmd_array.append(
                {
                    "command": args.pop(0),
                    "rargs": args,
                    "redirects": ops,
                }
            )

        lastpp = None
        for index, cmd in reversed(list(enumerate(cmd_array))):
            #%++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
            if cmd["command"].endswith(('.sh', '.bash')) or self.isbash(cmd["command"]):
                
                script = cmd["command"]
                cmd["rargs"]= [script, *cmd["rargs"]]
                cmd["command"]="bash"
                log.msg(f"found runnable bash custom script {script}, bash execution {cmd['command']} {cmd['rargs']}...")
            #%++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
            cmdclass = self.protocol.getCommand(
                cmd["command"], environ["PATH"].split(":")
            )
            if cmdclass:
                log.msg(
                    input=cmd["command"] + " " + " ".join(cmd["rargs"]),
                    format="Command found: %(input)s",
                )
                if index == len(cmd_array) - 1:
                    lastpp = PipeProtocol(
                        self.protocol,
                        cmdclass,
                        cmd["rargs"],
                        None,
                        None,
                        self.redirect,
                        cmd.get("redirects", []),
                    )
                    pp = lastpp
                else:
                    pp = PipeProtocol(
                        self.protocol,
                        cmdclass,
                        cmd["rargs"],
                        None,
                        lastpp,
                        self.redirect,
                        cmd.get("redirects", []),
                    )
                    lastpp = pp
            else:
                log.msg(
                    eventid="cowrie.command.failed",
                    input=cmd["command"] + " " + " ".join(cmd["rargs"]),
                    format="Command not found: %(input)s",
                )
                message = "-bash: {}: command not found\n".format(
                    cmd["command"]
                ).encode("utf8")
                redirects = cmd.get("redirects", [])
                if redirects:
                    temp_pp = PipeProtocol(
                        self.protocol,
                        None,
                        [],
                        None,
                        None,
                        self.redirect,
                        redirects,
                    )
                    temp_pp.errReceived(message)
                    for real_path, virtual_path in temp_pp.redirect_real_files:
                        self.protocol.terminal.redirFiles.add((real_path, virtual_path))
                else:
                    self.protocol.terminal.write(message)

                # Import here to avoid circular dependency with protocol module
                from cowrie.shell import protocol

                if (
                    isinstance(self.protocol, protocol.HoneyPotExecProtocol)
                    and not self.cmdpending
                ):
                    exit_status = failure.Failure(error.ProcessDone(status=""))
                    self.protocol.terminal.transport.processEnded(exit_status)

                runOrPrompt()
                pp = None  # Got a error. Don't run any piped commands
                break
        if pp and getattr(pp, "has_redirection_error", False):
            runOrPrompt()
            return

        if pp:
            self.protocol.call_command(pp, cmdclass, *cmd_array[0]["rargs"])

    def resume(self) -> None:
        if self.interactive:
            self.protocol.setInsertMode()
        self.runCommand()

    def showPrompt(self) -> None:
        if not self.interactive:
            return

        prompt = ""
        if CowrieConfig.has_option("honeypot", "prompt"):
            prompt = CowrieConfig.get("honeypot", "prompt")
            prompt += " "
        else:
            cwd = self.protocol.cwd
            homelen = len(self.protocol.user.avatar.home)
            if cwd == self.protocol.user.avatar.home:
                cwd = "~"
            elif (
                len(cwd) > (homelen + 1)
                and cwd[: (homelen + 1)] == self.protocol.user.avatar.home + "/"
            ):
                cwd = "~" + cwd[homelen:]

            # Example: [root@svr03 ~]#   (More of a "CentOS" feel)
            # Example: root@svr03:~#     (More of a "Debian" feel)
            prompt = f"{self.protocol.user.username}@{self.protocol.hostname}:{cwd}"
            if not self.protocol.user.uid:
                prompt += "# "  # "Root" user
            else:
                prompt += "$ "  # "Non-Root" user

        self.protocol.terminal.write(prompt.encode("ascii"))
        self.protocol.ps = (prompt.encode("ascii"), b"> ")

    def eofReceived(self) -> None:
        """
        this should probably not go through ctrl-d, but use processprotocol to close stdin
        """
        log.msg("received eof, sending ctrl-d to command")
        if self.protocol.cmdstack:
            self.protocol.cmdstack[-1].handle_CTRL_D()

    def handle_CTRL_C(self) -> None:
        self.protocol.lineBuffer = []
        self.protocol.lineBufferIndex = 0
        self.protocol.terminal.write(b"\n")
        self.showPrompt()

    def handle_CTRL_D(self) -> None:
        log.msg("Received CTRL-D, exiting..")
        status = failure.Failure(error.ProcessDone(status=""))
        self.protocol.terminal.transport.processEnded(status)

    def handle_TAB(self) -> None:
        """
        lineBuffer is an array of bytes
        """
        if not self.protocol.lineBuffer:
            return

        line: bytes = b"".join(self.protocol.lineBuffer)
        if line[-1:] == b" ":
            clue = ""
        else:
            clue = line.split()[-1].decode("utf8")

        # clue now contains the string to complete or is empty.
        # line contains the buffer as bytes
        basedir = os.path.dirname(clue)
        if basedir and basedir[-1] != "/":
            basedir += "/"

        if not basedir:
            tmppath = self.protocol.cwd
        else:
            tmppath = basedir

        try:
            r = self.protocol.fs.resolve_path(tmppath, self.protocol.cwd)
        except Exception:
            return

        if not self.protocol.fs.exists(r):
            return

        files = []
        for x in self.protocol.fs.get_path(r):
            if clue == "":
                files.append(x)
                continue
            if not x[fs.A_NAME].startswith(os.path.basename(clue)):
                continue
            files.append(x)

        if not files:
            return

        # Clear early so we can call showPrompt if needed
        for _i in range(self.protocol.lineBufferIndex):
            self.protocol.terminal.cursorBackward()
            self.protocol.terminal.deleteCharacter()

        newbuf = ""
        if len(files) == 1:
            newbuf = " ".join(
                [*line.decode("utf8").split()[:-1], f"{basedir}{files[0][fs.A_NAME]}"]
            )
            if files[0][fs.A_TYPE] == fs.T_DIR:
                newbuf += "/"
            else:
                newbuf += " "
            newbyt = newbuf.encode("utf8")
        else:
            if os.path.basename(clue):
                prefix = os.path.commonprefix([x[fs.A_NAME] for x in files])
            else:
                prefix = ""
            first = line.decode("utf8").split(" ")[:-1]
            newbuf = " ".join([*first, f"{basedir}{prefix}"])
            newbyt = newbuf.encode("utf8")
            if newbyt == b"".join(self.protocol.lineBuffer):
                self.protocol.terminal.write(b"\n")
                maxlen = max(len(x[fs.A_NAME]) for x in files) + 1
                perline = int(self.protocol.user.windowSize[1] / (maxlen + 1))
                count = 0
                for file in files:
                    if count == perline:
                        count = 0
                        self.protocol.terminal.write(b"\n")
                    self.protocol.terminal.write(
                        file[fs.A_NAME].ljust(maxlen).encode("utf8")
                    )
                    count += 1
                self.protocol.terminal.write(b"\n")
                self.showPrompt()

        self.protocol.lineBuffer = [y for x, y in enumerate(iterbytes(newbyt))]
        self.protocol.lineBufferIndex = len(self.protocol.lineBuffer)
        self.protocol.terminal.write(newbyt)


    #%++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    # custom functions
    def apply_strategy(self, prediction):
        d = defer.Deferred()
        tag=prediction["trap_template"]
        match tag:
            case t if re.match(r'^(AWS|K8S|VPN|TRAP|LURE|LEAK)_', t):
                content = self.get_template(tag)
                match tag:
                    case t if re.match(r'^AWS_',t):
                        # aws token
                        self.trap_aws(prediction, content)
                    case t if re.match(r'^K8S_',t):
                        # Kubeconfig token
                        self.trap_kubernetes(prediction, content)
                    case t if re.match(r'^VPN_',t):
                        # wireguard token
                        self.trap_wireguard(prediction, content)
                    case t if re.match(r'^TRAP_',t):
                        # HTTP token trap
                        self.trap_http(prediction, content)
                    case t if re.match(r'^LURE_',t):
                        # txt trap, log controller
                        self.trap_pdf(prediction, content)
                    case t if re.match(r'^LEAK_',t):
                        # PDF token
                        self.trap_leak_file(prediction, content)
            case "FILE_SUBSTITUTION_HTTP":
                # File substitution trap
                self.trap_file_subs(prediction)
            case "NO_OP": 
                print("No operation needed")
            case _ :
                print("Error: invalid trap template")
                print(json.dumps(prediction, indent=2))
        try:
            # LOGIC: Resolve strategy_name to specific FS changes
            
            
            # Artificial Delay (if specific to strategy)
            # reactor.callLater(0.1, d.callback, None)
            d.callback(None) # Signal done
        except Exception as e:
            d.errback(e)
            
        return d
    def get_template(self, tag):
        templ = self.templates.get(tag)
        return templ["content"]

    @defer.inlineCallbacks
    def trap_aws(self, prediction, content): 
        log.msg(f"generating aws_keys canary token at {prediction['trap_path']}...")
        response = yield self.canary_request("aws_keys", memo=f"AWS Trap: {prediction['trap_path']}") 
        if not response:
            log.msg("Failed to get AWS canary.")
            return
        if isinstance(response, list):
            response = response[0]

        access_key = response.get("aws_access_key_id", "")
        secret_key = response.get("aws_secret_access_key", "")

        if not access_key or not secret_key:
            log.msg("Specific trap type: AWS Credentials - Missing keys in response")
            return

        final_content = content.replace(r"{{AWS_ACCESS_KEY_ID}}", access_key)\
                                .replace(r"{{AWS_SECRET_ACCESS_KEY}}", secret_key)

        target_path = prediction.get("trap_path", "/home/root/.aws/credentials")
        self._inject_file_into_fs(target_path, final_content.encode('utf-8'))

    @defer.inlineCallbacks
    def trap_kubernetes(self, prediction, content):
        import base64
        log.msg(f"generating Kubernetes canary token at {prediction['trap_path']}...")
        response = yield self.canary_request("kubeconfig",memo=f"Kubernetes Trap: {prediction['trap_path']}")
        if not response:
            log.msg("Specific trap type: Kubeconfig - No response")
            return
            
        if isinstance(response, list):
            response = response[0]
            
        encoded_kubeconfig = response.get("kubeconfig")
        if not encoded_kubeconfig:
            log.msg("Specific trap type: Kubeconfig - No kubeconfig data in response")
            return
            
        try:
            decoded_kubeconfig_bytes = base64.b64decode(encoded_kubeconfig)
            decoded_kubeconfig_str = decoded_kubeconfig_bytes.decode('utf-8')
            
            final_content = content.replace(r"{{KUBECONFIG_CONTENT}}", decoded_kubeconfig_str)
            
            target_path = prediction.get("trap_path", "/home/root/.kube/config")
            self._inject_file_into_fs(target_path, final_content.encode('utf-8'))
        except Exception as e:
            log.msg(f"Error decoding kubeconfig or injecting: {e}")

    @defer.inlineCallbacks
    def trap_wireguard(self, prediction, content):
        import shlex
        log.msg(f"generating wireguard canary token at {prediction['trap_path']}...")
        response = yield self.canary_request("wireguard",memo=f"Wireguard Trap: {prediction['trap_path']}")
        if not response:
            log.msg("Specific trap type: Wireguard VPN token - No response")
            return

        if isinstance(response, list):
            response = response[0]
        
        #try content hydratation
        wg_conf = response.get("wg_conf")
        if not wg_conf:
            log.msg("No wg_conf in response")
            return

        tokens= shlex.split(wg_conf)
        final_content = wg_conf #default fallback on canarytoken result 
        try:
            # Extract with safety checks
            priv_idx = tokens.index("PrivateKey") + 2
            pub_idx = tokens.index("PublicKey") + 2
            ep_idx = tokens.index("Endpoint") + 2
            addr_idx = tokens.index("Address") + 2
            
            # Bounds check
            if all(0 <= i < len(tokens) for i in [priv_idx, pub_idx, ep_idx, addr_idx]):
                priv_k = tokens[priv_idx]
                pub_k = tokens[pub_idx]
                ep = tokens[ep_idx]
                addr = tokens[addr_idx]
                
                final_content = (content
                    .replace(r"{{WIREGUARD_PRIVATE_KEY}}", priv_k)
                    .replace(r"{{WIREGUARD_PUBLIC_KEY}}", pub_k)
                    .replace(r"{{WIREGUARD_ENDPOINT}}", ep)
                    .replace(r"{{WIREGUARD_ADDRESS}}", addr))
                log.msg(f"Wireguard tokens extracted: {len(tokens)} total")
            else:
                log.msg("Wireguard: Token indices out of bounds")
                
        except ValueError as e:
            log.msg(f"Wireguard parsing failed ({e}), using raw wg_conf")
    
        # File injection
        target_path = prediction.get("trap_path", "/etc/wireguard/wg0.conf")
        self._inject_file_into_fs(target_path, final_content.encode('utf-8'))
    

    @defer.inlineCallbacks
    def trap_http(self, prediction, content):
        log.msg(f"generating web canary token at {prediction['trap_path']}...")
        response = yield self.canary_request("web",memo=f"Web Trap: {prediction['trap_path']}")
        if not response:
            log.msg("Specific trap type: HTTP simple call - No response")
            return

        if isinstance(response, list):
            response = response[0]

        url = response.get("token_url", "")
        if url:
            content = content.replace(r"{{HTTP_CANARY_URL}}", url)

        target_path = prediction.get("trap_path", "/var/www/html/config.php")
        self._inject_file_into_fs(target_path, content.encode('utf-8'))
    
    @defer.inlineCallbacks
    def trap_pdf(self, prediction, content):
        log.msg(f"generating adobe_pdf canary token at {prediction['trap_path']}...") 
        response = yield self.canary_request("adobe_pdf",memo=f"Adobe PDF Trap: {prediction['trap_path']}")
        if not response:
            log.msg("Specific trap type: Adobe PDF - No response")
            return

        if isinstance(response, list):
            response = response[0]

        token_url = response.get("token_url")
        token = response.get("token")
        if not token_url:
            log.msg("Specific trap type: Adobe PDF - No token URL")
            return

        # pdf local creation
        packet = io.BytesIO()
        # Create a new PDF with Reportlab
        can = canvas.Canvas(packet, pagesize=letter)
        # Set font and draw text
        text_object = can.beginText(40, 750) # Start near top-left
        text_object.setFont("Helvetica", 12)
        
        # content might be a list or string
        lines = content.split('\n') if isinstance(content, str) else content

        for line in lines:
            text_object.textLine(line)
        
        can.drawText(text_object)
        can.save()

        # Move to the beginning of the StringIO buffer
        packet.seek(0)

        try:
            # open the PDF we just created with pikepdf to inject the token
            # pikepdf modifies the internal structure (the "OpenAction")
            pdf = pikepdf.Pdf.open(packet)
            pdf.Root.OpenAction = pikepdf.Dictionary(
                S=pikepdf.Name.URI,
                URI=token_url
            )

            # Save modified PDF to a new memory buffer
            out_stream = io.BytesIO()
            pdf.save(out_stream)
            pdf_bytes = out_stream.getvalue()

            # Inject into Cowrie FS
            filename = f"confidential_{token}.pdf" if token else "confidential.pdf"
            target_path = prediction.get("trap_path", f"/home/root/Documents/{filename}")
            self._inject_file_into_fs(target_path, pdf_bytes)

        except Exception as e:
            log.msg(f"PDF Gen Error: {e}")


    @defer.inlineCallbacks
    def trap_leak_file(self, prediction, content):
        # canary creation request
        transport = getattr(self.protocol.terminal, 'transport', None)
        attacker_ip = get_attacker_ip(transport)

        log.msg(f"Leak file from {attacker_ip}")
        log.msg(f"generating leak file trap at {prediction['trap_path']}...") 
        target_path = prediction.get("trap_path", "/tmp/sensitive.data")
        
        response = yield self.canary_request("web", memo=f"Leak file violation from ip {attacker_ip}: path: {target_path}")
        if not response:
            log.msg("Specific trap type: leak simple file - No response")
            return

        # Handle list response from new canary tokens
        if isinstance(response, list):
            response = response[0]

        url = response.get("token_url")
        if not url:
            return

        # log listening process assignment
        basename = os.path.basename(target_path)
        # File injection
        vpath = self._inject_file_into_fs(target_path, content.encode('utf-8'))
        if not vpath:
            return

        # adding file to the lookup for it to be monitored (path-based key)
        self.lookup_files[vpath] = (os.path.basename(vpath), url)
    def trap_file_subs(self, prediction):
        """
        the curl and wget command simulation has been modified so that they act on their own with 
        a file sustitution strategy. here we send them context to see if the prediction was right
        """
        # context dictionary
        context_data = {
            "comment" : "Prediction of malware download",
            "predicted_path": prediction.get("trap_path"),
            "timestamp": time.time(),
        }
        
        # self.protocol is part of the context shared by wget/curl
        self.protocol.ai_prediction_queue.append(context_data)
        
        log.msg(f"AI PREDICTION QUEUED: Total active predictions: {len(self.protocol.ai_prediction_queue)}")
        
        return defer.succeed(None)

    def _inject_file_into_fs(self, virtual_path: str, content_bytes: bytes):
        """        Inject/replace a file in Cowrie's simulated FS and back it with a real temp file.

        Returns canonical absolute virtual path (string) on success, None on failure.
        """
        import os
        import tempfile
        from cowrie.shell import fs
        
        # Create a persistent temp file for the content
        # delete=False is crucial so it persists after closure
        fd, real_path = tempfile.mkstemp(prefix="cowrie_trap_")
        os.write(fd, content_bytes)
        os.close(fd)

        os.chmod(real_path, 0o644)


        # Ensure parent directory exists
        dirname = os.path.dirname(virtual_path)
        try:
            self._ensure_directory_exists(dirname)
        except Exception as e:
            log.msg(f"Critical FS error (ensure_dir) for {virtual_path}: {e}")
            try:
                os.unlink(real_path)
            except OSError:
                pass
            return None

        # Create or Update the file entry
        try:    
            target_uid, target_gid = self._get_owner_from_path(virtual_path)
            
            created = self.protocol.fs.mkfile(
                virtual_path,
                target_uid,
                target_gid,
                len(content_bytes),
                0o100644
            )

            file_entry = self.protocol.fs.getfile(virtual_path)
            
            executable_exts = ('.sh', '.py', '.pl', '.exe', '.bin')
            is_executable = virtual_path.lower().endswith(executable_exts) or '/bin/' in virtual_path or '/sbin/' in virtual_path
            perm=  33261 if is_executable else 33188 # 0755 if ex, else 0644

            if file_entry:
                # CRITICAL: Always update the realfile pointer
                # This fixes the "FileNotFound" error by ensuring the metadata 
                # points to the NEW temp file we just created.
                file_entry[fs.A_CONTENTS] = None
                file_entry[fs.A_REALFILE] = real_path
                file_entry[fs.A_TYPE]     = fs.T_FILE
                file_entry[fs.A_SIZE] = len(content_bytes)
                file_entry[fs.A_MODE]  = perm
                file_entry[fs.A_CTIME] = timestamp_creation(real_path)
                
                log.msg(f"Injected/Updated trap file at {virtual_path} -> {real_path}")
                return virtual_path
            
            # If we reach here, we couldn't get the file entry at all
            log.msg(f"Failed to resolve file entry for {virtual_path}")
            os.unlink(real_path)
            return None

        except Exception as e:
            log.msg(f"Failed to inject file {virtual_path}: {e}")
            try:
                os.unlink(real_path)
            except OSError:
                pass
            return None

    def _ensure_directory_exists(self, path: str):
        """        mkdir -p in Cowrie FS using your fs.py signature:
        mkdir(path, uid, gid, size, mode, ctime=None)
        """
        import os

        path = self.protocol.fs.resolve_path(path, self.protocol.cwd)

        if path in ("", "/"):
            return "/"

        if self.protocol.fs.exists(path):
            return path

        parent = os.path.dirname(path) or "/"
        if parent != path:
            self._ensure_directory_exists(parent)

        target_uid, target_gid = self._get_owner_from_path(path)
        ctime = timestamp_creation(path)

        # size=4096, mode=16877 (0o40755)
        self.protocol.fs.mkdir(path, target_uid, target_gid, 4096, 16877, ctime=ctime)
        log.msg(f"Created directory {path}")
        return path

    def _load_passwd_database(self) -> None:
        """
        Reads /etc/passwd and caches it into {username: (uid, gid)}.
        """
        try:
            # obtaining passwd from /etc/
            etc_node = self.protocol.fs.resolve_path("/etc", "/")
            files_in_etc = self.protocol.fs.get_path(etc_node)
            
            passwd_entry = next((f for f in files_in_etc if f[fs.A_NAME] == "passwd"), None)
            
            if not passwd_entry:
                log.msg("Warning: /etc/passwd not found in FS simulation")
                return

            # getting passwd content
            real_path = passwd_entry[fs.A_REALFILE]
            
            if real_path and os.path.exists(real_path):
                with open(real_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        
                        # standard passwd line format user:x:uid:gid:comment:home:shell
                        parts = line.split(":")
                        if len(parts) >= 4:
                            username = parts[0]
                            try:
                                uid = int(parts[2])
                                gid = int(parts[3])
                                self.user_db_cache[username] = (uid, gid)
                            except ValueError:
                                continue
            else:
                log.msg(f"Critical: Virtual /etc/passwd points to missing real file: {real_path}")

        except Exception as e:
            log.msg(f"Error loading passwd database: {e}")


    def _get_owner_from_path(self, path):
        """
        Gets UID and GUID from chached passwd informations
        """
        parts = path.strip('/').split('/')
        
        # home directory case(es. /home/user/...)
        if len(parts) >= 2 and parts[0] == 'home':
            target_username = parts[1]
            
            # DB lookup
            if target_username in self.user_db_cache:
                uid, gid = self.user_db_cache[target_username]
                return int(uid), int(gid)
            
            # Fallback, if current id is not present in /etc/passwd
            if target_username == self.protocol.user.username:
                return int(self.protocol.user.uid), int(self.protocol.user.gid) 
            
            # Fallback n°2: standard uid
            return 1000, 1000

        # Se il path è /root o sottocartelle
        if len(parts) >= 1 and parts[0] == 'root':
             return 0, 0
        # final fallback
        return 0, 0
    
    @defer.inlineCallbacks
    def canary_request(self, token_type, memo="Honeypot intrusion"):
        type_mapping = {
            "aws_keys": "aws_keys",
            "kubeconfig": "kubeconfig",
            "wireguard": "wireguard",
            "adobe_pdf": "adobe_pdf",
            "web": "web"
        }

        if token_type not in type_mapping:
            log.msg(f"Error: token_type '{token_type}' not supported for canary generation.")
            return None

               
        payload = {
            "memo": f"{memo}\ncowrie_session_id={self.protocol.sess_id}",
            "type": type_mapping[token_type],
            "webhook_url": f"http://{WEBHOOK_IP}:9000/webhook"
        }

        # async POST request
        try:
            response = yield treq.post(API_URL, data=payload, timeout=3)
            
            if response.code != 200:
                log.msg(f"Canary API failed with code {response.code}")
                return None

            content = yield response.content()
            data = json.loads(content)
            
            # API returns a list with one object or a single object -> this handles both
            if isinstance(data, list):
                if len(data) > 0:
                    result = data[0]
                else:
                    return None
            else:
                result = data

            # patch the token_url to include the public port 8008
            if 'token_url' in result:
                result['token_url'] = result['token_url'].replace(WEBHOOK_IP, f"{WEBHOOK_IP}:8008")

            return result

        except Exception as e:
            log.msg(f"Error generating canary token: {e}")
            return None
    
    def check_leak_file(self, line: str) -> None:
        """       
        If attacker references a watched file path, fire its canary and remove it.
        """
        if not self.lookup_files:
            return

        try:
            tokens = shlex.split(line)
        except ValueError as e:
            log.err(f"shlex failed on '{line}': {e}")
            return

        for watched_vpath, (_basename, url) in list(self.lookup_files.items()):
            candidate_paths = [
                t for t in tokens
                if _basename == t or _basename in t
            ]

            if not candidate_paths:
                continue

            matching_path = None
            for  path in candidate_paths:
                try:
                    with timeout(0.1):
                        abs_path = self.protocol.fs.resolve_path(path, self.protocol.cwd)
                        f = self.protocol.fs.getfile(abs_path)
                        if f is not None :
                            matching_path =abs_path
                            break #found abs path, 
                except TimeoutError:
                    log.err(f"FS timeout on path '{path}'")
                    continue
                except Exception as e:
                    log.err(f"FS error on '{path}': {e}")
                    continue

            if  matching_path and matching_path == watched_vpath:
                log.msg(f"CANARY HIT: {matching_path} -> {url}")
                self.fire_canary_token(url)
                self.lookup_files.pop(watched_vpath, None)
                break

    def fire_canary_token(self, token_url):
        # fire and forget request
        log.msg(f"firing leak notification to {token_url}")
        d = treq.get(token_url, timeout=5.0, unbuffered=True)
        
        # callback to ignore the body, no RAM consumption
        def _drain(resp):
            return resp.collect(lambda _: None)

        # async call to the canary: response and errors are not needed
        d.addCallback(_drain)
        d.addErrback(lambda _: None)# silent error handling
        
        return d
    
    def isbash(self, cmd):
        if not getattr(self.protocol, "fs", None):
            return False

        try:
            with timeout(0.1):
                abs_path = self.protocol.fs.resolve_path(cmd, self.protocol.cwd)
                file = self.protocol.fs.getfile(abs_path)
        except TimeoutError:
            log.msg(f"triggered timeout while looking for {file}")
            return False
        if file:
            firstline=""
            content= file[fs.A_CONTENTS]
            if content: #inline content existing
                firstline = content.split('\n')[0]
            else: # file[fs.A_CONTENTS] =None, check for real file content's
                realfile= file[fs.A_REALFILE]
                if realfile and os.path.exists(realfile):
                    with open(realfile, 'r', encoding='utf-8', errors='ignore') as f:
                        firstline = f.readline().strip()

            shebang = firstline.strip().lstrip('#')
            
            # Shebang patterns (case insensitive)
            bash_patterns = [
                '!/bin/bash',
                '!/bin/sh', 
                '!/usr/bin/bash',
                '!/usr/bin/sh',
                '!/bin/dash',  # Debian Almquist Shell
            ]
            return any(pattern in shebang for pattern in bash_patterns)
        else:
            return False


def timestamp_creation(path):
    depth = path.count('/')
    base_time = time.time() - (86400 * 30) # 30 days ago
    fake_time =  base_time + (depth * 3600) + random.randint(0, 3000)

    # fallback if it surpasses now
    if fake_time > time.time():
        fake_time = time.time() - 10
    return fake_time

def get_attacker_ip(transport):
    """
    Get the real attacker IP, supporting PROXY protocol.
    Walks up the transport chain to find the SSH transport with getClientIP().
    """
    if not transport:
        return "unknown"
    
    # Try to find the SSH transport with getClientIP method (PROXY protocol support)
    # Walk up the chain: terminal.transport -> session -> conn -> transport (SSH)
    current = transport
    for _ in range(10):  # Prevent infinite loops
        if hasattr(current, 'getClientIP'):
            return current.getClientIP()
        
        # Try various paths up the transport chain
        if hasattr(current, 'session'):
            session = current.session
            if hasattr(session, 'conn') and hasattr(session.conn, 'transport'):
                current = session.conn.transport
                continue
        
        if hasattr(current, 'transport'):
            current = current.transport
            continue
            
        break
    
    # Fallback to old method if getClientIP not found
    if hasattr(transport, "getPeer"):
        peer = transport.getPeer()
        host = getattr(peer, "host", None)
        if host:
            return host
        address = getattr(peer, "address", None)
        if address:
            return address
        return str(peer)
    
    return "unknown"

'''old
def get_attacker_ip(transport):
    if not transport or not hasattr(transport, "getPeer"):
        return "unknown"

    peer = transport.getPeer()

    # Safe attribute access (no hasattr)
    host = getattr(peer, "host", None)
    if host:
        return host

    address = getattr(peer, "address", None)
    if address:
        return address

    # Final fallback
    return str(peer)
'''

@contextmanager
def timeout(seconds):
    def timeout_handler(signum, frame):
        raise TimeoutError("FS operation timeout")
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
#%++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++