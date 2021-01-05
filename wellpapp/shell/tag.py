from __future__ import print_function

from wellpapp import Client

def main(arg0, argv):
	if len(argv) < 2:
		print("Usage:", arg0, "post-spec tag [tag [...]]")
		print("or:", arg0, "-r tag post-spec [post-spec [...]]")
		return 1

	def set_tag(full, weak, remove, tag):
		tag = client.parse_tag(tag)
		if not tag: return
		tag, val = tag
		s = full
		if tag[0] == "-":
			s = remove
			tag = tag[1:]
		elif tag[0] == "~":
			s = weak
			tag = tag[1:]
		s.add((tag, val))
		return True

	client = Client()
	full = set()
	weak = set()
	remove = set()
	if argv[0] == "-r":
		if not set_tag(full, weak, remove, argv[1]):
			print("Tag not found")
			return 1
		client.begin_transaction()
		for post in argv[2:]:
			md5 = client.postspec2md5(post)
			if not md5 or not client.get_post(md5):
				print(post, "not found")
				continue
			try:
				client.tag_post(md5, full, weak, remove)
			except Exception:
				print("Failed to set on", post)
		client.end_transaction()
	else:
		md5 = client.postspec2md5(argv[0])
		if not md5 or not client.get_post(md5):
			print("Post not found")
			return 1
		for tag in argv[1:]:
			if not set_tag(full, weak, remove, tag):
				print("Unknown tag", tag)
		if full or weak or remove:
			client.tag_post(md5, full, weak, remove)
