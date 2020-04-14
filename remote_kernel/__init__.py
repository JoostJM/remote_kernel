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

from collections import OrderedDict
import logging

logger = logging.getLogger('remote_kernel')
logger.propagate = False
hndlr = logging.StreamHandler()
hndlr.setFormatter(logging.Formatter('%(name)s %(levelname)-.1s: %(message)s'))

logger.addHandler(hndlr)
logger.setLevel(logging.INFO)
hndlr.setLevel(logging.INFO)

def get_resource_dir():
  import os
  resource_dir = os.path.join(os.path.dirname(__file__), 'resources')
  return os.path.abspath(resource_dir)

# argument template for starting up an IPyKernel without supplying a connection file
# arguments to fill this template are read from the connection file which remains on
# the local computer. It only ignores the kernel_name argument from the connection file.
CMD_ARGS = OrderedDict([
  ('--ip', '"%(ip)s"'),
  ('--stdin', '%(stdin_port)i'),
  ('--shell', '%(shell_port)i'),
  ('--iopub', '%(iopub_port)i'),
  ('--hb', '%(hb_port)i'),
  ('--control', '%(control_port)i'),
  ('--Session.signature_scheme', '"%(signature_scheme)s"'),
  ('--Session.key', '"b\'%(key)s\'"'),  # Py3 compat, ensure the key is interpreted as a byte string
  ('--transport', '"%(transport)s"')
])
