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
import logging

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
  ipykernel_group.add_argument('--name', '-n', default='remote_kernel-%(user)s@%(host)s',
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
