from __future__ import print_function

from wellpapp import Client

def main(arg0, argv):
	if len(argv) != 2:
		print("Usage:", arg0, "tagname alias")
		return 1
	client = Client()
	tag = client.find_tag(argv[0])
	if tag:
		client.add_alias(argv[1], tag)
	else:
		print("No such tag", argv[0])
		return 1
