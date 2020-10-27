import argparse
import json
import logging
import os
import threading
import time

from jupyter_core.paths import jupyter_runtime_dir

from . import CMD_ARGS, get_parser
from .ssh_client import ParamikoClient
from .sync import ParamikoSync


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
  spec = check_spec(kernel_spec, spec)

  args = spec['argv']

  assert args[1:3] == ['-m', 'remote_kernel'], \
      'Kernel spec %s is not a remote_kernel specification' % kernel_spec

  # Remove the jupyter supplied connection_file specification
  if '-f' in args and args[args.index('-f') + 1] == '{connection_file}':
    idx = args.index('-f')
    del args[idx: idx+2]
  elif '-f={connection_file}' in args:
    del args[args.index('-f={connection_file}')]

  return parse_args(args[3:])


def check_spec(kernel_spec, spec):
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


def parse_args(argv=None):
  global logger
  parser = get_parser()

  logger.debug('parsing arguments')
  args = parser.parse_args(argv)
  arg_dict = args.__dict__.copy()

  target = arg_dict.pop('target')

  connection_file = arg_dict.pop('file')
  if connection_file is not None:
    logger.debug('reading kernel config file %s', args.file)
    with open(args.file, mode='r') as file_fs:
      conn_config = json.load(file_fs)
  else:
    logger.debug('Generating new kernel config')
    conn_config = generate_config()

  return start_kernel(target, conn_config, **arg_dict)


def start_kernel(ssh_host, connection_config, **kwargs):
    global logger

    ssh_key = kwargs.get('ssh_key', None)
    jump_server = kwargs.get('jump_server', None)
    command = kwargs.get('pre_command', None)
    kernel = kwargs.get('kernel', 'python -m ipykernel')
    no_remote_files = kwargs.get('no_remote_files', False)

    fwd_ports = [('localhost', connection_config[port]) for port in connection_config if port.endswith('_port')]

    kernel_fname = None
    try:
      with ParamikoClient().connect_override(ssh_host, ssh_key, jump_server) as ssh_client:
        tunnel = ssh_client.create_forwarding_tunnel(fwd_ports, fwd_ports.copy())

        if no_remote_files:
          arguments = ' '.join(['%s=%s' % (key, value) for key, value in CMD_ARGS.items()]) % connection_config
        else:
          config_str = json.dumps(connection_config, indent=2)
          ssh_client.exec_command("echo '%s' > remote_kernel.json" % config_str)
          arguments = '-f ~/remote_kernel.json'

        # Setup synchronization if enabled
        if kwargs.get('synchronize', False):
          synchronizer = ParamikoSync(ssh_client, **{k: v for k, v in kwargs.items() if k in
                                                     ('local_folder=', 'remote_folder', 'recursive', 'bi_directional')})
          synchronizer.set_subfolder(kwargs.get('kernel_name', 'N/A'))
          try:
            with synchronizer.connect() as sync:
              sync.sync()
          except Exception:
            logger.error('Error synchronizing files!', exc_info=True)
        else:
          synchronizer = None

        # Start IPyKernel
        ssh_cmd = '%s %s' % (kernel, arguments)
        if synchronizer is not None:
          logger.info("Changing dir to %s", synchronizer.remote_folder)
          ssh_cmd = '%s && %s' % (synchronizer.get_chdir_cmd(), ssh_cmd)
        if command is not None:
          ssh_cmd = '%s && %s' % (command, ssh_cmd)

        chan = ssh_client.get_transport().open_session()
        chan.get_pty()
        logger.debug('Excecuting cmd %s', ssh_cmd)
        chan.exec_command(ssh_cmd)

        try:
          time.sleep(0.5)  # Wait just a bit to allow the IPyKernel to start up
          tunnel.start()

          kernel_fname = os.path.join(jupyter_runtime_dir(),
                                      'kernel-%s@%s.json' % (ssh_client.username, ssh_client.host))
          with open(kernel_fname, mode='w') as kernel_fs:
            json.dump(connection_config, kernel_fs, indent=2)

          logger.info('Remote Kernel started. To connect another client to this kernel, use:\n\t--existing %s' %
                      os.path.basename(kernel_fname))

          def writeall(sock):
            while True:
              data = sock.recv(4096)
              if not data:
                logger.info("\r\n*** SSH Channel Closed ***\r\n\r\n")
                break
              logger.info("REMOTE >>> " + data.decode('utf-8').replace('\n', '\nREMOTE >>> '))

          writer = threading.Thread(target=writeall, args=(chan,))
          writer.setDaemon(True)
          writer.start()

          while not chan.exit_status_ready():
            time.sleep(1)

        except (KeyboardInterrupt, SystemExit):
          logger.info("Interrupting kernel...")

        if not no_remote_files:
          ssh_client.exec_command('rm ~/remote_kernel.json')

        if synchronizer is not None:
          try:
            with synchronizer.connect() as sync:
              sync.sync()
          except Exception:
            logger.error('Error synchronizing files!', exc_info=True)

        return 0
    except Exception:
      logger.error('Main loop error', exc_info=True)
      return 1
    finally:
      if kernel_fname is not None and os.path.exists(kernel_fname):
        os.remove(kernel_fname)
