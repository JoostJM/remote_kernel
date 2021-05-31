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

    self._jump_host = None
    self.tunnels = []

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    self.close()

  def connect_override(self, host, pkey=None, jump_host=None, use_jump_pkey=True):
    """
    Alternative function to connect to SSH client. provides an override to paramiko.SSHClient.connect, with
    fewer arguments.

    :param host: SSH host to connect to. Expected format: [username@]host[:port]
    :param pkey: paramiko.RSAKey or string pointing to ssh key to use for authentication
    :param jump_host: Optional (list or tuple of) string (format same as `host`) or instance of ParamikoClient connected
      to the jump server. When an item in the list is a ParmikoClient, all subsequent items are ignored.
    :param use_jump_pkey: If True and jump_host is not None, re-use the jump_host.private_key.
        If successful, pkey is ignored.
    :return: None
    """
    if jump_host is not None:
      # First check if jump host is a list/tuple or a single item
      if isinstance(jump_host, (tuple, list)):
        # Get the last item, as the first real connection is made at the bottom of this recursive function
        if len(jump_host) > 0:
          jump_client = jump_host[-1]
          next_jump = jump_host[:-1]
        else:
          jump_client = None
          next_jump = None
      else:
        jump_client = jump_host
        next_jump = None

      # set the jump_host, connect to it if the item is just the host address
      if jump_client is None:
        pass
      elif isinstance(jump_client, ParamikoClient):
        self._jump_host = jump_client
      elif isinstance(jump_client, str):
        self._jump_host = ParamikoClient().connect_override(jump_client, pkey, next_jump, use_jump_pkey)
      else:
        raise ValueError("Jump host items should either be ParamikoClient or string, found type %s" % type(jump_client))

    self.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Parse out the connection string
    host_match = self.host_pattern.fullmatch(host)
    if host_match is None:
      raise ValueError('Host string "%s" is invalid. Should match [username@]host[:port]')
    host_dict = host_match.groupdict()
    self.host = host_dict['host']
    if host_dict['port'] is not None:
      self.port = int(host_dict['port'])
    self.username = host_dict['user']

    if self.username is None:
      if dialog is None:
        raise ValueError('username is required, but password dialog does not work!')
      self.username = dialog.PromptDialog(prompt='Connecting to\n%s:%i\nUsername:' % (self.host, self.port),
                                          title="Username?").showDialog()
      assert self.username is not None and self.username != ''

    # Set up the authentication variables
    pwd = None
    if self._jump_host is not None and use_jump_pkey and self._jump_host.private_key is not None:
      self.private_key = self._jump_host.private_key
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
    if self._jump_host is not None:
      src_addr = (self._jump_host.host, self._jump_host.port)
      dest_addr = (self.host, self.port)
      jump_transport = self._jump_host.get_transport()
      jump_channel = jump_transport.open_channel('direct-tcpip', dest_addr=dest_addr, src_addr=src_addr)

      self._jump_host = self._jump_host

    self.connect(self.host, self.port, self.username, pwd, self.private_key, sock=jump_channel)
    return self

  def close(self):
    # Clean up SSH connection
    for tunnel in self.tunnels:
      tunnel.close()
    self.tunnels = None

    super(ParamikoClient, self).close()
    if self._jump_host is not None:
      self._jump_host.close()
      self._jump_host = None

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
    self.tunnels.append(tunnel)
    return tunnel
