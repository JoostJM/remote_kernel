import argparse
import logging
import sys


def main(argv=None):
  logger = logging.getLogger('remote_kernel.main')

  script = 'N/A'
  try:
    if argv is None:
      argv = sys.argv[1:]

    if len(argv) == 0:
      logger.error('Cannot start without command line arguments')
      return 1

    elif argv[0].startswith('-'):  # if first argument is not a script select: start kernel
      from remote_kernel.start import parse_args
      script = 'Start kernel'
      logger.debug('Starting Start script with args %s', argv)
      return parse_args(argv)
    else:
      parser = argparse.ArgumentParser(add_help=False)
      parser.add_argument('cmd', choices=['install', 'from-spec'])
      args, remainder = parser.parse_known_args(argv)

      if args.cmd == 'install':
        from remote_kernel.install import parse_args
        script = 'Install kernel'
        logger.debug('Starting Install script with args %s', remainder)
        return parse_args(remainder)
      elif args.cmd == 'from-spec':
        from remote_kernel.start import get_spec
        script = 'Start kernel from kernel_spec file'
        logger.debug('Starting kernel from spec file')
        return get_spec(remainder)
      return 0
  except Exception:
    logger.error('%s error', script, exc_info=True)
    return 1


if __name__ == '__main__':
  exit(main())
