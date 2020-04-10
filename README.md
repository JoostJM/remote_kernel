# Remote Kernel
Remote kernel is a pure-python package that sets up an ssh 
connection with port forwarding to a remote host, and starts
up an IPyKernel on that host. This allows a locally running 
instance of Jupyter or Spyder to easily run code on a remote 
server. Moreover, this can be installed as a jupyter 'kernel',
allowing you to use this just as easily as you would use a 
local kernel!

## Installation

To install remote_kernel, run: 

`pip install git+https://github.com/JoostJM/remote_kernel`

## Usage

Remote kernel is intended to spawn kernels on remote servers
for use in both Jupyter notebooks and Spyder.

### Jupyter

Install the remote kernel:

`python -m remote_kernel install <ssh_host> [Options]`

To obtain a list of options for the installation, run:

`python -m remote_kernel install --help`

### Spyder

To use the remote kernel in spyder, a kernel needs to be
manually started and then connected to from spyder.

To start the remote kernel:

`python -m remote_kernel <ssh_host> [Options]`

Again, options can be listed using:

`python -m remote_kernel <ssh_host> [Options]`

If successfull, this will print a message like this:

```
INFO:remote_kernel.start:Remote Kernel started. To connect another client to this kernel, use:
	--existing kernel-<user>@<host>.json
```

Copy this name (or just the `<user>@<host` part) and use it
to [connect to a local existing kernel in spyder](https://docs.spyder-ide.org/ipythonconsole.html#connect-to-an-external-kernel).
Even though the kernel is running remotely, and we're using SSH, 
connect to it as if it were running locally (i.e. don't check the SSH box).
*N.B. The convenience function with the id expansion also works using
the `<user>@<host>` part, even though it's not a number.*

*N.B. By default, remote_kernel starts regular ipykernels on the remote
server, but this can be overridden using the `-c` command line option.*

## Acknowledgements/Requirements

This package relies heaviliy on the following packages

- [paramiko](https://github.com/paramiko/paramiko), 
  for setting up the ssh connection.
- [sshtunnel](https://github.com/pahaz/sshtunnel), 
  for creating the forwarding tunnels for the kernel ports.
