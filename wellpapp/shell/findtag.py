from __future__ import print_function

from sys import exit
from wellpapp import Client
from argparse import ArgumentParser
from operator import itemgetter

def main(arg0, argv):
	parser = ArgumentParser(prog=arg0)
	parser.add_argument("-f", "--fuzzy", action="store_true", help="Fuzzy matching")
	parser.add_argument("-a", "--anywhere", action="store_true", help="Match anywhere")
	parser.add_argument("-s", "--short", action="store_true", help="Short listing (just tagnames)")
	parser.add_argument("-i", "--implies", action="append", default=[], metavar="TAG", help="Only find tags that imply this tag")
	parser.add_argument("-t", "--type", action="append", default=[], help="Only tags of this type")
	parser.add_argument(metavar="partial-tag-name", dest="part")
	args = parser.parse_args(argv)

	client = Client()

	def short(tag):
		print(tag.name)

	def long(tag):
		names = [tag.name] + sorted(tag.alias)
		props = [str(p) for p in (tag.type, tag.posts, tag.weak_posts)]
		if tag.valuetype: props.insert(0, "valuetype:" + tag.valuetype)
		print(" ".join(names + props))

	def parse_tags(lst):
		for name in lst:
			guid = client.find_tag(name, with_prefix=True)
			if not guid:
				print("Tag %s not found" % (name,))
				exit(1)
			yield guid

	def collect_implies(guid, res):
		for impl in client.tag_implies(guid):
			if impl.guid not in res:
				res.add(impl.guid)
				if not impl.guid.startswith("-"):
					collect_implies(impl.guid, res)

	match = "F" if args.fuzzy else "E"
	where = "P" if args.anywhere else "I"
	cmd = match + "A" + where
	printer = short if args.short else long
	implies = set(parse_tags(args.implies))
	tagtypes = set(args.type)

	for tag in sorted(client.find_tags(cmd, args.part), key=itemgetter('name')):
		if implies:
			tag_implies = set()
			collect_implies(tag.guid, tag_implies)
			if implies - tag_implies:
				continue
		if tagtypes:
			if tag.type not in tagtypes:
				continue
		printer(tag)
