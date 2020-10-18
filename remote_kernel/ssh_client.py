import logging
import os
import re

import paramiko
from sshtunnel import SSHTunnelForwarder

logger = logging.getLogger('remote_kernel.ssh_client')
try:
  from . import dialog
except ImportError as e:
  logger.warning('Could not import GUI module!\n\t' + str(e))
  dialog = None


class ParamikoClient(paramiko.SSHClient):
  # Regex pattern to parse out ssh connection arguments of format [username@]host[:port]
  host_pattern = re.compile(r'((?P<user>[^@]+)@)?(?P<host>[^:]+)(:(?P<port>\d+))?')

  def __init__(self, hostkeys='~/.ssh/known_hosts'):
    super(ParamikoClient, self).__init__()
    self.host = None
    self.port = paramiko.config.SSH_PORT
    self.username = None
    self.private_key = None
    self.load_host_keys(os.path.expanduser(hostkeys))

  def connect_override(self, host, pkey=None, jump_host=None, use_jump_pkey=True):
    """
    Alternative function to connect to SSH client. provides an override to paramiko.SSHClient.connect, with
    fewer arguments.

    :param host: SSH host to connect to. Expected format: [username@]host[:port]
    :param pkey: paramiko.RSAKey or string pointing to ssh key to use for authentication
    :param jump_host: Optional instance of ParamikoClient connected to the jump server.
    :param use_jump_pkey: If True and jump_host is not None, re-use the jump_host.private_key.
        If successful, pkey is ignored.
    :return: None
    """
    # Parse out the connection string
    host_match = self.host_pattern.fullmatch(host)
    if host_match is None:
      raise ValueError('Host string "%s" is invalid. Should match [username@]host[:port]')
    host_dict = host_match.groupdict()
    self.host = host_dict['host']
    if host_dict['port'] is not None:
      self.port = int(self.port)
    self.username = host_dict['user']

    if self.username is None:
      if dialog is None:
        raise ValueError('username is required, but password dialog does not work!')
      self.username = dialog.PromptDialog(prompt='Connecting to\n%s:%i\nUsername:' % (self.host, self.port),
                                          title="Username?").showDialog()
      assert self.username is not None and self.username != ''

    # Set up the authentication variables
    pwd = None
    if jump_host is not None and use_jump_pkey and jump_host.private_key is not None:
      self.private_key = jump_host.private_key
    elif pkey is not None:
      if isinstance(pkey, paramiko.RSAKey):
        self.private_key = pkey
      elif isinstance(pkey, str):
        try:
          self.private_key = paramiko.RSAKey.from_private_key_file(os.path.expanduser(pkey))
        except paramiko.PasswordRequiredException:
          if dialog is None:
            raise ValueError('Provided key requires password, but password dialog does not work!')
          pwd = dialog.PwdDialog(prompt='Loading SSH Key:\n%s\nRSA passphrase' % pkey,
                                 title="RSA Passphrase").showDialog()
          self.private_key = paramiko.RSAKey.from_private_key_file(os.path.expanduser(pkey), pwd)
    elif dialog is None:
      raise ValueError('Cannot start client without private key when password dialog does not work.')
    else:
      pwd = dialog.PwdDialog(prompt='Connecting to\n%s@%s:%i\nPassword:' % (self.username, self.host, self.port),
                             title='Password').showDialog()

    jump_channel = None
    if jump_host is not None:
      assert isinstance(jump_host, ParamikoClient)
      src_addr = (jump_host.host, jump_host.port)
      dest_addr = (self.host, self.port)
      jump_transport = jump_host.get_transport()
      jump_channel = jump_transport.open_channel('direct-tcpip', dest_addr=dest_addr, src_addr=src_addr)

    self.connect(self.host, self.port, self.username, pwd, self.private_key, sock=jump_channel)

  def create_forwarding_tunnel(self, local_bind_addresses, remote_bind_addresses):
    # Set up the tunnel. Though we pass the target host, port, user and dummy password, these are not used.
    # This is done to make sure the initialization does not fail (does type checking on the connection args)
    # Instead, we manually set the transport we get from the existing connection.
    # This prevents the tunnel from trying to open up a new connection

    # Suppress log output from sshtunnel
    ssh_logger = logging.getLogger('ssh_tunnel')
    ssh_logger.addHandler(logging.NullHandler())
    tunnel = SSHTunnelForwarder((self.host, self.port),
                                ssh_username=self.username, ssh_password='dummy',
                                local_bind_addresses=local_bind_addresses,
                                remote_bind_addresses=remote_bind_addresses,
                                logger=ssh_logger)
    tunnel._transport = self.get_transport()
    return tunnel
