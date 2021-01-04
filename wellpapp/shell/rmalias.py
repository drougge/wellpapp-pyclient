from __future__ import print_function

from wellpapp import Client

def main(arg0, argv):
	if len(argv) != 1:
		print("Usage:", arg0, "alias")
		return 1
	client = Client()
	client.remove_alias(argv[0])
