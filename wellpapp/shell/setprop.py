from __future__ import print_function

from wellpapp import Client

def main(arg0, argv):
	if len(argv) < 2:
		print("Usage:", arg0, "post-spec property=value [property=value [...]]")
		print("or:", arg0, "-r property=value post-spec [post-spec [...]]")
		print("Properties as specified in decimal format where possible.")
		print("(So width=42, not width=2a)")
		return 1

	def set_prop(props, spec):
		prop, val = spec.split("=", 1)
		props[prop] = val

	client = Client()
	props = {}
	if argv[0] == "-r":
		set_prop(props, argv[1])
		client.begin_transaction()
		for post in argv[2:]:
			md5 = client.postspec2md5(post)
			if not md5 or not client.get_post(md5):
				print(post, "not found")
				continue
			try:
				client.modify_post(md5, **props)
			except Exception:
				print("Failed to set on", post)
		client.end_transaction()
	else:
		md5 = client.postspec2md5(argv[0])
		if not md5 or not client.get_post(md5):
			print("Post not found")
			return 1
		for prop in argv[1:]:
			set_prop(props, prop)
		if props:
			client.modify_post(md5, **props)
