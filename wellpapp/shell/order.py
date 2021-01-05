from __future__ import print_function

from wellpapp import Client

def main(arg0, argv):
	if len(argv) < 2:
		print("Usage:", arg0, "tagname post-spec [post-spec [...]]")
		return 1

	client = Client()
	data = {}
	tag = client.find_tag(argv[0], data)
	if not tag:
		print("Tag not found")
		return 1
	if data["weak_posts"]:
		print("Can't order a tag with weak posts")
		return 1
	posts = map(client.postspec2md5, argv[1:])
	wtag = "~" + tag
	for post, spec in zip(posts, argv[1:]):
		if post:
			post = client.get_post(post, True)
		if not post:
			print("Post " + spec + " not found")
			return 1
		if tag in post.implfulltags or tag in post.implweaktags:
			print("Post " + spec + " has tag implied.")
			print("Can't order a tag with implied posts.")
			return 1
		if tag not in post.tags.guids:
			print("Post " + spec + " doesn't have tag.")
			return 1
	client.order(tag, posts)
