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

import logging
logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)
for hndlr in logging.getLogger().handlers:
  hndlr.setLevel(logging.INFO)

def get_resource_dir():
  import os
  resource_dir = os.path.join(os.path.dirname(__file__), 'resources')
  return os.path.abspath(resource_dir)
