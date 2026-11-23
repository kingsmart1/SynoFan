#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiuFudi
#
# This file is part of synofan (a Synology port of niufan), licensed under the
# GNU General Public License version 3 or (at your option) any later version.
# See the LICENSE file for the full text.
"""Self-contained login guard for the Synology build.

The Synology nginx serves ``/webman/3rdparty/synofan/`` statically and without
authenticating the caller, so the daemon has to protect its own ``/api/``
surface.  This module adds a single-password login:

* the package writes a random *initial* password on first start;
* the operator logs in once and is forced to set a real password;
* setting it removes the plaintext bootstrap file;
* passwords are stored as PBKDF2-HMAC-SHA256;
* sessions are signed random tokens held in memory (a restart logs everyone
  out), delivered as an HttpOnly + SameSite cookie.

The public UI shell (HTML/JS/CSS) stays unauthenticated -- it carries no
state -- while every ``/api/`` call must present a valid session.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time

_SESSION_TTL = 12 * 3600
_SESSION_COOKIE = "synofan_sid"
_ITERATIONS = 200_000
_MAX_ATTEMPTS = 5
_ATTEMPT_WINDOW = 300
_LOGIN_DELAY = 0.4
_MIN_LENGTH = 8


class AuthGuard:
    def __init__(self, etc_dir, log=lambda msg: None):
        self.etc_dir = etc_dir
        self.log = log
        os.makedirs(etc_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._sessions = {}
        self._attempts = {}
        self._ensure_password()

    # -- password storage -------------------------------------------------- #

    def _auth_path(self):
        return os.path.join(self.etc_dir, "auth.json")

    def _initial_path(self):
        return os.path.join(self.etc_dir, "initial_password")

    def _ensure_password(self):
        if os.path.exists(self._auth_path()) or os.path.exists(self._initial_path()):
            return
        password = secrets.token_urlsafe(12)
        path = self._initial_path()
        with open(path, "w") as handle:
            os.chmod(path, 0o600)
            handle.write(password + "\n")
        self.log("wrote initial password to %s" % path)

    @staticmethod
    def _hash(password, salt, iterations):
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations)

    def _record(self):
        try:
            with open(self._auth_path(), "r") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def _verify(self, password, record):
        try:
            expected = bytes.fromhex(record["hash"])
            salt = bytes.fromhex(record["salt"])
            iterations = int(record["iterations"])
        except (KeyError, TypeError, ValueError):
            return False
        return hmac.compare_digest(self._hash(password, salt, iterations), expected)

    def _initial_password(self):
        try:
            with open(self._initial_path(), "r") as handle:
                return handle.read().strip()
        except OSError:
            return None

    # -- sessions ---------------------------------------------------------- #

    def _new_session(self):
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = time.time() + _SESSION_TTL
        return token

    def _session_valid(self, token):
        if not token:
            return False
        with self._lock:
            expires = self._sessions.get(token)
            if expires is None:
                return False
            if expires < time.time():
                del self._sessions[token]
                return False
            self._sessions[token] = time.time() + _SESSION_TTL
            return True

    def _drop_session(self, token):
        with self._lock:
            self._sessions.pop(token, None)

    def _session_token(self, handler):
        cookies = handler.headers.get("Cookie") or ""
        for part in cookies.split(";"):
            name, _, value = part.strip().partition("=")
            if name == _SESSION_COOKIE:
                return value
        return None

    # -- rate limiting ----------------------------------------------------- #

    def _client(self, handler):
        return handler.headers.get("X-Real-IP") or "0.0.0.0"

    def _throttled(self, key):
        with self._lock:
            now = time.time()
            count, start = self._attempts.get(key, (0, now))
            if now - start > _ATTEMPT_WINDOW:
                count, start = 0, now
            count += 1
            self._attempts[key] = (count, start)
            return count > _MAX_ATTEMPTS

    # -- HTTP glue --------------------------------------------------------- #

    def check(self, handler):
        """Authorisation for everything except the auth endpoints themselves."""
        path = handler._relative()
        if not path.startswith("/api/"):
            return None  # the static UI shell is public
        if self._session_valid(self._session_token(handler)):
            if not self.change_required():
                return None
            return (403, "需要先设置新密码")
        return (401, "需要登录")

    def __call__(self, handler):
        # fancontrold.authorise() invokes the guard as ``guard(handler)``, so
        # expose the policy check as the call operator as well.
        return self.check(handler)

    def route(self, handler, path):
        """Serve ``/api/auth/*``.  Returns True when handled."""
        if path == "/api/auth/session":
            authenticated = self._session_valid(self._session_token(handler))
            handler._json({
                "ok": True,
                "authenticated": authenticated,
                "change_required": authenticated and self.change_required(),
            })
            return True
        if path == "/api/auth/login" and handler.command == "POST":
            return self._do_login(handler)
        if path == "/api/auth/logout" and handler.command == "POST":
            self._drop_session(self._session_token(handler))
            handler._json({"ok": True})
            return True
        if path == "/api/auth/password" and handler.command == "POST":
            return self._do_password(handler)
        handler._error(404, "unknown endpoint")
        return True

    def _set_cookie(self, handler, token):
        secure = (handler.headers.get("X-Forwarded-Proto") or "").lower() == "https"
        cookie = "%s=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=%d" % (
            _SESSION_COOKIE, token, _SESSION_TTL)
        if secure:
            cookie += "; Secure"
        handler.send_header("Set-Cookie", cookie)

    def _do_login(self, handler):
        body = handler._read_body()
        password = ""
        if body is not None:
            try:
                password = str(json.loads(body.decode("utf-8")).get("password") or "")
            except (ValueError, UnicodeDecodeError):
                password = ""
        time.sleep(_LOGIN_DELAY)
        if self._throttled(self._client(handler)):
            handler._error(429, "尝试次数过多，请稍后再试")
            return True

        record = self._record()
        change_required = record is None
        if record is not None:
            ok = self._verify(password, record)
        else:
            initial = self._initial_password()
            ok = bool(initial) and hmac.compare_digest(password, initial)

        if not ok:
            handler._error(401, "密码错误")
            return True

        token = self._new_session()
        payload = json.dumps({"ok": True, "change_required": change_required}).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Cache-Control", "no-store")
        self._set_cookie(handler, token)
        handler.end_headers()
        handler.wfile.write(payload)
        return True

    def _do_password(self, handler):
        if not self._session_valid(self._session_token(handler)):
            handler._error(401, "需要登录")
            return True
        body = handler._read_body()
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (ValueError, UnicodeDecodeError):
            payload = {}
        new_password = str(payload.get("new") or "")
        record = self._record()
        if record is not None:
            current = str(payload.get("current") or "")
            if not self._verify(current, record):
                handler._error(403, "当前密码不正确")
                return True
        # In initial mode the session already proves possession of the
        # bootstrap password, so no "current" is required.
        if len(new_password) < _MIN_LENGTH:
            handler._error(400, "新密码至少 %d 位" % _MIN_LENGTH)
            return True
        self._store_password(new_password)
        handler._json({"ok": True})
        return True

    def _store_password(self, password):
        salt = secrets.token_bytes(16)
        record = {
            "salt": salt.hex(),
            "hash": self._hash(password, salt, _ITERATIONS).hex(),
            "iterations": _ITERATIONS,
        }
        path = self._auth_path()
        tmp = path + ".tmp"
        with open(tmp, "w") as handle:
            json.dump(record, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
        try:
            os.unlink(self._initial_path())
        except OSError:
            pass
        self.log("password set (initial bootstrap removed)")

    def change_required(self):
        return self._record() is None
