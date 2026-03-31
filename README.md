## Purpose
_Multibuild_ script speeds up operations during release process.
It works with _rhpkg_ utility (and custom commands) in _dist-git_
repos and runs tasks in threads. It also switches branches
automatically.

## Installation

```bash
git clone https://github.com/onosek/multibuild
cd multibuild
pip3 install --user .
```

Or for development (editable install):
```bash
pip3 install --user -e .
```

## Building

To build source and wheel packages:
```bash
pip3 install --user build
python3 -m build
```

Packages will be created in the `dist/` directory.

## Configuration

Configuration uses hierarchical INI format. On first run, multibuild automatically
creates a default config file at the platform-appropriate location:

- **Linux**: `~/.config/multibuild/multibuild.conf`
- **macOS**: `~/Library/Application Support/multibuild/multibuild.conf`
- **Windows**: `%LOCALAPPDATA%\multibuild\multibuild.conf`

The location respects XDG Base Directory specification on Linux (via `$XDG_CONFIG_HOME`).

### Configuration hierarchy

1. **User config** (`~/.config/multibuild/multibuild.conf`)
   For global settings like Ansible credentials. These values work across all projects.

2. **Repository config** (`/<repository_path>/multibuild.conf`)
   For repository-specific settings like `active_branches`.

If a variable is not specified in the project config, it falls back to the user config.

**Note**: Empty values in config files are treated as set:
```ini
[section]
var1=
var2=bbb
```
Both `var1` and `var2` are considered specified, even though `var1` is empty.
To use the fallback value from user config, comment out or remove the line.

## Shell Completion

To enable tab completion for bash:

```bash
# For current session
eval "$(register-python-argcomplete multibuild)"

# Permanently (add to ~/.bashrc)
echo 'eval "$(register-python-argcomplete multibuild)"' >> ~/.bashrc
```

Or enable globally for all Python scripts:
```bash
activate-global-python-argcomplete
```
