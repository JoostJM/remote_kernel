"""


Connection config:

Key                   Cmd Arg
ip                    --ip
stdin_port            --stdin
shell_port            --shell
iopub_port            --iopub
hb_port               --hb
control_port          --control
signature_scheme      --Session.signature_scheme    must have the form hmac-HASH
key                   --Session.key                 b''
kernel_name           --
transport             --transport  ['tcp', 'icp']
"""

import argparse
from collections import OrderedDict
import json
import logging
import os

logger = logging.getLogger('remote_kernel')
logger.propagate = False
hndlr = logging.StreamHandler()
hndlr.setFormatter(logging.Formatter('%(name)s %(levelname)-.1s: %(message)s'))

logger.addHandler(hndlr)
logger.setLevel(logging.INFO)
hndlr.setLevel(logging.INFO)


def get_resource_dir():
  import os
  resource_dir = os.path.join(os.path.dirname(__file__), 'resources')
  return os.path.abspath(resource_dir)


def get_parser(connection_file_arg=True):
  parser = argparse.ArgumentParser(fromfile_prefix_chars='@')

  ssh_group = parser.add_argument_group(title='SSH Connection', description="Arguments specifying the SSH connection "
                                                                            "to the remote server")
  ssh_group.add_argument('--target', '-t', metavar='[username@]host[:port]', required=True,
                         help='Remote server to connect to. Formatted as [username@]host[:port]')
  ssh_group.add_argument('-J', dest='jump_server', metavar='[username@]host[:port]', default=None, action='append',
                         help='Optional jump servers to connect through to the host')
  ssh_group.add_argument('-i', dest='ssh_key', default=None, help='ssh key to use for authentication')

  ipykernel_group = parser.add_argument_group(title='IPyKernel Arguments', description="Arguments to start the "
                                                                                       "ipykernel on the remote server")
  ipykernel_group.add_argument('--kernel', '-k', default='python -m ipykernel',
                               help='Kernel start command, default is "ipykernel"')
  ipykernel_group.add_argument('--pre-command', '-pc', default=None,
                               help='Additional commands to execute on remote server, prior to '
                                    'starting the kernel (specified in `--kernel`)')
  ipykernel_group.add_argument('--name', '-n', dest='kernel_name', default='remote_kernel-%(user)s@%(host)s',
                               help='Display name of the kernel to install\n'
                                    'Default: remote_kernel-<user>@<host>')
  if connection_file_arg:
    ipykernel_group.add_argument('--file', '-f', help='Connection file to configure the kernel')

  ipykernel_group.add_argument('--no-remote-files', action='store_true',
                               help='If specified, no remote files are created/removed on the remote host.\n'
                                    'Connection arguments are passed via commandline.\n'
                                    'N.B. This is less secure, as these arguments are visible in the processes list!')

  sync_group = parser.add_argument_group(title='Remote file sync options',
                                         description='Arguments controlling synchronization of remote files')
  sync_group.add_argument('--synchronize', '-s', action='store_true', help='If specified, synchronizes files')
  sync_group.add_argument('--no-recursive', '-nr', action='store_false', dest='recursive',
                          help='If specified, skips synchronizing files in the sub-folders of the sync folder')
  sync_group.add_argument('--bi-directional', '-bd', action='store_true',
                          help='If specified, synchronizes from remote to local and from local to remote')
  sync_group.add_argument('--remote-folder', '-rf', default='remote_kernel_sync',
                          help='Remote root folder to sync (containing sub-folders for each unique local folder')
  sync_group.add_argument('--local-folder', '-lf', default='remote_kernel_sync',
                          help='Name of local sub-folder to synchronize')
  return parser


def get_spec(argv=None):
  global logger
  from jupyter_core.paths import jupyter_path

  spec_parser = argparse.ArgumentParser()
  spec_parser.add_argument('kernel_name', help='Name of jupyter registered kernel to start (folder name)')
  spec_args = spec_parser.parse_args(argv)

  kernel_name = spec_args.kernel_name

  if os.path.isabs(kernel_name):
    kernel_spec = kernel_name
  else:
    kernel_spec = None
    for d in ['.'] + jupyter_path('kernels'):
      logger.debug('Searching in directory %s', d)
      if os.path.isfile(os.path.join(d, kernel_name, 'kernel.json')):
        kernel_spec = os.path.join(d, kernel_name, 'kernel.json')
        break

    assert kernel_spec is not None, \
        'Kernel specification file %s not found!' % kernel_name

  logger.info('Loading kernel specification file %s', kernel_spec)

  with open(kernel_spec, mode='r') as spec_fs:
    spec = json.load(spec_fs)

  # Ensure specification is the correct version
  spec = _check_spec(kernel_spec, spec)

  args = spec['argv']

  assert args[1:3] == ['-m', 'remote_kernel'], \
      'Kernel spec %s is not a remote_kernel specification' % kernel_spec

  # Remove the jupyter supplied connection_file specification
  if '-f' in args and args[args.index('-f') + 1] == '{connection_file}':
    idx = args.index('-f')
    del args[idx: idx+2]
  elif '-f={connection_file}' in args:
    del args[args.index('-f={connection_file}')]

  return args[3:]


def _check_spec(kernel_spec, spec):
  """
  Check if the deprecated "command" argument is present,
  represents the first version of remote_kernel definition
  If so, update to new-style kernel definition and re-save kernel spec
  :param kernel_spec: File name where the kernel specification is stored
  :param spec: JSON kernel specification to check and update if necessary
  :return: Kernel specification, updated to new version if necessary.
  """
  global logger

  args = spec['argv']
  cmd = None
  pre_args = None
  post_args = None
  if '--command' in args:
    cmd_idx = args.index('--command')
    cmd = args[cmd_idx + 1]
    pre_args = args[:cmd_idx]
    post_args = args[cmd_idx + 2:]
  elif '-c' in args:
    cmd_idx = args.index('-c')
    cmd = args[cmd_idx + 1]
    pre_args = args[:cmd_idx]
    post_args = args[cmd_idx + 2:]
  else:
    for a_idx, a in enumerate(args):
      if a.startswith('-c='):
        cmd = a[3:]
        pre_args = args[:a_idx]
        post_args = args[a_idx + 1:]
        break
      elif a.startswith('--command='):
        cmd = a[10:]
        pre_args = args[:a_idx]
        post_args = args[a_idx + 1:]
        break

  if cmd is not None:
    cmds = cmd.split(' && ')
    kernel_args = []
    if len(cmds) > 1:
      kernel_args += ['-pc', ' && '.join(cmds[:-1])]
    if cmds[-1] != 'python -m ipykernel':
      kernel_args += ['-k', cmds[-1]]

    logger.warning('Deprecated version of kernel specification detected! Updating to new format...')
    logger.debug('Normalizing command "%s" to %s', cmd, kernel_args)

    spec['argv'] = pre_args + kernel_args + post_args

    with open(kernel_spec, mode='w') as spec_fs:
      json.dump(spec, spec_fs, indent=2)
  return spec


# argument template for starting up an IPyKernel without supplying a connection file
# arguments to fill this template are read from the connection file which remains on
# the local computer. It only ignores the kernel_name argument from the connection file.
CMD_ARGS = OrderedDict([
  ('--ip', '"%(ip)s"'),
  ('--stdin', '%(stdin_port)i'),
  ('--shell', '%(shell_port)i'),
  ('--iopub', '%(iopub_port)i'),
  ('--hb', '%(hb_port)i'),
  ('--control', '%(control_port)i'),
  ('--Session.signature_scheme', '"%(signature_scheme)s"'),
  ('--Session.key', '"b\'%(key)s\'"'),  # Py3 compat, ensure the key is interpreted as a byte string
  ('--transport', '"%(transport)s"')
])

from ._version import get_versions  # noqa: I202
__version__ = get_versions()['version']
del get_versions
