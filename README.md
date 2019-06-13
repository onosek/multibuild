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
