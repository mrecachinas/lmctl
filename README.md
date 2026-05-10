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
lmctl login          # authenticate, choose a machine, save defaults
lmctl switch         # arrow-key picker for a different default machine
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

Passwords are not stored. The installation key is stored separately at
`~/.config/lmctl/installation_key.json`. Override paths with `--config-file`,
`--key-file`, `LMCTL_CONFIG_FILE`, or `LMCTL_KEY_FILE`.

## Help

```text
usage: lmctl [-h] [--username USERNAME] [--password PASSWORD] [--key-file KEY_FILE] [--config-file CONFIG_FILE]
             {login,switch,config,key,register,things,show,dashboard,settings,statistics,schedule,firmware,power,steam}
             ...

Control La Marzocco Home machines using pylamarzocco.

positional arguments:
  {login,switch,config,key,register,things,show,dashboard,settings,statistics,schedule,firmware,power,steam}
    login               Authenticate, choose a machine, and save defaults.
    switch              Choose a different default machine.
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
  --password PASSWORD   La Marzocco Home password. Defaults to LMCTL_PASSWORD, LAMARZOCCO_PASSWORD, or an interactive prompt.
  --key-file KEY_FILE   Installation key JSON file. Defaults to LMCTL_KEY_FILE or ~/.config/lmctl/installation_key.json.
  --config-file CONFIG_FILE
                        Configuration JSON file. Defaults to LMCTL_CONFIG_FILE or ~/.config/lmctl/config.json.
```

## Development

```bash
uv run pytest -q
uv build
```
