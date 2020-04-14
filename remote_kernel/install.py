import argparse
import json
import logging
import os
import shutil
import sys

from jupyter_core.paths import jupyter_data_dir
import paramiko

from . import CMD_ARGS, get_resource_dir
from .ssh_client import ParamikoClient


logger = logging.getLogger('remote_kernel.install')


def parse_args(argv=None):
  parser = argparse.ArgumentParser()
  parser.add_argument('--target', '-t', metavar='[username@]host[:port]', required=True,
                      help='Remote server to connect to. Formatted as [username@]host[:port]')
  parser.add_argument('-J', dest='jump_server', metavar='[username@]host[:port]', default=None, action='append',
                      help='Optional jump servers to connect through to the host')
  parser.add_argument('-i', dest='ssh_key', default=None, help='ssh key to use for authentication')
  parser.add_argument('--kernel', '-k', default='python -m ipykernel',
                      help='Kernel start command, default is "ipykernel"')
  parser.add_argument('--command', '-c', default=None,
                      help='Additional commands to execute on remote server, prior to '
                           'starting the kernel (specified in `--kernel`)')
  parser.add_argument('--name', '-n', default='remote_kernel-%(user)s@%(host)s',
                      help='Display name of the kernel to install\n'
                           'Default: remote_kernel-<user>@<host>')
  parser.add_argument('--no-remote-files', action='store_true',
                      help='If specified, no remote files are created/removed on the remote host.\n'
                           'Connection arguments are passed via commandline.\n'
                           'N.B. This is less secure, as these arguments are visible in the processes list!')
  parser.add_argument('--skip-kernel-test', action='store_true',
                      help='If specified, the kernel starting command is not tested.\n'
                           'This can be useful for starting kernels that do not expose\n'
                           'the --help-all commandline option')
  parser.add_argument('--dry-run', action='store_true',
                      help='If specified, test settings without writing kernel specs.')

  args = parser.parse_args(argv)

  arg_dict = args.__dict__.copy()
  kernel_name = arg_dict.pop('name')
  ssh_host = arg_dict.pop('target')

  return install_kernel(kernel_name, ssh_host, **arg_dict)


def install_kernel(kernel_name, ssh_host, **kwargs):
  global logger

  ssh_key = kwargs.get('ssh_key', None)
  jump_server = kwargs.get('jump_server', None)

  pre_command = kwargs.get('command', None)
  kernel_cmd = kwargs.get('kernel', 'python -m ipykernel')
  dry_run = kwargs.get('dry_run', False)
  skip_kernel_test = kwargs.get('skip_kernel_test', False)
  no_remote_files = kwargs.get('no_remote_files', False)

  clients = []
  try:
    # Connect via jump server(s) if specified
    for srvr in jump_server:
      client = ParamikoClient()
      client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
      logger.debug('Connecting to jump server %s@%s:%i', client.username, client.host, client.port)
      client.connect_override(srvr, ssh_key, clients[-1] if len(clients) > 0 else None)
      clients.append(client)
    ssh_client = ParamikoClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    logger.debug('Connecting to remote server %s@%s:%i', ssh_client.username, ssh_client.host, ssh_client.port)
    ssh_client.connect_override(ssh_host, ssh_key, clients[-1] if len(clients) > 0 else None)
    clients.append(ssh_client)

    logger.info('Connection to remote server successfull!')

    chan = ssh_client.get_transport().open_session()
    chan.get_pty()
    cmds = []
    if pre_command is not None:
      cmds.append(pre_command)
    if not skip_kernel_test:
      cmds.append('%s --help-all' % kernel_cmd)

    cmd = ' && '.join(cmds)

    logger.debug('Running cmd %s', cmd)
    chan.exec_command(cmd)
    result = chan.recv_exit_status()

    output = ''
    data = chan.recv(4096)
    while data:
      output += data.decode('utf-8')
      logger.debug("REMOTE >>> " + data.decode('utf-8'))
      data = chan.recv(4096)

    if result != 0:
      logger.error('CMD %s returned a non-zero exit status on remote server.\n\n%s', cmd, output)
      return 1
    elif not skip_kernel_test:
      for cmd in CMD_ARGS.keys():
        if '\n' + cmd not in output:
          logger.error('Help message does not specify required argument %s', cmd)
          return 1

    if dry_run:
      logger.info('Test passed, returning without writing kernel specs.')
      return 0

    logger.info('Command successful, writing kernel_spec file')
    name_spec = dict(
      user=ssh_client.username,
      host=ssh_client.host,
      port=ssh_client.port
    )
    kernel_name = kernel_name % name_spec
    safe_name = ''.join(c if c.isalnum() or c in ('.', '-', '_') else '-' for c in kernel_name).rstrip()

    kernel_dir = os.path.join(jupyter_data_dir(), 'kernels', safe_name)

    if os.path.isdir(kernel_dir):
      logger.error('Kernel directory %s already exists. Choose another name or delete the directory', kernel_dir)
      return 1

    # Build-up command args to start a kernel
    kernel_args = [
      sys.executable,
      '-m', 'remote_kernel',
      ssh_host
    ]
    if jump_server is not None:
      for j in jump_server:
        kernel_args += ['-J', j]
    if ssh_key is not None:
      kernel_args += ['-i', ssh_key]
    if pre_command is not None:
      kernel_args += ['-c', '%s && python -m ipykernel' % pre_command]
    if no_remote_files:
      kernel_args += ['--no-remote-files']
    kernel_args += ['-f', '{connection_file}']

    kernel_spec = dict(
      argv=kernel_args,
      language='python',
      display_name=kernel_name
    )

    os.makedirs(kernel_dir)
    with open(os.path.join(kernel_dir, 'kernel.json'), mode='w') as kernel_fs:
      json.dump(kernel_spec, kernel_fs, indent=2)

    resource_dir = get_resource_dir()
    for fname in ('logo-32x32.png', 'logo-64x64.png'):
      shutil.copy(os.path.join(resource_dir, fname), os.path.join(kernel_dir, fname))

    logger.info('Kernel specification installed in %s', kernel_dir)
    return 0

  finally:
    clients.reverse()
    for client in clients:
      client.close()
