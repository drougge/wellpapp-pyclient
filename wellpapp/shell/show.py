from __future__ import print_function

from sys import version_info
from wellpapp import Client
from re import match
from os import readlink, stat
from optparse import OptionParser

if version_info[0] > 2:
	unicode = str

def main(arg0, argv):
	def implfmt(impl):
		data = client.get_tag(impl.guid, with_prefix=True)
		a = [data.pname, unicode(impl.prio)]
		if impl.filter:
			a.append(impl.filter[0] + unicode(impl.filter[1]))
			a.append(unicode(impl.value))
		elif impl.value:
			a.append(u":")
			a.append(unicode(impl.value))
		return u"\n\t" + u"\t".join(a)

	def show_implies(guid, heading, reverse):
		impl = client.tag_implies(guid, reverse)
		if impl: print(heading + u"".join(sorted(map(implfmt, impl))))

	def fmt_tag(tag):
		if tag.value:
			val = u" = " + unicode(tag.value)
		else:
			val = u""
		return tag.pname + val

	def show_post(m, short=False, show_thumbs=False):
		post = client.get_post(m, True, ["tagname", "tagdata", "datatags", "ext", "created", "width", "height"])
		if not post:
			print("Post not found")
			return 1
		print(m + " created " + post.created.localtimestr())
		if not short:
			print(post["width"], "x", post["height"], post["ext"])
		try:
			path = readlink(client.image_path(m))
			try:
				path += " (%d bytes)" % (stat(path).st_size,)
			except OSError:
				path += " (MISSING)"
		except Exception:
			path = "MISSING"
		print("Original file: " + path)
		if show_thumbs:
			jpeg, png = client.thumb_fns(m, post.ext)
			for kind, lst in (("jpeg", jpeg), ("png", png)):
				for fn, z in lst:
					try:
						extra = "%d bytes" % (stat(fn).st_size,)
					except OSError:
						extra = "MISSING"
					print("Thumb %dpx %s: %s (%s)" % (z, kind, fn, extra))
		if short: return 0
		tags = [fmt_tag(t) for n, t in sorted(post.datatags.items())]
		if tags:
			print("Data:\n\t", end="")
			print(u"\n\t".join(sorted(tags)))
		print("Tags:\n\t", end="")
		tags = [fmt_tag(t) for t in post.fulltags] + [fmt_tag(t) for t in post.weaktags]
		print(u"\n\t".join(sorted(tags)))
		tags = [fmt_tag(t) for t in post.implfulltags] + [fmt_tag(t) for t in post.implweaktags]
		if tags:
			print("Implied:\n\t", end="")
			print(u"\n\t".join(sorted(tags)))
		rels = client.post_rels(m)
		if rels:
			print("Related posts:\n\t" + "\n\t".join(rels))
		return 0

	def show_tag(name, short=False, show_thumbs=False):
		guid = client.find_tag(name)
		if not guid and match(r"(?:\w{6}-){3}\w{6}", name):
			guid = name
		if not guid:
			print("Tag not found")
			return 1
		data = client.get_tag(guid)
		if not data:
			print("Tag not found")
			return 1
		print("Tag:", data["name"])
		if data.alias:
			if len(data.alias) == 1:
				print("Aliases:", data.alias[0])
			else:
				print("Aliases:")
				for a in sorted(data.alias):
					print("\t" + a)
		print("GUID:", guid)
		print("Type:", data["type"])
		if "valuetype" in data and data["valuetype"]:
			print("Valuetype:", data["valuetype"])
		if short: return 0
		print(data["posts"], "posts")
		print(data["weak_posts"], "weak posts")
		show_implies(guid, u"Implies:", False)
		show_implies(guid, u"Implied by:", True)
		flags = [f for f in data if data[f] is True]
		if flags:
			print("Flags:\n\t" + "\n\t".join(flags))
		return 0

	p = OptionParser(usage="Usage: %prog [-qt] post-spec or tagname [...]", prog=arg0)
	p.add_option("-q", "--short",
	             action="store_true",
	             help="Short output format"
	            )
	p.add_option("-t", "--show-thumbs",
	             action="store_true",
	             help="Show thumb paths"
	            )
	opts, args = p.parse_args(argv)
	if not args:
		p.print_help()
		return 1
	client = Client()
	ret = 0
	for object in args:
		object = client.postspec2md5(object, object)
		if match(r"^[0-9a-f]{32}$", object):
			ret |= show_post(object, **opts.__dict__)
		else:
			ret |= show_tag(object, **opts.__dict__)
		if len(args) > 1: print()
	return ret
