from __future__ import print_function

import sys
import os
from importlib import import_module

def main():
	arg0 = os.path.basename(sys.argv[0])
	argv = sys.argv[1:]
	def usage(fh):
		print("Usage:", arg0, "command [args]", file=fh)
		print(file=fh)
		print("Available commands:", file=fh)
		commands = dict(
			add='add posts',
			findtag='search for tags',
			fsck='check db',
			fusefs='mount filesystem',
			implies='add tag implication',
			mergetags='merge tags',
			mkalias='make tag alias',
			mktag='make tag',
			modtag='modify tag',
			order='order tag',
			replace='replace file',
			rmalias='delete alias',
			rmpost='delete post',
			rotate='rotate post',
			setprop='set post properties',
			show='show post/tag',
			tag='tag post',
			tagwindow='tagging gui',
		)
		try:
			import fuse; fuse
		except ImportError:
			del commands['fusefs']
		tmpl = '    %%-%ds  %%s' % (max(len(cmd) for cmd in commands),)
		for cmd, desc in sorted(commands.items()):
			print(tmpl % (cmd, desc,), file=fh)
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
