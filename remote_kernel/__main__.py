import argparse
import json
import logging

from .start import start_kernel


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


def main(argv=None):
  logger = logging.getLogger('remote_kernel.main')

  parser = argparse.ArgumentParser()
  parser.add_argument('ssh_host')
  parser.add_argument('-J', dest='jump_server', default=[], action='append')
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

  return start_kernel(args.ssh_host, args.ssh_key, args.jump_server, args.command, conn_config)


if __name__ == '__main__':
  exit(main())
