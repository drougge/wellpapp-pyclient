#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient, dbcfg, Post
import re
from os.path import exists, dirname
from os import makedirs, stat
import Image
from sys import stdout
from subprocess import call

def usage():
	print "Usage:", argv[0], "[-t] spec-file"
	print "spec-file contains:"
	print "source server port"
	print "destination server port"
	print "max_side"
	print "dest_dir for images"
	print "empty line"
	print "any number of search-specs"
	print "empty line"
	print "any number of include:tag and exclude:tag lines"
	exit(1)

_guid_re = re.compile(r"(?:\w{6}-){3}\w{6}$")
def parse_tag(t, **a):
	g = src_client.find_tag(t, **a)
	if g: t = g
	assert _guid_re.match(t)
	return t

def parse_search(s):
	want = []
	dont = []
	for t in s.split():
		g = parse_tag(t, with_prefix=True)
		if g[0] == "-":
			dont.append(g[1:])
		else:
			want.append(g)
	return dict(guids=want, excl_guids=dont)

class Spec:
	def __init__(self, fh):
		self.src = fh.readline().strip().split()
		self.dest = fh.readline().strip().split()
		self.max_side = int(fh.readline())
		self.dest_dir = fh.readline().strip()
		assert self.dest_dir != "" and exists(self.dest_dir)
		empty = fh.readline().strip()
		assert empty == ""
		line = fh.readline().strip()
		self.search = []
		while line:
			self.search.append(line)
			line = fh.readline().strip()
		self.include = []
		self.exclude = []
		self.fh = fh
		for line in self.fh:
			ie, t = line.strip().split(":", 1)
			if ie == "include":
				self.include.append(t)
			elif ie == "exclude":
				self.exclude.append(t)
			else:
				print "bad line:", line
				exit(1)
	
	def parse(self):
		self.search = map(parse_search, self.search)
		self.include = set(map(parse_tag, self.include))
		self.exclude = set(map(parse_tag, self.exclude))
		both = self.include.intersection(self.exclude)
		if both:
			print "Either exclude or include, not both:"
			print "\n".join(sorted([src_client.get_tag(t).name for t in both]))
			exit(1)

def rotate_image(img, rot):
	rotation = {90: Image.ROTATE_270, 180: Image.ROTATE_180, 270: Image.ROTATE_90}
	if rot not in rotation: return img
	return img.transpose(rotation[rot])

def copyfile(src_fn, dest_fn):
	src_fh = open(src_fn, "rb")
	dest_fh = open(dest_fn, "wb")
	dest_fh.write(src_fh.read())
	dest_fh.close()
	src_fh.close()

def copyexif(src_fn, dest_fn):
	call(["exiftool", "-q", "-overwrite_original", "-tagsFromFile", src_fn,
	      "-Orientation=Normal", dest_fn])

def newer(a, b):
	return stat(a).st_mtime > stat(b).st_mtime

if len(argv) == 2:
	test = False
	fn = argv[1]
elif len(argv) == 3:
	test = True
	fn = argv[2]
	if argv[1] != "-t":
		usage()
else:
	usage()

spec = Spec(file(fn))

src_cfg = dbcfg()
src_cfg.server, src_cfg.port = spec.src
src_client = dbclient(src_cfg)

dest_cfg = dbcfg()
dest_cfg.server, dest_cfg.port = spec.dest
dest_cfg.image_base = spec.dest_dir
dest_cfg.thumb_base = spec.dest_dir
dest_client = dbclient(dest_cfg)

spec.parse()

if not test:
	posts = dest_client._search_post("SP", [])
	if posts:
		print "ERROR: destination server has posts"
		exit(1)
	tags = dest_client.find_tags("EAI", "")
	if tags:
		print "ERROR: destination server has tags"
		exit(1)

posts = {}
for s in spec.search:
	ps = src_client.search_post(wanted=["tagguid", "implied", "ext", "width", "height", "rotate", "imgdate", "created"], **s)[0]
	for p in ps:
		posts[p.md5] = p
posts = posts.values()

bad = set()
for post in posts:
	for t in post.tagguid + post.impltagguid:
		if t[0] in "~-!": t = t[1:]
		if t not in spec.include and t not in spec.exclude:
			bad.add(t)

if bad:
	print "Unspecified tags:"
	names = [src_client.get_tag(t).name for t in bad]
	for n in names:
		print "include:" + n
	for n in names:
		print "exclude:" + n
	exit(1)

if test: exit(0)

z = spec.max_side

print "Copying to destination server.."
dest_client.begin_transaction()

print "Tags.."
ordered = set()
for t in spec.include:
	tag = src_client.get_tag(t)
	dest_client.add_tag(tag.name, tag.type, tag.guid)
	if "alias" in tag:
		for alias in tag.alias:
			dest_client.add_alias(alias, tag.guid)
	if tag.ordered: ordered.add(tag.guid)

for t in spec.include:
	impl = src_client.tag_implies(t)
	if impl:
		for g, p in impl:
			dest_client.add_implies(t, g, p)

print "Posts.."
for post in posts:
	tags = [t for t in post.tagguid if t[-27:] in spec.include]
	data = Post(post)
	del data["tagguid"]
	del data["impltagguid"]
	w, h = data.width, data.height
	if w > z:
		h = h * z // w
		w = z
	if h > z:
		w = w * z // h
		h = z
	data.width, data.height = w, h
	data.rotate = 0
	dest_client.add_post(**data)
	full = [g for g in tags if g[0] != "~"]
	weak = [g[1:] for g in tags if g[0] == "~"]
	dest_client.tag_post(post.md5, full, weak)

rels = set()
print "Relationships.."
for post in posts:
	all = []
	for rel in src_client.post_rels(post.md5) or []:
		if rel + post.md5 not in rels:
			rels.add(post.md5 + rel)
			all.append(rel)
	if all:
		dest_client.add_rels(post.md5, all)

print "Ordering.."
for g in ordered:
	order = [p.md5 for p in src_client.search_post(guids=[g], order=["group"])[0]]
	dest_client.order(g, order)

dest_client.end_transaction()

print "Copying/rescaling images"
count = 0
for post in posts:
	m = post.md5
	w, h = post.width, post.height
	src_fn = src_client.image_path(m)
	dest_fn = dest_client.image_path(m)
	if not exists(dest_fn):
		d = dirname(dest_fn)
		if not exists(d): makedirs(dirname(dest_fn))
		if w > z or h > z or post.rotate > 0:
			img = Image.open(src_fn)
			img.thumbnail((z, z), Image.ANTIALIAS)
			img = rotate_image(img, post.rotate)
			if post.ext == "jpeg":
				opts = dict(quality=90)
			else:
				opts = {}
			img.save(dest_fn, format=post.ext.upper(), **opts)
			if post.ext == "jpeg":
				copyexif(src_fn, dest_fn)
		else:
			copyfile(src_fn, dest_fn)
	src_fn = src_client.thumb_path(m, 200)
	dest_fn = dest_client.thumb_path(m, 200)
	if not exists(dest_fn) or newer(src_fn, dest_fn):
		d = dirname(dest_fn)
		if not exists(d): makedirs(dirname(dest_fn))
		copyfile(src_fn, dest_fn)
	count += 1
	progress = "\r%d/%d" % (count, len(posts))
	stdout.write(progress)
	stdout.flush()
print
