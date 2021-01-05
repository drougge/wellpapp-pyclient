from __future__ import print_function

from wellpapp import Client

def main(arg0, argv):
	if len(argv) not in (2, 3, 4):
		print("Usage:", arg0, "tag new_name [new_type [new_valuetype]]")
		return 1

	a = {}
	if len(argv) > 2:
		a["type"] = argv[2]
	if len(argv) > 3:
		a["valuetype"] = argv[3]

	client = Client()
	tag = client.find_tag(argv[0])
	a["name"] = argv[1]
	if not tag:
		print("Tag not found")
		return 1
	client.mod_tag(tag, **a)
