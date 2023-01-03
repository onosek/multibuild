## Purpose
_Multibuild_ script speeds up operations during release process.
It works with _rhpkg_ utility (and custom commands) in _dist-git_
repos and runs tasks in threads. It also switches branches
automatically.

## Installation

```
git clone https://github.com/onosek/multibuild
cd multibuild
python3 setup.py sdist
pip3 install --user dist/multibuild-XXX.tar.gz
```

## Configuration

Configuration is hierarchical (INI format). The Main user's config
file:
```
    ~/.local/multibuild/multibuild.conf
```
For setting the Ansible credentials use the main config file
preferably. 'Username' and 'token' values from there will work
across the user's account.

Use the project's config file
```
    /<project_path>/multibuild.conf
```
to set 'active_branches' value, because it is specific to the project.

If there is no project's config file (or some variables are not
specified), all missing values are taken from the main config file.
```
[section]
var1=
var2=bbb
```
Warning: both 'var1' and 'var2' are considered as specified although
'var1' is an empty string. If you need 'var1' to be taken from
the main config, comment it with '#' or remove the line.
