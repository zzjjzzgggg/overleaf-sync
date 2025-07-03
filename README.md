# Overleaf/CE Sync

## Install
```
pip install -e .
```

## Usage
```
Usage: ols [OPTIONS] COMMAND [ARGS]...

Options:
  --push               Push local files to remote.
  --pull               Pull remote files to local.
  -n, --name TEXT      Specify the project name, default to use current folder
                       name as project name.
  --store-path PATH    Path to load the persisted cookie (default .olauth).
  --hash-path PATH     Path to load the file hashes (default .olhash).
  -i, --olignore PATH  Path to the ignored file list (default .olignore).
  -v, --verbose        Enable extended error logging.
  --version            Show the version and exit.
  --help               Show this message and exit.

Commands:
  list
  login

```

### Login
Log in local Overleaf CE or official overleaf.com.
```
Usage: ols login [OPTIONS]

Options:
  -s, --server_ip IP  Server IP for Overleaf CE. If not provided, default to
                      overleaf.com.
  --path PATH         Path to store the persisted cookie (default to .olauth).
  -v, --verbose       Enable extended error logging.
  --help              Show this message and exit.
```

### Syncing
```
ols --pull
ols --push
```
