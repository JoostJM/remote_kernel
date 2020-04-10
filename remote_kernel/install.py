import argparse
import json
import logging
import os
import shutil
import sys

from jupyter_core.paths import jupyter_data_dir
import paramiko

from . import get_resource_dir
from .ssh_client import ParamikoClient


logger = logging.getLogger('remote_kernel.install')


def parse_args(argv=None):
  parser = argparse.ArgumentParser()
  parser.add_argument('ssh_host', metavar='[username@]host[:port]',
                      help='Remote server to connect to. Formatted as [username@]host[:port]')
  parser.add_argument('-J', dest='jump_server', metavar='[username@]host[:port]', default=None, action='append',
                      help='Optional jump servers to connect through to the host')
  parser.add_argument('-i', dest='ssh_key', default=None, help='ssh key to use for authentication')
  parser.add_argument('--command', '-c', default=None,
                      help='Additional commands to execute on remote server, prior to '
                           'starting the kernel (`python -m ipykernel -f {connection_file}`)')
  parser.add_argument('--name', '-n', default='remote_kernel-%(user)s@%(host)s',
                      help='Display name of the kernel to install')

  args = parser.parse_args(argv)
  return install_kernel(args.name, args.ssh_host, args.ssh_key, args.jump_server, args.command)


def install_kernel(kernel_name, ssh_host, ssh_key=None, jump_server=None, pre_command=None):
  global logger

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
    cmd = 'python -c "import ipykernel"'
    if pre_command is not None:
      cmd = '%s && %s' % (pre_command, cmd)

    logger.debug('Running cmd %s', cmd)
    chan.exec_command(cmd)
    result = chan.recv_exit_status()

    if result != 0:
      logger.error('CMD %s returned a non-zero exit status on remote server.', cmd)
      data = chan.recv(4096)
      while data:
        logger.info("REMOTE >>> " + data.decode('utf-8'))
        data = chan.recv(4096)
      return 1

    logger.info('Command successful, writing kernel_spec file')

    name_spec = dict(
      user=ssh_client.username,
      host=ssh_client.host,
      port=ssh_client.port
    )
    kernel_name = kernel_name % name_spec
    kernel_dir = os.path.join(jupyter_data_dir(), 'kernels', kernel_name)

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
  except Exception as e:
    logger.error('Kernel installation error', exc_info=True)
    return 1
  finally:
    clients.reverse()
    for client in clients:
      client.close()
