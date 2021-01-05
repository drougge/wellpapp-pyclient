from __future__ import print_function

from wellpapp import Client

def main(arg0, argv):
	if len(argv) < 2:
		print("Usage:", arg0, "rotation post-spec [post-spec [..]]")
		return 1

	new_r = int(argv[0])
	if abs(new_r) not in (90, 180, 270):
		print("Can only handle 90, 180 or 270 degrees rotation")
		return 1

	def rotate(spec):
		global bad
		md5 = client.postspec2md5(spec)
		post = None
		if md5:
			post = client.get_post(md5, wanted = ["rotate", "ext", "width", "height"])
		if not post:
			print(spec + ": Post not found")
			bad = 1
			return
		r = int(post.get("rotate", 0))
		if r not in (0, 90, 180, 270):
			print(spec + ": Invalid current rotation")
			bad = 1
			return
		dest_r = (r + new_r) % 360
		props = {"rotate": dest_r}
		if abs(new_r) in (90, 270):
			props["width"], props["height"] = post["height"], post["width"]
		client.save_thumbs(md5, None, post.ext, dest_r, True)
		client.modify_post(md5, **props)

	client = Client()
	client.begin_transaction()
	bad = 0

	for spec in argv[1:]:
		rotate(spec)
	return bad
