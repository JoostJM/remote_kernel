import logging
import sys


def main(argv=None):
  logger = logging.getLogger('remote_kernel.main')

  if argv is None:
    argv = sys.argv[1:]

  if len(argv) < 1:
    logger.error('Requires at least an argument to select script or arguments to start kernel!')
    return 2
  elif argv[0] == 'install':
    from .install import parse_args
    del argv[0]  # remove the 'install' argument
    logger.debug('Starting Install script with args %s', argv)
    return parse_args(argv)
  else:  # No script select --> start kernel
    from .start import parse_args
    logger.debug('Starting Start script with args %s', argv)
    return parse_args(argv)


if __name__ == '__main__':
  exit(main())
