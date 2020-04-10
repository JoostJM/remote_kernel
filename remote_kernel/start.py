
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
import json
import logging
import os
import time

import paramiko
from jupyter_core.paths import jupyter_runtime_dir

from .ssh_client import ParamikoClient

# argument template for starting up an IPyKernel without supplying a connection file
# arguments to fill this template are read from the connection file which remains on
# the local computer. It only ignores the kernel_name argument from the connection file.
CMD_ARGS = ' '.join([
  '--ip="%(ip)s"',
  '--stdin=%(stdin_port)i',
  '--shell=%(shell_port)i',
  '--iopub=%(iopub_port)i',
  '--hb=%(hb_port)i',
  '--control=%(control_port)i',
  '--Session.signature_scheme="%(signature_scheme)s"',
  '--Session.key="b\'%(key)s\'"',  # Py3 compat: ensure the key is interpreted as a byte string
  '--transport="%(transport)s"'
])

logger = logging.getLogger('remote_kernel.start')


def generate_config():
  """
  Generate a new kernel connection config dictionary
  :return: Kernel config dictionary
  """
  from jupyter_client.session import new_id
  import socket
  from contextlib import closing

  def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
      s.bind(('', 0))
      s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      return s.getsockname()[1]

  return dict(
    ip='127.0.0.1',
    key=new_id(),
    signature_scheme='hmac-sha256',
    kernel_name='',
    stdin_port=find_free_port(),
    shell_port=find_free_port(),
    iopub_port=find_free_port(),
    hb_port=find_free_port(),
    control_port=find_free_port(),
    transport='tcp'
  )


def parse_args(argv=None):
  global logger
  parser = argparse.ArgumentParser()
  parser.add_argument('ssh_host', metavar='[username@]host[:port]',
                      help='Remote server to connect to. Formatted as [username@]host[:port]')
  parser.add_argument('-J', dest='jump_server', metavar='[username@]host[:port]', default=[], action='append')
  parser.add_argument('-i', dest='ssh_key', default=None)
  parser.add_argument('--command', '-c', default='python -m ipykernel')
  parser.add_argument('--file', '-f')

  logger.debug('parsing arguments')
  args = parser.parse_args(argv)

  if args.file is not None:
    logger.debug('reading kernel config file %s', args.file)
    with open(args.file, mode='r') as file_fs:
      conn_config = json.load(file_fs)
  else:
    logger.debug('Generating new kernel config')
    conn_config = generate_config()

  return start_kernel(args.ssh_host, conn_config, args.ssh_key, args.jump_server, args.command)


def start_kernel(ssh_host, connection_config, ssh_key=None, jump_server=None, command=None):
    global CMD_ARGS, logger

    arguments = CMD_ARGS % connection_config
    ssh_cmd = '%s %s' % (command, arguments)

    fwd_ports = [('localhost', connection_config[port]) for port in connection_config if port.endswith('_port')]
    fwd_ports.append(('localhost', 0))

    clients = []
    tunnel = None
    kernel_fname = None
    try:
      # Connect via jump server(s) if specified
      if jump_server is not None:
        for srvr in jump_server:
          client = ParamikoClient()
          client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
          client.connect_override(srvr, ssh_key, clients[-1] if len(clients) > 0 else None)
          clients.append(client)
      ssh_client = ParamikoClient()
      ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
      ssh_client.connect_override(ssh_host, ssh_key, clients[-1] if len(clients) > 0 else None)
      clients.append(ssh_client)

      tunnel = ssh_client.create_forwarding_tunnel(fwd_ports, fwd_ports.copy())

      chan = ssh_client.get_transport().open_session()
      chan.get_pty()
      chan.exec_command(ssh_cmd)
      time.sleep(0.5)  # Wait just a bit to allow the IPyKernel to start up
      tunnel.start()

      kernel_fname = os.path.join(jupyter_runtime_dir(),
                                  'kernel-%s@%s.json' % (ssh_client.username, ssh_client.host))
      with open(kernel_fname, mode='w') as kernel_fs:
        json.dump(connection_config, kernel_fs, indent=2)

      logger.info('Remote Kernel started. To connect another client to this kernel, use:\n\t--existing %s' %
            os.path.basename(kernel_fname))

      try:
        while True:
          data = chan.recv(4096)
          if not data:
            logger.info("\r\n*** SSH Channel Closed ***\r\n\r\n")
            break
          logger.debug("REMOTE >>> " + data.decode('utf-8').replace('\n', '\nREMOTE >>> '))
      except (KeyboardInterrupt, SystemExit):
        logging.info("Cancelled!")
      return 0
    except Exception as e:
      logger.error('Main loop error', exc_info=True)
      return 1
    finally:
      try:
        if tunnel is not None:
          tunnel.close()
        clients.reverse()
        for client in clients:
          client.close()
      except KeyboardInterrupt:  # When users keep hammering that CTRL-C
        pass
      finally:
        if kernel_fname is not None and os.path.exists(kernel_fname):
          os.remove(kernel_fname)
