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

    self.recursive = recursive
    self.bi_directional = bi_directional
    self.logger.debug('Starting SFTP client')
    self.sftp_client = SFTP.from_transport(ssh_client.get_transport())

    self.local_folder = os.path.abspath(local_folder)
    self.logger.debug('Normalized local path to %s', self.local_folder)
    self.remote_folder = self.sftp_client.normalize(remote_folder)
    self.logger.debug('Normalized remote path to %s', self.remote_folder)

    self._check_sync_folders()

    self.excluded_files = {}

    self._last_sync = 0

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    self.close()

  def _check_sync_folders(self):
    if self.sftp_client is None:
      self.logger.warning('This ParamikoSync instance has been closed')
      return

    if not os.path.isdir(self.local_folder):
      self.logger.info('Creating local sync directory %s', self.local_folder)
      os.makedirs(self.local_folder)

    remote_dirname = os.path.dirname(self.remote_folder)
    remote_basename = os.path.basename(self.remote_folder)
    remote_dirs = {entry.filename: entry for entry in self.sftp_client.listdir_attr(remote_dirname)}

    # Ensure the folder structure in the sync folder is copied
    if remote_basename not in remote_dirs.keys() or not self._isdir(remote_dirs[remote_basename]):
      self.logger.info('Creating remote sync directory %s', self.remote_folder)
      self.sftp_client.mkdir(self.remote_folder)

  def get_chdir_cmd(self):
    return 'cd "%s"' % self.remote_folder

  def sync(self):
    if self.sftp_client is None:
      self.logger.warning('This ParamikoSync instance has been closed')
      return

    self._sync_remote_folder()
    if self.bi_directional:
      self._sync_local_folder()
    self._last_sync = time.time()

  def _sync_local_folder(self, folder='.'):
    self.logger.debug('Synchronizing local folder %s to remote folder %s',
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
        elif entry in self.excluded_files or entry_stat.st_mtime < self._last_sync:  # Not changed since last sync, skip
          continue
        else:
          remote_file = remote_entries.get(entry, None)
          remote_mtime = 0
          if remote_file is not None:
            remote_mtime = remote_file.st_mtime

          if entry_stat.st_mtime > remote_mtime:
            dest_file = self._unix_join(self.remote_folder, entry_path)
            self.sftp_client.put(os.path.join(self.local_folder, entry_path), dest_file)
            self.sftp_client.utime(dest_file, (entry_stat.st_atime, entry_stat.st_mtime))

  def _sync_remote_folder(self, folder='.'):
    self.logger.debug('Synchronizing remote folder %s to local folder %s',
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
        elif entry.st_mtime < self._last_sync:  # Not changed since last sync, skip
          continue
        else:
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
            self.sftp_client.get(self._unix_join(self.remote_folder, entry_path), local_file)

            # Set the local file's modified time to the modified time on the server
            os.utime(local_file, (entry.st_atime, entry.st_mtime))

  @staticmethod
  def _isdir(attr):
    return (attr.st_mode & 0o40000) == 0o40000

  @staticmethod
  def _unix_join(*path_parts):
    return '/'.join(path_parts)

  def close(self):
    if self.sftp_client:
      self.logger.debug('Closing SFTP Client')
      self.sftp_client.close()
      self.sftp_client = None
