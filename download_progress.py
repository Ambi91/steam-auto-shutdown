"""Live estimate of Steam download progress.

Steam doesn't rewrite appmanifest_*.acf while it downloads – only when a download
starts, pauses or finishes – so the byte counts there stand still for the whole
download. The estimate combines two sources that do change live:

* Steam's logs/content_log.txt says right away which app started or stopped
  downloading, and how many bytes were already done ("update started : download X/Y").
* The bytes Steam has received over the network since then are added to that.
  On macOS these are counted for Steam's own processes (nettop); on Linux and
  Windows for all network interfaces, as per-process counters would need extra
  libraries – other traffic then counts too.

It is an estimate (compressed downloads and other traffic make it a little off);
the manifest value replaces it whenever Steam writes a new one.
"""

import re
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

# [2026-11-22 17:11:24] AppID 457140 App update changed : Running Update,Downloading,Staging,
LOG_LINE = re.compile(r"^\[[^\]]+\] AppID (?P<appid>\d+) (?P<event>[^:]+?) : (?P<rest>.*)$")
UPDATE_STARTED = re.compile(r"download (\d+)/(\d+)")


def _run(cmd):
    kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}  # CREATE_NO_WINDOW
    return subprocess.run(cmd, capture_output=True, text=True, timeout=5, **kw).stdout


def read_net_bytes():
    """Total bytes received so far (see the module docstring for what is counted), or None."""
    try:
        if sys.platform == "darwin":
            total, found = 0, False
            for line in _run(["nettop", "-P", "-L", "1", "-x", "-J", "bytes_in"]).splitlines():
                parts = line.split(",")
                if len(parts) >= 2 and "steam" in parts[0].lower() and parts[1].strip().isdigit():
                    total += int(parts[1])
                    found = True
            return total if found else None
        if sys.platform.startswith("linux"):
            total = 0
            for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
                name, data = line.split(":", 1)
                if name.strip() != "lo":
                    total += int(data.split()[0])
            return total
        if sys.platform == "win32":
            # "netstat -e": the first row with two numbers is "Bytes  <received>  <sent>"
            # (the label is translated on non-English Windows, the order isn't).
            for line in _run(["netstat", "-e"]).splitlines():
                nums = [p for p in line.split() if p.isdigit()]
                if len(nums) == 2:
                    return int(nums[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


class ContentLog:
    """Follows Steam's content_log.txt and remembers, per app, whether it is downloading."""

    TAIL = 256 * 1024  # on the first read, look only at the end of the log

    def __init__(self, path):
        self.path = Path(path)
        self.pos = None
        self.downloading = {}  # appid -> True/False, from the last "App update changed" line
        self.suspended = {}    # appid -> True/False, from the last "state changed" line
        self.started = {}      # appid -> bytes done when the last download started

    def poll(self):
        """Read the new lines. Returns the appids that started downloading since the last poll."""
        try:
            size = self.path.stat().st_size
        except OSError:
            return set()
        if self.pos is None:
            self.pos = max(0, size - self.TAIL)
        elif size < self.pos:  # Steam started a new log
            self.pos = 0
        if size <= self.pos:
            return set()
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read(size - self.pos)
        except OSError:
            return set()
        end = data.rfind(b"\n")
        if end < 0:
            return set()  # only half a line so far
        self.pos += end + 1
        started = set()
        for line in data[:end].decode("utf-8", "replace").splitlines():
            m = LOG_LINE.match(line.strip())
            if not m:
                continue
            appid, event, rest = m["appid"], m["event"], m["rest"]
            if event == "App update changed":
                now = "Downloading" in rest
                if now and not self.downloading.get(appid):
                    started.add(appid)
                self.downloading[appid] = now
            elif event == "state changed":
                # A paused download ends with "(Suspended)"; StateFlags in the manifest
                # look the same for a paused and a running download.
                self.suspended[appid] = "(Suspended)" in rest
            elif event == "update started":
                s = UPDATE_STARTED.search(rest)
                if s:
                    self.started[appid] = int(s[1])
        return started


class ProgressEstimator:
    """Estimates bytes downloaded for the app Steam is downloading right now."""

    def __init__(self, log_path, net_reader=read_net_bytes, clock=time.monotonic):
        self.log = ContentLog(log_path) if log_path else None
        self.read_net, self.clock = net_reader, clock
        self.samples = deque(maxlen=8)  # (time, net bytes) – for the download speed
        self.base = None  # (appid, bytes done at base, net bytes at base, manifest bytes at base)
        self.current = None  # appid being downloaded right now (after the last estimate())

    def is_paused(self, appid):
        """True if Steam's log says the app's download is paused."""
        return bool(self.log and self.log.suspended.get(appid)) and appid != self.current

    def _current(self, items):
        """Appid of the app downloading now (Steam downloads one at a time), or None."""
        ids = [item[0] for item in items]
        if self.log is not None:
            for appid in ids:
                if self.log.downloading.get(appid):
                    return appid
        # No log (or it doesn't mention these apps): trust the manifest's Downloading bit.
        for appid, _name, _done, _total, flags in items:
            if flags & 1048576:
                return appid
        return None

    def speed(self):
        """Bytes per second over the last ~30 s of samples, or None."""
        if len(self.samples) < 2:
            return None
        (t0, b0), (t1, b1) = self.samples[0], self.samples[-1]
        if t1 - t0 < 1 or b1 < b0:
            return None
        return (b1 - b0) / (t1 - t0)

    def estimate(self, items):
        """items: (appid, name, done, total, flags) of active downloads.
        Returns {appid: (estimated bytes done, bytes per second or None)} – for the one app
        downloading right now, or {} when there is nothing to estimate."""
        restarted = self.log.poll() if self.log else set()
        appid = self.current = self._current(items)
        if appid is None:
            self.base = None
            self.samples.clear()
            return {}
        net = self.read_net()
        if net is None:
            return {}
        now = self.clock()
        if self.samples and net < self.samples[-1][1]:
            self.samples.clear()  # counter reset (Steam or the network restarted)
        self.samples.append((now, net))

        item = next(i for i in items if i[0] == appid)
        done, total = item[2], item[3]
        if (self.base is None or self.base[0] != appid or appid in restarted
                or done != self.base[3] or net < self.base[2]):
            start = self.log.started.get(appid, 0) if self.log else 0
            self.base = (appid, max(done, start), net, done)
        est = self.base[1] + (net - self.base[2])
        if total:
            est = min(est, total - 1)  # never claim "done" before Steam does
        return {appid: (est, self.speed())}
