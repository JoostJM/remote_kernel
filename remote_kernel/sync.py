import json
import logging
import os
import time

from paramiko import SFTP


class ParamikoSync(object):
  def __init__(self, ssh_client,
               local_folder='./remote_kernel_sync',
               remote_folder='./remote_kernel_sync',
               recursive=True,
               bi_directional=False):
    self.logger = logging.getLogger('remote_kernel.sync')

    self.ssh_client = ssh_client
    self.sftp_client = None

    self.local_folder = os.path.abspath(local_folder)
    self.logger.debug('Normalized local path to %s', self.local_folder)
    self.remote_folder = remote_folder

    # Directionality and extent of synchronization
    self.recursive = recursive
    self.bi_directional = bi_directional

    # Local and remote sync folders are only checked when a connection is first made.
    self._is_folder_checked = False

    # Files that should be excluded during synchronization
    self.excluded_files = {'.remote_kernel_sync'}  # config file to allow separate subfolders

    # Epoch time of last synchronization
    self._last_sync = 0

  def __del__(self):
    self.logger.debug('Finalizing ParamikoSync instance')
    self.close()  # Ensure the connection is closed
    self.ssh_client = None

  def __enter__(self):
    self.connect()
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    self.close()

  def connect(self, skip_check=False):
    if self.sftp_client is None:
      self.logger.debug('Starting SFTP client')
      self.sftp_client = SFTP.from_transport(self.ssh_client.get_transport())

      if not self._is_folder_checked and not skip_check:
        self.check_local_sync_folders()
        self.check_remote_sync_folder()
        self._is_folder_checked = True

    return self

  def close(self):
    if self.sftp_client:
      self.logger.debug('Closing SFTP Client')
      self.sftp_client.close()
      self.sftp_client = None

  def check_local_sync_folders(self):
    if not os.path.isdir(self.local_folder):
      self.logger.info('Creating local sync directory %s', self.local_folder)
      os.makedirs(self.local_folder)

  def check_remote_sync_folder(self):
    if self.sftp_client is None:
      self.logger.warning('This ParamikoSync instance has been closed')
      return

    self.remote_folder = self.sftp_client.normalize(self.remote_folder)
    self.logger.debug('Normalized remote path to %s', self.remote_folder)

    remote_dirname = os.path.dirname(self.remote_folder)
    remote_basename = os.path.basename(self.remote_folder)
    remote_dirs = {entry.filename: entry for entry in self.sftp_client.listdir_attr(remote_dirname)}

    # Ensure the folder structure in the sync folder is copied
    if remote_basename not in remote_dirs.keys() or not self._isdir(remote_dirs[remote_basename]):
      self.logger.info('Creating remote sync directory %s', self.remote_folder)
      self.sftp_client.mkdir(self.remote_folder)

  def get_chdir_cmd(self):
    return 'cd "%s"' % self.remote_folder

  def set_subfolder(self, kernel_name):
    local_config = os.path.join(self.local_folder, '.remote_kernel_sync')
    if os.path.isfile(local_config):
      with open(local_config) as conf_fs:
        config = json.load(conf_fs)
    else:
      config = {}

    kernel_config = config.get(kernel_name, None)
    if kernel_config is None:
      with self.connect():  # This connection ensures local and remote root folders are created
        remote_folders = self._get_remote_dirs()
        i = 1
        while str(i) in remote_folders:
          i += 1
        self.remote_folder = self._unix_join(self.remote_folder, str(i))
        self.logger.info('Creating synchronization sub-folder %s', self.remote_folder)
        self.sftp_client.mkdir(self.remote_folder)
      config[kernel_name] = {'remote_kernel_id': str(i)}
      with open(local_config, mode='w') as out_fs:
        json.dump(config, out_fs)
    else:
      self.remote_folder = self._unix_join(self.remote_folder, kernel_config['remote_kernel_id'])

  def _get_remote_dirs(self, folder='.'):
    return [
      entry.filename
      for entry in self.sftp_client.listdir_attr(self._unix_join(self.remote_folder, folder))
      if self._isdir(entry)
    ]

  def sync(self):
    if self.sftp_client is None:
      self.logger.warning('This ParamikoSync instance has been closed')
      return

    self._sync_remote_folder()
    if self.bi_directional:
      self._sync_local_folder()
    self._last_sync = time.time()

  def _sync_local_folder(self, folder='.'):
    self.logger.info('Synchronizing local folder %s to remote folder %s',
                     self._unix_join(self.local_folder, folder), self.remote_folder)
    folder_stack = [folder]

    while len(folder_stack) > 0:
      fldr = folder_stack.pop()

      entries = os.listdir(os.path.join(self.local_folder, fldr))
      remote_entries = {entry.filename: entry for entry in
                        self.sftp_client.listdir_attr(self._unix_join(self.remote_folder, fldr))}

      for entry in entries:
        entry_path = self._unix_join(fldr, entry)
        entry_stat = os.stat(os.path.join(self.local_folder, entry_path))

        if self._isdir(entry_stat):
          if self.recursive:
            # Ensure the folder structure in the sync folder is copied
            if entry not in remote_entries.keys() or not self._isdir(remote_entries[entry]):
              self.sftp_client.mkdir(self._unix_join(self.remote_folder, entry_path))

            folder_stack.append(entry_path)
        elif entry in self.excluded_files or entry_stat.st_mtime < self._last_sync:
          continue  # Excluded or unchanged since last sync, skip
        else:  # This file should be synced!
          # Compare to the local version if it exists
          remote_file = remote_entries.get(entry, None)
          remote_mtime = 0
          if remote_file is not None:
            remote_mtime = remote_file.st_mtime

          if entry_stat.st_mtime > remote_mtime:
            dest_file = self._unix_join(self.remote_folder, entry_path)
            self.logger.info('Pushing file %s to the remote', entry_path)
            self.sftp_client.put(os.path.join(self.local_folder, entry_path), dest_file)
            self.sftp_client.utime(dest_file, (entry_stat.st_atime, entry_stat.st_mtime))

  def _sync_remote_folder(self, folder='.'):
    self.logger.info('Synchronizing remote folder %s to local folder %s',
                     self._unix_join(self.remote_folder, folder), self.local_folder)
    folder_stack = [folder]

    while len(folder_stack) > 0:
      fldr = folder_stack.pop()
      entries = self.sftp_client.listdir_attr(self._unix_join(self.remote_folder, fldr))

      for entry in entries:
        entry_path = self._unix_join(fldr, entry.filename)
        if self._isdir(entry):
          if self.recursive:
            folder_stack.append(entry_path)
        elif entry in self.excluded_files or entry.st_mtime < self._last_sync:
          continue  # Excluded or unchanged since last sync, skip
        else:  # This file should be synced!
          # Compare to the local version if it exists
          local_file = os.path.join(self.local_folder, entry_path)
          local_mtime = 0
          if os.path.isfile(local_file):
            local_mtime = os.stat(local_file).st_mtime

          if entry.st_mtime > local_mtime:
            # Ensure the destination directory exists
            dest_dir = os.path.join(self.local_folder, fldr)
            if not os.path.isdir(dest_dir):
              os.makedirs(dest_dir)

            # Get the file
            self.logger.info('Getting file %s from the remote', entry_path)
            self.sftp_client.get(self._unix_join(self.remote_folder, entry_path), local_file)

            # Set the local file's modified time to the modified time on the server
            os.utime(local_file, (entry.st_atime, entry.st_mtime))

  @staticmethod
  def _isdir(attr):
    return (attr.st_mode & 0o40000) == 0o40000

  @staticmethod
  def _unix_join(*path_parts):
    return '/'.join(path_parts)
