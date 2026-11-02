# network-tui

A NetworkManager TUI with vim keybindings, written to replace `nmtui`, whose
newt widgets can't be rebound. Everything shells out to `nmcli`.

Keys (from the header of `network-tui.py`): `j`/`k` move, `gg`/`G` top/bottom,
`Enter`/`l` select, `h`/`q` back (`q` at the main menu quits). Wi-Fi: `Enter`
connect, `d` disconnect, `r` rescan. Connections: `Enter` up/down, `e` edit,
`a` autoconnect, `x` delete. Editor: `Enter` edit/cycle field, `s` save, `h` back.

Single file, Python 3 standard library only (`curses`, `subprocess`).
`@nmcli@` is a placeholder for the `nmcli` path; substitute it at install
time (the install-script flake replaces it with the Nix store path) or
replace it with `nmcli` to run it directly:

```sh
sed 's|@nmcli@|nmcli|' network-tui.py > /tmp/network-tui && python3 /tmp/network-tui
```

Consumed by [install-script](https://github.com/zoraster-org/install-script)
as the `network-tui-src` flake input.

Licence: GPL-3.0 (see `LICENSE`), like the other zoraster-org tools.
