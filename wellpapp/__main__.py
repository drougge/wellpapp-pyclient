from __future__ import print_function

import sys
from importlib import import_module

def main():
	arg0 = sys.argv[0]
	argv = sys.argv[1:]
	def usage(fh):
		print("Usage:", arg0, "command [args]", file=fh)
	if len(argv) < 1:
		usage(sys.stderr)
		return 1
	command = argv[0]
	argv = argv[1:]
	if command in ('-h', '--help'):
		usage(sys.stdout)
		return 0
	modname = 'wellpapp.shell.' + command
	if command.startswith('_') or '.' in command:
		modname = 'wellpapp._' # anything that won't be found
	try:
		mod = import_module(modname)
	except ModuleNotFoundError as e:
		if e.name != modname:
			raise
		print("Unknown command", command, file=sys.stderr)
		return 1
	return mod.main('%s %s' % (arg0, command), argv)

if __name__ == '__main__':
	sys.exit(main())
