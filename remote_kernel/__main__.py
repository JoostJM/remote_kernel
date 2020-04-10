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
import os
import re
import sys
import time

import paramiko
from sshtunnel import SSHTunnelForwarder

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

# Regex pattern to parse out ssh connection arguments of format [username@]host[:port]
HOST_PATTERN = re.compile(r'((?P<user>[^@]+)@)?(?P<host>[^:]+)(:(?P<port>\d+))?')


def main(argv=None):
    global CMD_ARGS, HOST_PATTERN

    parser = argparse.ArgumentParser()
    parser.add_argument('ssh_host')
    parser.add_argument('-J', dest='jump_server', default=None)
    parser.add_argument('-i', dest='ssh_key', default=None)
    parser.add_argument('--command', '-c', default='python -m ipykernel')
    parser.add_argument('--file', '-f', required=True)

    args = parser.parse_args(argv)

    with open(args.file, mode='r') as file_fs:
        conn_config = json.load(file_fs)

    arguments = CMD_ARGS % conn_config
    ssh_cmd = '%s %s' % (args.command, arguments)

    target_dict = HOST_PATTERN.fullmatch(args.ssh_host).groupdict()
    if target_dict['port'] is None:
        target_dict['port'] = '22'

    keyfile = None
    if args.ssh_key is not None:
        keyfile = os.path.expanduser(args.ssh_key)

    fwd_ports = [('localhost', conn_config[port]) for port in conn_config if port.endswith('_port')]

    jump_client = None
    ssh_client = None

    tunnel = None
    try:
        # Connect via jump channel if specified
        if args.jump_server is not None:
            jump_dict = HOST_PATTERN.fullmatch(args.jump_server).groupdict()
            if jump_dict['port'] is None:
                jump_dict['port'] = '22'
            src_addr = (jump_dict['host'], int(jump_dict['port']))
            dest_addr = (target_dict['host'], int(target_dict['port']))

            jump_client = paramiko.SSHClient()
            jump_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            jump_client.connect(jump_dict['host'], port=int(jump_dict['port']), username=jump_dict['user'], key_filename=keyfile)

            jump_transport = jump_client.get_transport()

            jump_channel = jump_transport.open_channel('direct-tcpip', dest_addr=dest_addr, src_addr=src_addr)
        else:
            jump_channel = None
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(target_dict['host'], port=int(target_dict['port']), username=target_dict['user'],
                           key_filename=keyfile, sock=jump_channel)

        ssh_transport = ssh_client.get_transport()

        # Set up the tunnel. Though we pass the target host, port, user and dummy password, these are not used.
        # This is done to make sure the initialization does not fail (does type checking on the connection args)
        # Instead, we manually set the transport we get from the existing connection.
        # This prevents the tunnel from trying to open up a new connection
        tunnel = SSHTunnelForwarder((target_dict['host'], int(target_dict['port'])),
                                    ssh_username=target_dict['user'], ssh_password='dummy',
                                    local_bind_addresses=fwd_ports,
                                    remote_bind_addresses=fwd_ports.copy())
        tunnel._transport = ssh_transport

        chan = ssh_transport.open_session()
        chan.get_pty()
        chan.exec_command(ssh_cmd)
        time.sleep(0.5)  # Wait just a bit to allow the IPyKernel to start up
        tunnel.start()
        try:
          while True:
            data = chan.recv(256)
            if not data:
              sys.stdout.write("\r\n*** SSH Channel Closed ***\r\n\r\n")
              sys.stdout.flush()
              break
            sys.stdout.write(data.decode('utf-8'))
            sys.stdout.flush()
        except (KeyboardInterrupt, SystemExit):
          print("Cancelled!")
    finally:
        if tunnel is not None and tunnel.is_alive:
            tunnel.stop()  # This also closes the transport we passed, but that's ok, we don't need it.
        if ssh_client is not None:
            ssh_client.close()
        if jump_client is not None:
            jump_client.close()


if __name__ == '__main__':
    main()
