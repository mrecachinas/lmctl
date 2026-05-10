# lmctl

Small CLI for La Marzocco Home machines using
[`pylamarzocco`](https://github.com/zweckj/pylamarzocco).

## Install

```bash
cd /Users/mrecachinas/Projects/Personal/lmctl
uv tool install --editable .
lmctl login
```

If `lmctl` is not on your `PATH`, run `uv tool update-shell` and restart your
shell.

## Common commands

```bash
lmctl login                  # authenticate, save password, choose default machine
lmctl password save          # save/update password later
lmctl switch                 # arrow-key picker for a different default machine
lmctl things
lmctl show
lmctl dashboard
lmctl power on
lmctl steam off
```

Use `--serial SERIAL` with `login`/`switch`, or pass `SERIAL` to machine
commands, to avoid the configured default.

## Config

Default config: `~/.config/lmctl/config.json`

```json
{
  "username": "you@example.com",
  "default_serial": "SERIAL"
}
```

The installation key is stored separately at
`~/.config/lmctl/installation_key.json`. Override paths with `--config-file`,
`--key-file`, `LMCTL_CONFIG_FILE`, or `LMCTL_KEY_FILE`.

Saved passwords use the OS keychain (`keyring` service `lmctl`) and are keyed by
username. Use `lmctl password status` or `lmctl password forget` to inspect or
remove the saved password. `lmctl login` saves by default; use
`lmctl login --no-save-password` or `--no-keyring` to opt out.

## Help

```text
usage: lmctl [-h] [--username USERNAME] [--password PASSWORD] [--no-keyring] [--key-file KEY_FILE]
             [--config-file CONFIG_FILE]
             {login,switch,password,config,key,register,things,show,dashboard,settings,statistics,schedule,firmware,power,steam}
             ...

Control La Marzocco Home machines using pylamarzocco.

positional arguments:
  {login,switch,password,config,key,register,things,show,dashboard,settings,statistics,schedule,firmware,power,steam}
    login               Authenticate, choose a machine, and save defaults.
    switch              Choose a different default machine.
    password            Manage the saved keychain password.
    config              Manage lmctl defaults.
    key                 Manage installation keys.
    register            Register the current installation key with La Marzocco.
    things              List account devices.
    show                Fetch dashboard, settings, statistics, schedule, and firmware.
    dashboard           Fetch a machine dashboard.
    settings            Fetch machine settings.
    statistics          Fetch machine statistics.
    schedule            Fetch a machine schedule.
    firmware            Fetch firmware information.
    power               Turn a machine on or off.
    steam               Turn steam on or off.

options:
  -h, --help            show this help message and exit
  --username USERNAME   La Marzocco Home username. Defaults to LMCTL_USERNAME or LAMARZOCCO_USERNAME, then saved config.
  --password PASSWORD   La Marzocco Home password. Defaults to LMCTL_PASSWORD, LAMARZOCCO_PASSWORD, saved keychain password, or an interactive prompt.
  --no-keyring          Do not read from or write to the OS keychain for this invocation.
  --key-file KEY_FILE   Installation key JSON file. Defaults to LMCTL_KEY_FILE or ~/.config/lmctl/installation_key.json.
  --config-file CONFIG_FILE
                        Configuration JSON file. Defaults to LMCTL_CONFIG_FILE or ~/.config/lmctl/config.json.
```

## Development

```bash
uv run pytest -q
uv build
```
