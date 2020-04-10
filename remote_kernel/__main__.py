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
import sys
import time

import paramiko

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


def main(argv=None):
    global CMD_ARGS

    parser = argparse.ArgumentParser()
    parser.add_argument('ssh_host')
    parser.add_argument('-J', dest='jump_server', default=None, action='append')
    parser.add_argument('-i', dest='ssh_key', default=None)
    parser.add_argument('--command', '-c', default='python -m ipykernel')
    parser.add_argument('--file', '-f', required=True)

    args = parser.parse_args(argv)

    with open(args.file, mode='r') as file_fs:
        conn_config = json.load(file_fs)

    arguments = CMD_ARGS % conn_config
    ssh_cmd = '%s %s' % (args.command, arguments)

    fwd_ports = [('localhost', conn_config[port]) for port in conn_config if port.endswith('_port')]

    clients = []
    tunnel = None
    try:
      # Connect via jump server(s) if specified
      for jump_server in args.jump_server:
        client = ParamikoClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect_override(jump_server, args.ssh_key, clients[-1] if len(clients) > 0 else None)
        clients.append(client)
      ssh_client = ParamikoClient()
      ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
      ssh_client.connect_override(args.ssh_host, args.ssh_key, clients[-1] if len(clients) > 0 else None)
      clients.append(ssh_client)

      tunnel = ssh_client.create_forwarding_tunnel(fwd_ports, fwd_ports.copy())

      chan = ssh_client.get_transport().open_session()
      chan.get_pty()
      chan.exec_command(ssh_cmd)
      time.sleep(0.5)  # Wait just a bit to allow the IPyKernel to start up
      tunnel.start()
      try:
        while True:
          data = chan.recv(4096)
          if not data:
            sys.stdout.write("\r\n*** SSH Channel Closed ***\r\n\r\n")
            sys.stdout.flush()
            break
          sys.stdout.write(data.decode('utf-8'))
          sys.stdout.flush()
          raise KeyboardInterrupt
      except (KeyboardInterrupt, SystemExit):
        print("Cancelled!")
      return 0
    except Exception as e:
      print(e)
      return 1
    finally:
      if tunnel is not None:
        tunnel.close()
      clients.reverse()
      for client in clients:
        client.close()


if __name__ == '__main__':
    exit(main())
