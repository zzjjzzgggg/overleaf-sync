import fnmatch
import glob
import io
import json
import os
import pickle
import traceback
import zipfile
from pathlib import Path
import time
import hashlib

import click
import dateutil.parser
from yaspin import yaspin


@click.group(invoke_without_command=True)
@click.option('--push', 'push', is_flag=True, help="Push local files to remote.")
@click.option('--pull', 'pull', is_flag=True, help="Pull remote files to local.")
@click.option(
    '-n',
    '--name',
    'project_name',
    default="",
    help=
    "Specify the project name, default to use current folder name as project name."
)
@click.option('--store-path',
              'cookie_path',
              default=".olauth",
              type=click.Path(exists=False),
              help="Path to load the persisted cookie (default .olauth).")
@click.option('--hash-path',
              'hash_path',
              default=".olhash",
              type=click.Path(exists=False),
              help="Path to load the file hashes (default .olhash).")
@click.option('-i',
              '--olignore',
              'olignore_path',
              default=".olignore",
              type=click.Path(exists=False),
              help="Path to the ignored file list (default .olignore).")
@click.option('-v',
              '--verbose',
              'verbose',
              is_flag=True,
              help="Enable extended error logging.")
@click.version_option(package_name='overleaf-sync')
@click.pass_context
def main(ctx, push, pull, project_name, cookie_path, hash_path, olignore_path,
         verbose):
    tm_tick = time.time()
    if ctx.invoked_subcommand is not None: return

    # try to find the root dir of the project
    for _ in range(5):
        if not os.path.isfile(cookie_path):
            os.chdir('..')
            print("Switch to directory", os.getcwd())
        else:
            break

    if not os.path.isfile(cookie_path):
        raise click.ClickException("Cookie not found. Please login.")

    with open(cookie_path, 'rb') as f:
        store = pickle.load(f)

    client = get_client(store)

    if project_name: update_info(project=project_name)
    else:
        project_name = get_key("project")
        if not project_name:
            project_name = os.path.basename(os.getcwd())
            update_info(project=project_name)
    print("Using project name:", project_name)

    project = execute_action(lambda: client.get_project(project_name),
                             "Querying project", "Project queried successfully.",
                             "Project could not be queried.", verbose)

    if project is None: return
    remote_timestamp = dateutil.parser.isoparse(
        project["lastUpdated"]).timestamp()

    project_info = execute_action(lambda: client.get_project_infos(project["id"]),
                                  "Querying project details",
                                  "Project details queried successfully.",
                                  "Project details could not be queried.",
                                  verbose)

    zip_file = execute_action(
        lambda: zipfile.ZipFile(io.BytesIO(client.download_project(project[
            "id"]))), "Downloading project", "Project downloaded successfully.",
        "Project could not be downloaded.", verbose)

    if zip_file is None: return

    if os.path.isfile(hash_path):
        with open(hash_path, 'rb') as f:
            hash_table = pickle.load(f)
    else:
        hash_table = {}

    remote_files = set(name for name in zip_file.namelist())
    local_files = olignore_keep_list(olignore_path)

    sync = not (pull or push)

    if pull or sync:
        # some remote files may be updated or not, decide by hash
        local_to_update = []
        for file_name in remote_files & local_files:
            pre_remote_hash = hash_table[file_name][
                0] if file_name in hash_table else None
            remote_hash = hashlib.sha1(zip_file.read(file_name)).hexdigest()
            local_hash = hashlib.sha1(open(file_name, 'rb').read()).hexdigest()
            local_timestamp = os.path.getmtime(file_name)
            if pre_remote_hash != remote_hash:  # remote update
                local_to_update.append(
                    (file_name, remote_hash, local_timestamp - remote_timestamp))

        sync_func(files_to_add=remote_files - local_files,
                  files_to_update=local_to_update,
                  files_to_delete=local_files - remote_files,
                  create_file_at_target=lambda name: write_file(
                      name, zip_file.read(name)),
                  delete_file_at_target=lambda name: delete_file(name),
                  create_file_at_source=lambda name: client.upload_file(
                      project["id"], project_info, name, open(name, 'rb')),
                  hash_table=hash_table,
                  source="remote",
                  target="local",
                  verbose=verbose)

    if push or sync:
        # TODO: remote delete some files, avoid re-creating these files when pushing
        # some local files may be updated or not, decide by mtime
        remote_to_update = []
        for file_name in remote_files & local_files:
            pre_local_timestamp = hash_table[file_name][
                1] if file_name in hash_table else 0
            local_timestamp = os.path.getmtime(file_name)
            remote_hash = hashlib.sha1(zip_file.read(file_name)).hexdigest()
            local_hash = hashlib.sha1(open(file_name, 'rb').read()).hexdigest()
            if pre_local_timestamp < local_timestamp:  # local update
                remote_to_update.append(
                    (file_name, local_hash, remote_timestamp - local_timestamp))

        sync_func(files_to_add=local_files - remote_files,
                  files_to_update=remote_to_update,
                  files_to_delete=remote_files - local_files,
                  create_file_at_target=lambda name: client.upload_file(
                      project["id"], project_info, name, open(name, 'rb')),
                  delete_file_at_target=lambda name: client.delete_file(
                      project["id"], project_info, name),
                  create_file_at_source=lambda name: write_file(
                      name, zip_file.read(name)),
                  hash_table=hash_table,
                  source="local",
                  target="remote",
                  verbose=verbose)

    # save hash table
    with open(hash_path, 'wb') as f:
        pickle.dump(hash_table, f)

    tm_cost = time.time() - tm_tick
    print("\nCost time {:.2f} seconds.".format(tm_cost))


@main.command(name='login')
@click.option(
    '-s',
    '--server_ip',
    default=None,
    help="Server IP for Overleaf CE. If not provided, default to overleaf.com.")
@click.option('--path',
              'cookie_path',
              default=".olauth",
              type=click.Path(exists=False),
              help="Path to store the persisted cookie (default to .olauth).")
@click.option('-v',
              '--verbose',
              'verbose',
              is_flag=True,
              help="Enable extended error logging.")
def login(server_ip, cookie_path, verbose):
    update_info(server=server_ip)
    if os.path.isfile(cookie_path) and not click.confirm(
            'Cookie already exist. Do you want to override it?'):
        return
    click.clear()
    execute_action(
        lambda: login_handler(server_ip, cookie_path), "Login",
        "Login successful. Cookie persisted as `" +
        click.format_filename(cookie_path) + "`. You may now sync your project.",
        "Login failed. Please try again.", verbose)


@main.command(name='list')
@click.option('--store-path',
              'cookie_path',
              default=".olauth",
              type=click.Path(exists=False),
              help="Path to load the persisted cookie (default .olauth).")
@click.option('-v',
              '--verbose',
              'verbose',
              is_flag=True,
              help="Enable extended error logging.")
def list_projects(cookie_path, verbose):

    def query_projects():
        for index, p in enumerate(
                sorted(client.all_projects(),
                       key=lambda x: x['lastUpdated'],
                       reverse=True)):
            if not index:
                click.echo("\n")
            click.echo(
                f"{dateutil.parser.isoparse(p['lastUpdated']).strftime('%m/%d/%Y, %H:%M:%S')} - {p['name']}"
            )
        return True

    if not os.path.isfile(cookie_path):
        raise click.ClickException(
            "Persisted Overleaf cookie not found. Please login or check store path."
        )

    with open(cookie_path, 'rb') as f:
        store = pickle.load(f)

    client = get_client(store)

    click.clear()
    execute_action(query_projects, "Querying all projects",
                   "Querying all projects successful.",
                   "Querying all projects failed. Please try again.", verbose)


def login_handler(server, path):
    if server is None:  # overleaf
        import olbrowserlogin as olbrowserlogin
        store = olbrowserlogin.login()
    else:  # overleaf CE
        import olcebrowserlogin as olbrowserlogin
        store = olbrowserlogin.login(server)

    if store is None: return False

    with open(path, 'wb+') as f:
        pickle.dump(store, f)
    return True


def delete_file(path):
    _dir = os.path.dirname(path)
    if _dir == path: return

    if _dir != '' and not os.path.exists(_dir): return
    else: os.remove(path)


def write_file(path, content):
    _dir = os.path.dirname(path)
    if _dir == path: return

    # path is a file
    if _dir != '' and not os.path.exists(_dir):
        os.makedirs(_dir)

    with open(path, 'wb+') as f:
        f.write(content)


def sync_func(files_to_add, files_to_update, files_to_delete,
              create_file_at_target, delete_file_at_target, create_file_at_source,
              hash_table, source, target, verbose):
    update_list = []
    not_sync_list = []
    for name, source_hash, dt, in files_to_update:
        if dt > 0 and not click.confirm(
                "\n[Warning]: Your {} file <{}> is likely {:.1f} seconds newer than {}."
                "\nContinue to overwrite with probabily an old version?"
                "\nNote that remote file update time is actually the remote project update time which may be incorrect."
                .format(target, name, dt, source)):
            not_sync_list.append(name)
        else:
            update_list.append((name, source_hash))

    delete_list = []
    restore_list = []
    not_restored_list = []
    for name in files_to_delete:
        delete_choice = click.prompt(
            "\n[Warning]: file {} does not exist on {} anymore (but still exists on {})."
            "\nShould the file be [d]eleted, [r]estored or [i]gnored?".format(
                name, source, target),
            default="i",
            type=click.Choice(['d', 'r', 'i']))
        if delete_choice == "d":
            delete_list.append(name)
        elif delete_choice == "r":
            restore_list.append(name)
        elif delete_choice == "i":
            not_restored_list.append(name)

    if files_to_add:
        click.echo("\n[NEW] Following new files created on {}:".format(target))
    for name in files_to_add:
        click.echo("\t%s" % name)
        try:
            create_file_at_target(name)
            hash_table[name] = [
                hashlib.sha1(open(name, 'rb').read()).hexdigest(),
                os.path.getmtime(name)
            ]
        except:
            if verbose: print(traceback.format_exc())
            raise click.ClickException(
                "\n[ERROR] An error occurred while creating new files on {}".
                format(target))

    if update_list:
        click.echo("\n[NEW] Following files updated on {}:".format(target))
    for name, hash in update_list:
        click.echo("\t%s" % name)
        try:
            create_file_at_target(name)
            hash_table[name] = [hash, os.path.getmtime(name)]
        except:
            if verbose: print(traceback.format_exc())
            raise click.ClickException(
                "\n[ERROR] An error occurred while creating new files on {}".
                format(target))

    if delete_list:
        click.echo("\n[DELETE] Following files deleted on {}:".format(target))
    for name in delete_list:
        click.echo("\t%s" % name)
        try:
            delete_file_at_target(name)
            if name in hash_table: del hash_table[name]
        except:
            if verbose: print(traceback.format_exc())
            raise click.ClickException(
                "\n[ERROR] An error occurred while delete file on {}".format(
                    target))

    if restore_list:
        click.echo("\n[NEW] Following new files restored on {}:".format(source))
    for name in restore_list:
        click.echo("\t%s" % name)
        try:
            create_file_at_source(name)
            hash_table[name] = [
                hashlib.sha1(open(name, 'rb').read()).hexdigest(),
                os.path.getmtime(name)
            ]
        except:
            if verbose: print(traceback.format_exc())
            raise click.ClickException(
                "\n[ERROR] An error occurred while creating new files on [%s]" %
                source)

    if not_sync_list:
        click.echo(
            "\n[SKIP] Following files on {} have not been synced to {}".format(
                source, target))
    for name in not_sync_list:
        click.echo("\t%s" % name)

    if not_restored_list:
        click.echo(
            "\n[SKIP] Following files on {} have not been synced to {}".format(
                target, source))
    for name in not_restored_list:
        click.echo("\t%s" % name)

    click.echo("")
    click.echo("✅  Synced files from [%s] to [%s]" % (source, target))
    click.echo("")


def execute_action(action,
                   progress_message,
                   success_message,
                   fail_message,
                   verbose_error_logging=False,
                   tries=3):
    rst = None
    success = False
    num_try = 0
    with yaspin(text=progress_message, color="green") as spinner:
        while not success and num_try < tries:
            try:
                rst = action()
                success = True
            except:
                if verbose_error_logging:
                    print(traceback.format_exc())
                num_try += 1
                print("\nFailed, will try again ({}/{})".format(num_try, tries))

        if success:
            spinner.write(success_message)
            spinner.ok("✅ ")
        else:
            spinner.fail("💥 ")
            raise click.ClickException(fail_message)
    return rst


def olignore_keep_list(olignore_path):
    """
    The list of files to keep synced, with support for sub-folders.
    Should only be called when syncing from local to remote.
    """
    # get list of files recursively (ignore .* files)
    files = glob.glob('**', recursive=True)

    if not os.path.isfile(olignore_path): keep_list = files
    else:
        with open(olignore_path, 'r') as f:
            ignore_pattern = f.read().splitlines()

        keep_list = [
            f for f in files
            if not any(fnmatch.fnmatch(f, ignore) for ignore in ignore_pattern)
        ]

    keep_list = set(
        Path(item).as_posix() for item in keep_list if not os.path.isdir(item))
    return keep_list


def read_info():
    info = {}
    if os.path.isfile(".olinfo"):
        with open(".olinfo", 'r') as f:
            info = json.load(f)
    return info


def update_info(**args):
    info = read_info()
    for k in args:
        info[k] = args[k]
    with open(".olinfo", "w") as fw:
        json.dump(info, fw)


def get_key(key):
    info = read_info()
    return info[key] if key in info else None


def get_client(store):
    client = None
    server = get_key('server')
    if server is None:  # overleaf
        from olclient import OverleafClient
        client = OverleafClient(store["cookie"], store["csrf"])
    else:  # overleaf CE
        from olceclient import OverleafClient
        client = OverleafClient(server, store["cookie"], store["csrf"])
    return client


if __name__ == "__main__":
    main()
