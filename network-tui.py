#!/usr/bin/env python3
# network-tui — NetworkManager TUI with native vim keybindings.
# Replaces nmtui, whose newt widget set cannot be rebound (see repo
# history for the foot text-bindings and tmux-shim attempts). Everything
# shells out to nmcli; @nmcli@ is substituted with the Nix store path by
# home-manager at build time. Colors match the fzf/newt popups: default
# (transparent) background, cyan selection.
#
#   j/k        move           gg / G    top / bottom
#   Ctrl+d/u   half page      /         filter (Esc or empty clears)
#   Enter / l  select         h / q     back (q at the main menu: quit)
#   Wi-Fi:       Enter connect · d disconnect · r rescan
#   Connections: Enter up/down · e edit · a autoconnect · x delete
#   Editor:      Enter edit/cycle field · s save · h back

import curses
import os
import subprocess

NMCLI = "@nmcli@"

ENTER_KEYS = (curses.KEY_ENTER, 10, 13, ord("l"))
BACK_KEYS = (ord("h"), ord("q"))


def run(*args, timeout=60):
    """Run nmcli, return (rc, stdout, stderr)."""
    try:
        p = subprocess.run(
            [NMCLI, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "LC_ALL": "C"},
        )
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)


def terse(line):
    """Split one `nmcli -g` line on unescaped colons."""
    out, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def bars(signal):
    n = min(4, max(0, (signal + 24) // 25))
    return ("▂▄▆█"[:n]).ljust(4)


class App:
    def __init__(self, stdscr):
        self.scr = stdscr
        self.msg = ""
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)  # selection
        curses.init_pair(2, curses.COLOR_CYAN, -1)                  # title
        curses.init_pair(3, curses.COLOR_WHITE, -1)                 # footer hint
        curses.init_pair(4, curses.COLOR_YELLOW, -1)                # message
        self.scr.keypad(True)

    # ---------- drawing ----------

    def _put(self, y, x, text, attr=0):
        h, w = self.scr.getmaxyx()
        if 0 <= y < h:
            try:
                self.scr.addnstr(y, x, text, max(0, w - x - 1), attr)
            except curses.error:
                pass

    def draw(self, title, rows, sel, top, footer, filt):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        body = h - 4
        self._put(0, 1, title, curses.color_pair(2) | curses.A_BOLD)
        self._put(1, 1, "─" * (w - 2), curses.color_pair(3) | curses.A_DIM)
        for i in range(body):
            idx = top + i
            if idx >= len(rows):
                break
            attr = curses.color_pair(1) if idx == sel else 0
            self._put(2 + i, 1, (" " + rows[idx]).ljust(w - 2), attr)
        status = footer + (f"   /{filt}" if filt else "")
        self._put(h - 2, 1, status, curses.color_pair(3) | curses.A_DIM)
        if self.msg:
            self._put(h - 1, 1, self.msg, curses.color_pair(4))
        self.scr.refresh()

    def note(self, text):
        self.msg = text[:200]

    def busy(self, text):
        h, _ = self.scr.getmaxyx()
        self._put(h - 1, 1, text, curses.color_pair(4) | curses.A_BOLD)
        self.scr.refresh()

    # ---------- input widgets ----------

    def prompt(self, label, secret=False, initial=""):
        """Line editor on the bottom row. Enter=accept, Esc=cancel(None)."""
        h, _ = self.scr.getmaxyx()
        buf = list(initial)
        while True:
            shown = "*" * len(buf) if secret else "".join(buf)
            self._put(h - 1, 1, (label + shown + " ").ljust(120))
            curses.curs_set(1)
            self.scr.refresh()
            c = self.scr.getch()
            if c in (10, 13, curses.KEY_ENTER):
                curses.curs_set(0)
                return "".join(buf)
            if c == 27:  # Esc
                curses.curs_set(0)
                return None
            if c in (curses.KEY_BACKSPACE, 127, 8):
                if buf:
                    buf.pop()
            elif 32 <= c <= 126:
                buf.append(chr(c))

    def confirm(self, question):
        h, _ = self.scr.getmaxyx()
        self._put(h - 1, 1, (question + " [y/N] ").ljust(120), curses.color_pair(4))
        self.scr.refresh()
        return self.scr.getch() in (ord("y"), ord("Y"))

    # ---------- generic vim list ----------

    def pick(self, title, rows, footer, extra_keys="", sel=0):
        """Vim-keyed list. Returns (action, original_index):
        action is 'enter', a char from extra_keys, or None for back."""
        filt = ""
        top = 0
        pending_g = False
        while True:
            vis = [i for i, r in enumerate(rows) if filt.lower() in r.lower()] \
                if filt else list(range(len(rows)))
            if not vis:
                vis_sel = -1
            else:
                sel = max(0, min(sel, len(vis) - 1))
                vis_sel = sel
            h, _ = self.scr.getmaxyx()
            body = max(1, h - 4)
            if vis_sel >= 0:
                top = min(top, vis_sel)
                top = max(top, vis_sel - body + 1)
            self.draw(title, [rows[i] for i in vis], vis_sel, top, footer, filt)
            c = self.scr.getch()
            self.msg = ""
            if c == ord("g"):
                if pending_g:
                    sel, pending_g = 0, False
                else:
                    pending_g = True
                continue
            pending_g = False
            if c == ord("j") or c == curses.KEY_DOWN:
                sel += 1
            elif c == ord("k") or c == curses.KEY_UP:
                sel -= 1
            elif c == ord("G"):
                sel = len(vis) - 1
            elif c == 4:  # Ctrl+d
                sel += body // 2
            elif c == 21:  # Ctrl+u
                sel -= body // 2
            elif c == ord("/"):
                new = self.prompt("/")
                filt = new or ""
                sel, top = 0, 0
            elif c in BACK_KEYS or c == 27:
                return None, None
            elif c in ENTER_KEYS and vis_sel >= 0:
                return "enter", vis[vis_sel]
            elif 0 <= c < 256 and chr(c) in extra_keys:
                return chr(c), vis[vis_sel] if vis_sel >= 0 else None
            if vis:
                sel = max(0, min(sel, len(vis) - 1))


# ---------- data helpers ----------

def wifi_networks(rescan=False):
    args = ["-g", "IN-USE,SSID,SECURITY,SIGNAL", "device", "wifi", "list"]
    if rescan:
        args += ["--rescan", "yes"]
    rc, out, err = run(*args, timeout=90)
    nets = {}
    for line in out.splitlines():
        f = terse(line)
        if len(f) < 4 or not f[1]:
            continue
        net = {
            "inuse": f[0] == "*",
            "ssid": f[1],
            "sec": f[2] if f[2] and f[2] != "--" else "",
            "sig": int(f[3] or 0),
        }
        cur = nets.get(net["ssid"])
        if not cur or net["inuse"] or net["sig"] > cur["sig"]:
            net["inuse"] = net["inuse"] or (cur["inuse"] if cur else False)
            nets[net["ssid"]] = net
    return sorted(nets.values(), key=lambda n: (not n["inuse"], -n["sig"])), err


def wifi_device():
    rc, out, _ = run("-g", "DEVICE,TYPE", "device")
    for line in out.splitlines():
        f = terse(line)
        if len(f) >= 2 and f[1] == "wifi":
            return f[0]
    return "wlan0"


def saved_connections():
    rc, out, err = run("-g", "NAME,UUID,TYPE,DEVICE", "connection", "show")
    cons = []
    for line in out.splitlines():
        f = terse(line)
        if len(f) >= 4:
            cons.append({"name": f[0], "uuid": f[1],
                         "type": f[2].split("-")[-1], "dev": f[3]})
    return cons, err


# ---------- screens ----------

def wifi_screen(app):
    rescan = False
    while True:
        app.busy("Scanning..." if rescan else "Listing networks...")
        nets, err = wifi_networks(rescan)
        rescan = False
        if err and not nets:
            app.note(err)
        rows = [
            f'{"*" if n["inuse"] else " "} {n["ssid"]:<30.30} {bars(n["sig"])} {n["sec"]}'
            for n in nets
        ] or ["(no networks found)"]
        act, i = app.pick("Wi-Fi networks", rows,
                          "Enter connect · d disconnect · r rescan · / filter · h back",
                          extra_keys="dr")
        if act is None:
            return
        if act == "r":
            rescan = True
            continue
        if not nets:
            continue
        net = nets[i]
        if act == "d":
            app.busy("Disconnecting...")
            names = {c["name"] for c in saved_connections()[0] if c["dev"]}
            target = net["ssid"] if net["ssid"] in names else None
            rc, _, err = run("connection", "down", "id", target) if target else \
                run("device", "disconnect", wifi_device())
            app.note(err or "Disconnected.")
        elif act == "enter":
            if net["inuse"]:
                app.note(f'Already connected to {net["ssid"]}.')
                continue
            saved = {c["name"] for c in saved_connections()[0]}
            app.busy(f'Connecting to {net["ssid"]}...')
            if net["ssid"] in saved:
                rc, _, err = run("connection", "up", "id", net["ssid"], timeout=90)
            elif net["sec"]:
                pw = app.prompt(f'Password for {net["ssid"]}: ', secret=True)
                if pw is None:
                    continue
                app.busy(f'Connecting to {net["ssid"]}...')
                rc, _, err = run("device", "wifi", "connect", net["ssid"],
                                 "password", pw, timeout=90)
            else:
                rc, _, err = run("device", "wifi", "connect", net["ssid"], timeout=90)
            app.note(err if rc else f'Connected to {net["ssid"]}.')


def connections_screen(app):
    while True:
        cons, err = saved_connections()
        if err and not cons:
            app.note(err)
        rows = [
            f'{"*" if c["dev"] else " "} {c["name"]:<32.32} {c["type"]:<10.10} {c["dev"]}'
            for c in cons
        ] or ["(no saved connections)"]
        act, i = app.pick("Connections", rows,
                          "Enter up/down · e edit · a autoconnect · x delete · h back",
                          extra_keys="eax")
        if act is None:
            return
        if not cons:
            continue
        con = cons[i]
        if act == "enter":
            if con["dev"]:
                app.busy(f'Deactivating {con["name"]}...')
                rc, _, err = run("connection", "down", "uuid", con["uuid"])
            else:
                app.busy(f'Activating {con["name"]}...')
                rc, _, err = run("connection", "up", "uuid", con["uuid"], timeout=90)
            app.note(err or "OK.")
        elif act == "a":
            rc, cur, _ = run("-g", "connection.autoconnect",
                             "connection", "show", con["uuid"])
            new = "no" if cur == "yes" else "yes"
            rc, _, err = run("connection", "modify", con["uuid"],
                             "connection.autoconnect", new)
            app.note(err or f'autoconnect {new} for {con["name"]}.')
        elif act == "x":
            if app.confirm(f'Delete connection "{con["name"]}"?'):
                rc, _, err = run("connection", "delete", "uuid", con["uuid"])
                app.note(err or f'Deleted {con["name"]}.')
        elif act == "e":
            edit_screen(app, con)


def edit_screen(app, con):
    ipv4_methods = ["auto", "manual", "disabled", "shared"]
    ipv6_methods = ["auto", "manual", "disabled", "ignore"]
    props = [
        ("Autoconnect", "connection.autoconnect", "toggle"),
        ("IPv4 method", "ipv4.method", ipv4_methods),
        ("IPv4 addresses (a.b.c.d/nn)", "ipv4.addresses", "text"),
        ("IPv4 gateway", "ipv4.gateway", "text"),
        ("IPv4 DNS", "ipv4.dns", "text"),
        ("IPv6 method", "ipv6.method", ipv6_methods),
    ]
    if con["type"] == "wireless":
        props.append(("Wi-Fi password", "802-11-wireless-security.psk", "secret"))

    rc, out, err = run("-g", ",".join(p[1] for p in props),
                       "connection", "show", con["uuid"])
    vals = out.splitlines()
    vals += [""] * (len(props) - len(vals))
    vals = dict(zip((p[1] for p in props), vals))
    dirty = {}

    while True:
        rows = []
        for label, prop, _kind in props:
            v = dirty.get(prop, vals.get(prop, ""))
            if _kind == "secret":
                v = "(hidden — Enter to set)" if not dirty.get(prop) else "(changed)"
            rows.append(f'{label:<30.30} {v or "(unset)"}'
                        + ("  *" if prop in dirty else ""))
        act, i = app.pick(f'Edit: {con["name"]}', rows,
                          "Enter edit/cycle · s save · h back", extra_keys="s")
        if act is None:
            if dirty and not app.confirm("Discard unsaved changes?"):
                continue
            return
        if act == "s":
            errs = []
            for prop, val in dirty.items():
                rc, _, err = run("connection", "modify", con["uuid"], prop, val)
                if rc:
                    errs.append(err)
            if errs:
                app.note("; ".join(errs))
            else:
                dirty.clear()
                app.note("Saved. Reactivate the connection to apply.")
            continue
        label, prop, kind = props[i]
        cur = dirty.get(prop, vals.get(prop, ""))
        if kind == "toggle":
            dirty[prop] = "no" if cur == "yes" else "yes"
        elif isinstance(kind, list):
            dirty[prop] = kind[(kind.index(cur) + 1) % len(kind)] \
                if cur in kind else kind[0]
        elif kind == "secret":
            new = app.prompt(f"{label}: ", secret=True)
            if new:
                dirty[prop] = new
        else:
            new = app.prompt(f"{label}: ", initial=cur)
            if new is not None and new != vals.get(prop, ""):
                dirty[prop] = new


def hostname_screen(app):
    rc, cur, _ = run("general", "hostname")
    new = app.prompt(f"Hostname [{cur}]: ", initial=cur)
    if new and new != cur:
        rc, _, err = run("general", "hostname", new)
        app.note(err or f"Hostname set to {new}.")


def main(stdscr):
    app = App(stdscr)
    sel = 0
    while True:
        _, radio, _ = run("radio", "wifi")
        _, host, _ = run("general", "hostname")
        rows = [
            "Wi-Fi networks",
            "Connections",
            f"Hostname   ({host})",
            f"Wi-Fi radio   ({radio})",
            "Quit",
        ]
        act, sel_i = app.pick("Network", rows,
                              "j/k move · Enter select · q quit")
        if act is None or sel_i == 4:
            return
        sel = sel_i
        if sel_i == 0:
            wifi_screen(app)
        elif sel_i == 1:
            connections_screen(app)
        elif sel_i == 2:
            hostname_screen(app)
        elif sel_i == 3:
            run("radio", "wifi", "off" if radio == "enabled" else "on")


if __name__ == "__main__":
    curses.wrapper(main)
