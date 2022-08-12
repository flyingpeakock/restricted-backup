#!/usr/bin/env python3

# Restricts rsync to subdirectory declared in .ssh/authorized_keys.  See
# the rrsync man page for details of how to make use of this script.

# NOTE: install python3 braceexpand to support brace expansion in the args!

# Originally a perl script by: Joe Smith <js-cgi@inwap.com> 30-Sep-2004
# Python version by: Wayne Davison <wayne@opencoder.net>
# Edited for extra functionality outside of rsync by Philip Johansson <philipphuket@gmail.com>

# You may configure these 5 values to your liking.  See also the section of
# short & long options if you want to disable any options that rsync accepts.
RSYNC = '/usr/bin/rsync'
LOGFILE = 'rrsync.log' # NOTE: the file must exist for a line to be appended!
DEVICE = '/dev/sda'
DEVICE_MAPPED_NAME = 'cryptbackup'
MOUNT_POINT = '/mnt/backup'
KEEP_SNAPSHOTS = 21

# The following options are mainly the options that a client rsync can send
# to the server, and usually just in the one option format that the stock
# rsync produces. However, there are some additional convenience options
# added as well, and thus a few options are present in both the short and
# long lists (such as --group, --owner, and --perms).

# NOTE when disabling: check for both a short & long version of the option!

### START of options data produced by the cull-options script. ###

# To disable a short-named option, add its letter to this string:
short_disabled = 's'

# These are also disabled when the restricted dir is not "/":
short_disabled_subdir = 'KLk'

# These are all possible short options that we will accept (when not disabled above):
short_no_arg = 'ACDEHIJKLNORSUWXbcdgklmnopqrstuvxyz' # DO NOT REMOVE ANY
short_with_num = '@B' # DO NOT REMOVE ANY

# To disable a long-named option, change its value to a -1.  The values mean:
# 0 = the option has no arg; 1 = the arg doesn't need any checking; 2 = only
# check the arg when receiving; and 3 = always check the arg.
long_opts = {
  'append': 0,
  'backup-dir': 2,
  'block-size': 1,
  'bwlimit': 1,
  'checksum-choice': 1,
  'checksum-seed': 1,
  'compare-dest': 2,
  'compress-choice': 1,
  'compress-level': 1,
  'copy-dest': 2,
  'copy-unsafe-links': 0,
  'daemon': -1,
  'debug': 1,
  'delay-updates': 0,
  'delete': 0,
  'delete-after': 0,
  'delete-before': 0,
  'delete-delay': 0,
  'delete-during': 0,
  'delete-excluded': 0,
  'delete-missing-args': 0,
  'existing': 0,
  'fake-super': 0,
  'files-from': 3,
  'force': 0,
  'from0': 0,
  'fsync': 0,
  'fuzzy': 0,
  'group': 0,
  'groupmap': 1,
  'hard-links': 0,
  'iconv': 1,
  'ignore-errors': 0,
  'ignore-existing': 0,
  'ignore-missing-args': 0,
  'ignore-times': 0,
  'info': 1,
  'inplace': 0,
  'link-dest': 2,
  'links': 0,
  'list-only': 0,
  'log-file': 3,
  'log-format': 1,
  'max-alloc': 1,
  'max-delete': 1,
  'max-size': 1,
  'min-size': 1,
  'mkpath': 0,
  'modify-window': 1,
  'msgs2stderr': 0,
  'munge-links': 0,
  'new-compress': 0,
  'no-W': 0,
  'no-implied-dirs': 0,
  'no-msgs2stderr': 0,
  'no-munge-links': -1,
  'no-r': 0,
  'no-relative': 0,
  'no-specials': 0,
  'numeric-ids': 0,
  'old-compress': 0,
  'one-file-system': 0,
  'only-write-batch': 1,
  'open-noatime': 0,
  'owner': 0,
  'partial': 0,
  'partial-dir': 2,
  'perms': 0,
  'preallocate': 0,
  'recursive': 0,
  'remove-sent-files': 0,
  'remove-source-files': 0,
  'safe-links': 0,
  'sender': 0,
  'server': 0,
  'size-only': 0,
  'skip-compress': 1,
  'specials': 0,
  'stats': 0,
  'stderr': 1,
  'suffix': 1,
  'super': 0,
  'temp-dir': 2,
  'timeout': 1,
  'times': 0,
  'use-qsort': 0,
  'usermap': 1,
  'write-devices': -1,
}

### END of options data produced by the cull-options script. ###

import os, sys, re, argparse, glob, socket, time, subprocess, datetime
from argparse import RawTextHelpFormatter

try:
    from braceexpand import braceexpand
except:
    braceexpand = lambda x: [ DE_BACKSLASH_RE.sub(r'\1', x) ]

HAS_DOT_DOT_RE = re.compile(r'(^|/)\.\.(/|$)')
LONG_OPT_RE = re.compile(r'^--([^=]+)(?:=(.*))?$')
DE_BACKSLASH_RE = re.compile(r'\\(.)')

def main():
    command_full = os.environ.get('SSH_ORIGINAL_COMMAND', None)
    try:
        command_parts = command_full.split(' ')
    except AttributeError:
        die("No command given")
    command = command_parts[0]

    if command == 'open':
        if len(command_parts) != 2:
            die("No hostname supplied, unable to open backup drive")

        decrypt(DEVICE, DEVICE_MAPPED_NAME)
        mount(DEVICE_MAPPED_NAME, MOUNT_POINT)
        lock(command_parts[1], DEVICE_MAPPED_NAME)
        print('Backup drive successfully decrypted and mounted')

    elif command == 'close':
        if len(command_parts) != 2:
            die("No hostname supplied, unable to close backup drive")
        removeLock(command_parts[1], DEVICE_MAPPED_NAME)
        if hasLock(command_parts[1], DEVICE_MAPPED_NAME):
            print("Device is currently in use, not closing")
            return
        
        unmount(MOUNT_POINT, DEVICE_MAPPED_NAME)
        close(DEVICE_MAPPED_NAME)
        print("Backup drive successfully unmounted and encrypted")

    elif command == 'rsync':
        if isMounted(MOUNT_POINT):
            rrsync()
        else:
            die("Backup drive is not mounted")

    elif command == 'snapshot':
        if len(command_parts) != 2:
            die("No hostname supplied, unable to determine files to snapshot")
        createSnapshots(MOUNT_POINT, command_parts[1])
        removeSnapshots(MOUNT_POINT, command_parts[1])

    elif command == 'btrfs':
        try:
            if command_parts[2] == 'parent':
                snapshotParent(MOUNT_POINT, command_parts[1])
                return
            elif command_parts[2] == 'receive':
                snapshotReceive(MOUNT_POINT, command_parts[1], command_parts[3])
                removeSnapshotsBtrfs(MOUNT_POINT, command_parts[1])
            else:
                die("Unknown command")
        except IndexError:
            die("Not enough parameters for btrfs command")

    elif command == 'update':
        try:
            gitdir = command_parts[1]
        except IndexError:
            gitdir = "./restricted-backup"

        if not os.path.isdir(gitdir + '/.git'):
            die("Not a git repository, unable to run git update")

        command = "git pull"
        child = subprocess.run(command.split(' '), cwd=gitdir)

    else:
        die(f'Incorrect command')

def removeSnapshotsBtrfs(device, hostname):
    subvolumes = os.listdir(f'{device}/{hostname}')
    for subv in subvolumes:
        files =  os.listdir(f'{device}/{hostname}/{subv}')
        files_to_remove = files[0:-KEEP_SNAPSHOTS]
        for f in files_to_remove:
            command = f'btrfs subvolume delete {device}/{hostname}/{subv}/{f}'
            child = subprocess.run(command.split(' '))

def snapshotReceive(device, hostname, subvolume):
    print("here")
    if not isMounted(device):
        die('Unable to recieve snapshot, backup drive is not mounted')
    command = f'btrfs receive {device}/{hostname}/{subvolume}'
    child =  subprocess.run(command.split(' '), capture_output=True)
    print(child.stderr)
    if child.returncode != 0:
        return child.returncode
    return 0

def snapshotParent(device, hostname):
    if not isMounted(device):
        die('Unable to get parent, backup drive is not mounted')
    files = os.listdir(f'{device}/{hostname}/root/')
    parent = files[-1]
    print(parent)

def removeSnapshots(device, hostname):
    if not isMounted(device):
        die('Unable to create snapshots, backup drive is not mounted')
    
    subvolumes = ['root', 'home']
    for subvolume in subvolumes:
        files = os.listdir(f'{device}/snapshots/{hostname}/{subvolume}')
        files_to_remove = files[0:-KEEP_SNAPSHOTS]
        for file in files_to_remove:
            command = f'btrfs subvolume delete {device}/snapshots/{hostname}/{subvolume}/{file}'
            child = subprocess.run(command.split(' '))

def createSnapshots(device, hostname):
    if not isMounted(device):
        die('Unable to create snapshots, backup drive is not mounted')

    date = datetime.date.today().isoformat
    snapshots_root = f'{device}/snapshots/{hostname}'
    if os.path.exists(f'{snapshots_root}/root/{date}'):
        print("A snapshot already exists for today")
        return 0 # Already exists for today, not  creating another one

    snapshot_destinations = [ f'{snapshots_root}/root/{date}', f'{snapshots_root}/home/{date}' ]
    snapshot_sources = [ f'{device}/{hostname}', f'{device}/{hostname}/home' ]
    snapshots = zip(snapshot_sources, snapshot_destinations)
    
    results = []
    for snapshot in snapshots:
        command = f'btrfs subvolume snapshot -r {snapshot[0]} {snapshot[1]}'
        child = subprocess.run(command.split(' '))
        results.append(child.returncode)
    for res in results:
        if res != 0:
            die("Unable to create snapshots")
    return 0

def close(device):
    command = f'cryptsetup close /dev/mapper/{device}'
    child = subprocess.run(command.split(' '))
    if isOpen(f'/dev/mapper/{device}'):
        die("Unable to decrypt backup drive")
    if child.returncode != 0:
        return child.returncode
    return 0

def unmount(device, mapped):
    command = f'umount {device}'
    child = subprocess.run(command.split(' '))
    if isMounted(device):
        die("Unable to unmount backup drive")
    if child.returncode != 0:
        return child.returncode
    return 0

def removeLock(name, device):
    dir = os.path.dirname(os.path.realpath(__file__))
    try:
        os.remove(f"{dir}/{name}-{device}.lock")
    except FileNotFoundError:
        print('Lock file not found, something went wrong.')

def hasLock(name, device):
    dir = os.path.dirname(os.path.realpath(__file__))
    lock_files = [f for f in os.listdir(dir) if f.endswith(f'{device}.lock') and not f.startswith(name)]
    return len(lock_files) != 0

def lock(name, device):
    dir = os.path.dirname(os.path.realpath(__file__))
    file_name = f'{dir}/{name}-{device}.lock'
    fp = open(file_name, 'w')
    fp.close()

def isOpen(path):
    return os.path.exists(path)

def decrypt(dev, mapped):
    if isOpen(f'/dev/mapper/{mapped}'):
        return 0
    cmd = f'nice -n 10 cryptsetup open {dev} {mapped} --key-file=-'
    child = subprocess.run(cmd.split(' '))
    if not isOpen(f'/dev/mapper/{mapped}'):
        die("Unable to decrypt backup drive")
    if child.returncode != 0:
        return child.returncode
    return 0

def isMounted(mount):
    return os.path.ismount(mount)

def mount(device, mount):
    if isMounted(mount):
        return 0
    if not isOpen(f'/dev/mapper/{device}'):
        die("Backup drive is not decrypted")

    cmd = f'mount -o compress=lzo /dev/mapper/{device} {mount}'
    child = subprocess.run(cmd.split(' '))
    if not isMounted(mount):
        close(device)
        die('Unable to mount backup drive, it has been reencrypted')
    if child.returncode != 0:
        return child.returncode
    return 0

def rrsync():
    if not os.path.isdir(args.dir):
        die("Restricted directory does not exist!")

    # The format of the environment variables set by sshd:
    #   SSH_ORIGINAL_COMMAND:
    #     rsync --server          -vlogDtpre.iLsfxCIvu --etc . ARG  # push
    #     rsync --server --sender -vlogDtpre.iLsfxCIvu --etc . ARGS # pull
    #   SSH_CONNECTION (client_ip client_port server_ip server_port):
    #     192.168.1.100 64106 192.168.1.2 22

    command = os.environ.get('SSH_ORIGINAL_COMMAND', None)
    if not command:
        die("Not invoked via sshd")
    command = command.split(' ', 2)
    if command[0:1] != ['rsync']:
        die("SSH_ORIGINAL_COMMAND does not run rsync")
    if command[1:2] != ['--server']:
        die("--server option is not the first arg")
    command = '' if len(command) < 3 else command[2]

    global am_sender
    am_sender = command.startswith("--sender ") # Restrictive on purpose!
    if args.ro and not am_sender:
        die("sending to read-only server is not allowed")
    if args.wo and am_sender:
        die("reading from write-only server is not allowed")

    if args.wo or not am_sender:
        long_opts['sender'] = -1
    if args.no_del:
        for opt in long_opts:
            if opt.startswith(('remove', 'delete')):
                long_opts[opt] = -1
    if args.ro:
        long_opts['log-file'] = -1

    if args.dir != '/':
        global short_disabled
        short_disabled += short_disabled_subdir

    short_no_arg_re = short_no_arg
    short_with_num_re = short_with_num
    if short_disabled:
        for ltr in short_disabled:
            short_no_arg_re = short_no_arg_re.replace(ltr, '')
            short_with_num_re = short_with_num_re.replace(ltr, '')
        short_disabled_re = re.compile(r'^-[%s]*([%s])' % (short_no_arg_re, short_disabled))
    short_no_arg_re = re.compile(r'^-(?=.)[%s]*(e\d*\.\w*)?$' % short_no_arg_re)
    short_with_num_re = re.compile(r'^-[%s]\d+$' % short_with_num_re)

    log_fh = open(LOGFILE, 'a') if os.path.isfile(LOGFILE) else None

    try:
        os.chdir(args.dir)
    except OSError as e:
        die('unable to chdir to restricted dir:', str(e))

    rsync_opts = [ '--server' ]
    rsync_args = [ ]
    saw_the_dot_arg = False
    last_opt = check_type = None

    for arg in re.findall(r'(?:[^\s\\]+|\\.[^\s\\]*)+', command):
        if check_type:
            rsync_opts.append(validated_arg(last_opt, arg, check_type))
            check_type = None
        elif saw_the_dot_arg:
            # NOTE: an arg that starts with a '-' is safe due to our use of "--" in the cmd tuple.
            try:
                b_e = braceexpand(arg) # Also removes backslashes
            except: # Handle errors such as unbalanced braces by just de-backslashing the arg:
                b_e = [ DE_BACKSLASH_RE.sub(r'\1', arg) ]
            for xarg in b_e:
                rsync_args += validated_arg('arg', xarg, wild=True)
        else: # parsing the option args
            if arg == '.':
                saw_the_dot_arg = True
                continue
            rsync_opts.append(arg)
            if short_no_arg_re.match(arg) or short_with_num_re.match(arg):
                continue
            disabled = False
            m = LONG_OPT_RE.match(arg)
            if m:
                opt = m.group(1)
                opt_arg = m.group(2)
                ct = long_opts.get(opt, None)
                if ct is None:
                    break # Generate generic failure due to unfinished arg parsing
                if ct == 0:
                    continue
                opt = '--' + opt
                if ct > 0:
                    if opt_arg is not None:
                        rsync_opts[-1] = opt + '=' + validated_arg(opt, opt_arg, ct)
                    else:
                        check_type = ct
                        last_opt = opt
                    continue
                disabled = True
            elif short_disabled:
                m = short_disabled_re.match(arg)
                if m:
                    disabled = True
                    opt = '-' + m.group(1)

            if disabled:
                die("option", opt, "has been disabled on this server.")
            break # Generate a generic failure

    if not saw_the_dot_arg:
        die("invalid rsync-command syntax or options")

    if args.munge:
        rsync_opts.append('--munge-links')

    if not rsync_args:
        rsync_args = [ '.' ]

    cmd = (RSYNC, *rsync_opts, '--', '.', *rsync_args)

    if log_fh:
        now = time.localtime()
        host = os.environ.get('SSH_CONNECTION', 'unknown').split()[0] # Drop everything after the IP addr
        if host.startswith('::ffff:'):
            host = host[7:]
        try:
            host = socket.gethostbyaddr(socket.inet_aton(host))
        except:
            pass
        log_fh.write("%02d:%02d:%02d %-16s %s\n" % (now.tm_hour, now.tm_min, now.tm_sec, host, str(cmd)))
        log_fh.close()

    # NOTE: This assumes that the rsync protocol will not be maliciously hijacked.
    if args.no_lock:
        os.execlp(RSYNC, *cmd)
        die("execlp(", RSYNC, *cmd, ')  failed')
    child = subprocess.run(cmd)
    if child.returncode != 0:
        sys.exit(child.returncode)


def validated_arg(opt, arg, typ=3, wild=False):
    if opt != 'arg': # arg values already have their backslashes removed.
        arg = DE_BACKSLASH_RE.sub(r'\1', arg)

    orig_arg = arg
    if arg.startswith('./'):
        arg = arg[1:]
    arg = arg.replace('//', '/')
    if args.dir != '/':
        if HAS_DOT_DOT_RE.search(arg):
            die("do not use .. in", opt, "(anchor the path at the root of your restricted dir)")
        if arg.startswith('/'):
            arg = args.dir + arg

    if wild:
        got = glob.glob(arg)
        if not got:
            got = [ arg ]
    else:
        got = [ arg ]

    ret = [ ]
    for arg in got:
        if args.dir != '/' and arg != '.' and (typ == 3 or (typ == 2 and not am_sender)):
            arg_has_trailing_slash = arg.endswith('/')
            if arg_has_trailing_slash:
                arg = arg[:-1]
            else:
                arg_has_trailing_slash_dot = arg.endswith('/.')
                if arg_has_trailing_slash_dot:
                    arg = arg[:-2]
            real_arg = os.path.realpath(arg)
            if arg != real_arg and not real_arg.startswith(args.dir_slash):
                die('unsafe arg:', orig_arg, [arg, real_arg])
            if arg_has_trailing_slash:
                arg += '/'
            elif arg_has_trailing_slash_dot:
                arg += '/.'
            if opt == 'arg' and arg.startswith(args.dir_slash):
                arg = arg[args.dir_slash_len:]
                if arg == '':
                    arg = '.'
        ret.append(arg)

    return ret if wild else ret[0]


def lock_or_die(dirname):
    import fcntl
    global lock_handle
    lock_handle = os.open(dirname, os.O_RDONLY)
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except:
        die('Another instance of rrsync is already accessing this directory.')


def die(*msg):
    print(sys.argv[0], 'error:', *msg, file=sys.stderr)
    if sys.stdin.isatty():
        arg_parser.print_help(sys.stderr)
    sys.exit(1)


# This class displays the --help to the user on argparse error IFF they're running it interactively.
class OurArgParser(argparse.ArgumentParser):
    def error(self, msg):
        die(msg)


if __name__ == '__main__':
    our_desc = """Use "man rrsync" to learn how to restrict ssh users to using a restricted rsync command."""
    arg_parser = OurArgParser(description=our_desc, add_help=False)
    only_group = arg_parser.add_mutually_exclusive_group()
    only_group.add_argument('-ro', action='store_true', help="Allow only reading from the DIR. Implies -no-del and -no-lock.")
    only_group.add_argument('-wo', action='store_true', help="Allow only writing to the DIR.")
    arg_parser.add_argument('-munge', action='store_true', help="Enable rsync's --munge-links on the server side.")
    arg_parser.add_argument('-no-del', action='store_true', help="Disable rsync's --delete* and --remove* options.")
    arg_parser.add_argument('-no-lock', action='store_true', help="Avoid the single-run (per-user) lock check.")
    arg_parser.add_argument('-help', '-h', action='help', help="Output this help message and exit.")
    arg_parser.add_argument('dir', metavar='DIR', help="The restricted directory to use.")
    args = arg_parser.parse_args()
    args.dir = os.path.realpath(args.dir)
    args.dir_slash = args.dir + '/'
    args.dir_slash_len = len(args.dir_slash)
    if args.ro:
        args.no_del = True
    elif not args.no_lock:
        lock_or_die(args.dir)
    main()

