from __future__ import print_function

from wellpapp import Client

def main(arg0, argv):
	if len(argv) != 2:
		print("Usage:", arg0, "into-tag from-tag")
		return 1

	client = Client()
	into_t, from_t = map(client.find_tag, argv)
	if not into_t or not from_t:
		print("Tag not found")
		return 1
	client.merge_tags(into_t, from_t)
