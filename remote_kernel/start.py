
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
import json
import logging
import os
import sys
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


def start_kernel(ssh_host, ssh_key, jump_server, command, connection_config):
    global CMD_ARGS

    logger = logging.getLogger('remote_kernel.start')

    arguments = CMD_ARGS % connection_config
    ssh_cmd = '%s %s' % (command, arguments)

    fwd_ports = [('localhost', connection_config[port]) for port in connection_config if port.endswith('_port')]
    fwd_ports.append(('localhost', 0))

    clients = []
    tunnel = None
    kernel_fname = None
    try:
      # Connect via jump server(s) if specified
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
          logger.info("REMOTE >>> " + data.decode('utf-8'))
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
      except KeyboardInterrupt:
        pass
      finally:
        if kernel_fname is not None and os.path.exists(kernel_fname):
          os.remove(kernel_fname)
