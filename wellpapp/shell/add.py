from __future__ import print_function
from __future__ import unicode_literals

from hashlib import md5
from PIL import Image
from io import BytesIO
from os.path import basename, dirname, realpath, exists, lexists, join, sep
from os import readlink, symlink, unlink, stat
from wellpapp import Client, VTstring, make_pdirs, RawWrapper, identify_raw, ExifWrapper, raw_exts, VTgps
from struct import unpack
from multiprocessing import Lock, cpu_count, Queue, Process, Manager
from traceback import print_exc
from sys import version_info, exit
from argparse import ArgumentParser

if version_info[0] == 2:
	from Queue import Empty
	from io import open
else:
	from queue import Empty

def determine_filetype(data):
	data2 = data[:2]
	data3 = data[:3]
	data4 = data[:4]
	data6 = data[:6]
	data8 = data[:8]
	data16 = data[:16]
	data48 = data[4:8]
	if data3 == b"\xff\xd8\xff":
		# probably jpeg, but I like to be careful.
		if data[-2:] == b"\xff\xd9":
			# this is how a jpeg should end
			return "jpeg"
		if data[-4:] == b"SEFT" and b"SEFH" in data[-100:] and b"\xff\xd9\x00\x00" in data[-256:]:
			# samsung phones like to add this crap after the jpeg.
			# no idea why it's not in a makernote, but here we are.
			return "jpeg"
	if data6 in (b"GIF87a", b"GIF89a") and data[-1:] == b";":
		return "gif"
	if data8 == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
		return "png"
	if data2 == b"BM" and ord(data[5:6]) < 4 and data[13:14] == b"\x00":
		return "bmp"
	if data4 in (b"MM\x00*", b"II*\x00", b"IIRO", b"IIU\x00", b"FOVb", b"FUJI",):
		return identify_raw(BytesIO(data))
	flen = unpack("<I", data48)[0]
	dlen = len(data)
	if data3 == b"FWS" and flen == dlen:
		return "swf"
	if data3 == b"CWS" and dlen < flen < dlen * 10:
		return "swf"
	if data4 == b"RIFF" and data[8:12] == b"AVI " and flen < dlen < flen * 1.4 + 10240:
		return "avi"
	if data3 == b"\x00\x00\x01":
		return "mpeg"
	if data4 == b"\x1a\x45\xdf\xa3" and b"matroska" in data[:64]:
		return "mkv"
	if data4 == b"\x1a\x45\xdf\xa3" and b"webm" in data[:64]:
		return "webm"
	if data4 == b"OggS" and data[28:35] in (b"\x01video\x00", b"\x80theora"):
		return "ogm"
	if data16 == b"\x30\x26\xb2\x75\x8e\x66\xcf\x11\xa6\xd9\x00\xaa\x00\x62\xce\x6c":
		return "wmv"
	if data48 in (b"ftyp", b"mdat"):
		blen = unpack(">I", data4)[0]
		if data[blen + 4:blen + 8] == b"moov":
			if data48 == b"mdat" or data[8:10] == b"qt":
				return "mov"
			else:
				return "mp4"
		if blen < 100 and (data[8:10] == b"qt" or data[8:12] in (b"3gp4", b"\0\0\0\0")):
			return "mov"
		if data[0:1] == b"\x00" and data[8:12] in (b"mp41", b"mp42", b"isom"):
			return "mp4"
	if data48 == b"moov" and data[12:16] in (b"mvhd", b"cmov"):
		if b"\x00" in (data[0:1], data[8:9], data[16:17]):
			return "mov"
	if data4 == b"FLV\x01" and data[5:9] == b"\x00\x00\x00\x09" and ord(data[13:14]) in (8, 9, 18):
		return "flv"
	if data.startswith(b"%PDF-"):
		return "pdf"

def _gpspos(pos, ref):
	pos = pos[0] + pos[1] / 60 + pos[2] / 3600
	if ref and ref[0] in "SWsw":
		pos = -pos
	return "%.7f" % (pos,)

def fmt_tagvalue(v):
	if not v: return ""
	if isinstance(v, VTstring):
		return "=" + repr(v.str)
	else:
		return "=" + v.str

def flash_dimensions(data):
	sig = data[:3]
	assert sig in (b"FWS", b"CWS")
	data = data[8:]
	if sig == b"CWS":
		from zlib import decompress
		data = decompress(data)
	pos = [0] # No "nonlocal" in python2
	def get_bits(n, signed=True):
		val = 0
		for i in range(n):
			sh = 7 - (pos[0] % 8)
			bit = (ord(data[pos[0] // 8]) & (1 << sh)) >> sh
			if i == 0 and signed and bit:
				val = -1
			val = (val << 1) | bit
			pos[0] += 1
		return val
	bpv = get_bits(5, False)
	xmin = get_bits(bpv)
	xmax = get_bits(bpv)
	ymin = get_bits(bpv)
	ymax = get_bits(bpv)
	return [int(round(v / 20.0)) for v in (xmax - xmin, ymax - ymin)]

def mplayer_dimensions(fn):
	from subprocess import Popen, PIPE, STDOUT
	p = Popen(["mediainfo", "--Inform=Video;%Width% %Height%", fn],
	           stdout=PIPE, stderr=STDOUT, close_fds=True)
	data = p.communicate()[0].split()
	return tuple(map(int, data))

movie_ft = set("swf avi mpeg mkv ogm mp4 wmv flv mov webm".split())

def pdf_image(fn):
	from subprocess import check_output
	cmd = ["gs",
	       "-q",
	       "-sDEVICE=pngalpha",
	       "-sOutputFile=-",
	       "-dFirstPage=1",
	       "-dLastPage=1",
	       "-dBATCH",
	       "-dNOPAUSE",
	       "-dSAFER",
	       "-r100",
	       fn,
	]
	return check_output(cmd, close_fds=True)


def main(arg0, argv):
	def needs_thumbs(m, ft):
		if args.regenerate_thumbnail: return True
		jpeg_fns, png_fns = client.thumb_fns(m, ft)
		for fn, z in jpeg_fns + png_fns:
			if not exists(fn): return True

	def exif2tags(exif, tags):
		cfg = client.cfg
		if "lenstags" in cfg:
			lenstags = cfg.lenstags.split()
			for lt in lenstags:
				if lt in exif:
					v = exif[lt]
					if isinstance(v, tuple) or hasattr(v, "pop"):
						v = " ".join([str(e) for e in v])
					lt = "lens:" + lt + ":" + v
					if lt in cfg:
						tags.add_spec(cfg[lt])
		try:
			make = exif["Exif.Image.Make"].strip()
			model = exif["Exif.Image.Model"].strip()
			cam = "camera:" + make + ":" + model
			if cam in cfg:
				tags.add_spec(cfg[cam])
		except Exception:
			pass
		if "set_tags" in cfg:
			for st in cfg.set_tags.split():
				tn, et = st.split("=", 1)
				if et in exif:
					v = exif[et]
					if ("FocalLength" in et or "FNumber" in et) and not v:
						continue
					tags.add_spec(tn + "=" + str(exif[et]))
		if "Exif.GPSInfo.GPSLatitude" in exif:
			lat = _gpspos(exif["Exif.GPSInfo.GPSLatitude"], exif["Exif.GPSInfo.GPSLatitudeRef"])
			lon = _gpspos(exif["Exif.GPSInfo.GPSLongitude"], exif["Exif.GPSInfo.GPSLongitudeRef"])
			if "Exif.GPSInfo.GPSAltitude" in exif:
				from fractions import Fraction
				alt = Fraction(exif["Exif.GPSInfo.GPSAltitude"])
				if "Exif.GPSInfo.GPSAltitudeRef" in exif and float(exif["Exif.GPSInfo.GPSAltitudeRef"]):
					alt = -alt
				gps = VTgps("%s,%s,%.1f" % (lat, lon, alt))
			else:
				gps = VTgps("%s,%s" % (lat, lon))
			tags.add(("aaaaaa-aaaadt-faketg-gpspos", gps))
		if args.override_tags:
			tags.add(("aaaaaa-aaaac8-faketg-bddate", exif.date(args.timezone)))

	class tagset(set):
		def add(self, t):
			guid, val = t
			prefix = ""
			if guid[0] in "~-":
				prefix = guid[0]
				guid = guid[1:]
			chk = (guid, "~" + guid)
			rem = None
			for v in self:
				if v[0] in chk: rem = v
			if rem: self.remove(rem)
			if prefix != "-": set.add(self, (prefix + guid, val))

		def difference(self, other):
			other = {(guid, None if val is None else val.format()) for guid, val in other}
			for guid, val in self:
				if (guid, None if val is None else val.format()) not in other:
					yield guid, val

		def add_spec(self, s):
			try:
				with lock:
					t = client.parse_tag(s)
			except Exception:
				print("Failed to parse: " + s)
				return
			if t:
				self.add(t)
			else:
				print("Unknown tag " + s)

		def update(self, l):
			[self.add_spec(s) for s in l]

		def update_tags(self, l):
			[self.add((t.pguid, t.value)) for t in l]

	def find_tags(fn):
		path = "/"
		tags = tagset()
		if client.cfg.tags_filename:
			for dir in dirname(fn).split(sep):
				path = join(path, dir)
				TAGS = join(path, client.cfg.tags_filename)
				if exists(TAGS):
					tags.update(open(TAGS, "r", encoding="utf-8").readline().split())
		if args.tags_from_fn:
			tags.update(basename(fn).split()[:-1])
		return tags

	def record_filename(m, fn):
		dn = client.image_dir(m)
		rec_fn = join(dn, "FILENAMES")
		known = {}
		if exists(rec_fn):
			for line in open(rec_fn, "r", encoding="utf-8", errors="backslashreplace"):
				r_m, r_fn = line[:-1].split(" ", 1)
				known.setdefault(r_m, []).append(r_fn)
		if m not in known or fn not in known[m]:
			with lock:
				with open(rec_fn, "a", encoding="utf-8", errors="backslashreplace") as fh:
					fh.write(m + " " + fn + "\n")

	def generate_cache(m, fn, jz):
		cache_fn = client.cfg.image_base + "/cache"
		if exists(cache_fn):
			s = stat(fn)
			z = s.st_size
			mt = int(s.st_mtime)
			if jz:
				l = "1 %s %d %d %d %s\n" % (m, z, mt, jz, fn)
			else:
				l = "0 %s %d %d %s\n" % (m, z, mt, fn)
			with lock:
				with open(cache_fn, "a", encoding="utf-8") as fh:
					fh.write(l)

	def add_image(fn, m, data, warn_q):
		fn = realpath(fn)
		with lock:
			post = client.get_post(m, True)
		if post:
			ft = post.ext
		else:
			ft = args.type or determine_filetype(data)
		assert ft
		p = client.image_path(m)
		if lexists(p):
			ld = readlink(p)
			is_wpfs = False
			try:
				dot = fn.rindex(".")
				if "/" not in fn[dot:]:
					bare_fn = fn[:fn.rindex(".")]
					if m == bare_fn[-32:] and readlink(bare_fn)[-32:] == m:
						is_wpfs = True # probably
			except (OSError, ValueError):
				pass
			if is_wpfs:
				if not args.quiet:
					print("Not updating", fn, "because this looks like a wellpappfs")
			elif exists(p):
				if fn != ld:
					if not args.dummy: record_filename(m, fn)
					if not args.quiet:
						print("Not updating", m, fn)
			else:
				if args.dummy:
					if not args.quiet: print("Would have updated", m, fn)
				else:
					record_filename(m, ld)
					if not args.quiet: print("Updating", m, fn)
					unlink(p)
		do_cache = False
		if not lexists(p) and not args.dummy:
			make_pdirs(p)
			symlink(fn, p)
			do_cache = True
		if not post or needs_thumbs(m, ft):
			do_cache = True
			if ft in movie_ft:
				if not args.thumb_src:
					print("Can't generate " + ft + " thumbnails")
					exit(1)
				if not post:
					if ft == "swf":
						w, h = flash_dimensions(data)
					else:
						w, h = mplayer_dimensions(fn)
			else:
				if ft == "pdf":
					data = pdf_image(fn)
				datafh = RawWrapper(BytesIO(data))
				try:
					img = Image.open(datafh)
				except IOError:
					if args.thumb_src:
						img = Image.open(RawWrapper(open(args.thumb_src, "rb")))
						print("Warning: taking dimensions from thumb source")
					else:
						raise
				w, h = img.size
		if do_cache and not args.dummy:
			if ft in raw_exts:
				jfh = RawWrapper(BytesIO(data), True)
				jfh.seek(0, 2)
				jz = jfh.tell()
				jfh.close()
			else:
				jz = None
			generate_cache(m, fn, jz)
		exif = ExifWrapper(fn)
		if not post:
			rot = exif.rotation()
			if rot in (90, 270): w, h = h, w
			kw = {"md5": m, "width": w, "height": h, "ext": ft}
			if rot >= 0: kw["rotate"] = rot
			date = exif.date(args.timezone)
			if date:
				kw["imgdate"] = date
			if args.dummy:
				print("Would have created post " + m)
			else:
				with lock:
					client.add_post(**kw)
		if needs_thumbs(m, ft):
			if args.dummy:
				print("Would have generated thumbs for " + m)
			else:
				rot = exif.rotation()
				if args.thumb_src:
					img = Image.open(RawWrapper(open(args.thumb_src, "rb")))
				client.save_thumbs(m, img, ft, rot, args.regenerate_thumbnail)
		full = tagset()
		weak = tagset()
		with lock:
			post = client.get_post(m, True)
		posttags = tagset()
		if post:
			posttags.update_tags(post.tags)
		filetags = find_tags(fn)
		try:
			exif2tags(exif, filetags)
		except Exception:
			print_exc()
			warn_q.put(fn + ": failed to set tags from exif")
		for guid, val in filetags.difference(posttags):
			if guid in post.tags and not args.override_tags:
				print("Not overriding value on", post.tags[guid].pname)
			elif guid[0] == "~":
				weak.add((guid[1:], val))
			else:
				full.add((guid, val))
		if full or weak:
			with lock:
				if args.no_tagging or args.dummy:
					full = [client.get_tag(g).name + fmt_tagvalue(v) for g, v in full]
					weak = ["~" + client.get_tag(g).name + fmt_tagvalue(v) for g, v in weak]
					print("Would have tagged " + m + " " + " ".join(full + weak))
				else:
					client.tag_post(m, full, weak)

	parser = ArgumentParser(prog=arg0)
	parser.add_argument('-v', '--verbose', action="store_true")
	parser.add_argument('-q', '--quiet', action="store_true")
	parser.add_argument('-f', '--regenerate-thumbnail', action="store_true")
	parser.add_argument('-n', '--no-tagging', action="store_true", help='prints what would have been tagged')
	parser.add_argument('-g', '--tags-from-fn', action="store_true", help='generate tags from filename (all words except last)')
	parser.add_argument('-d', '--dummy', action="store_true", help='only print what would be done')
	parser.add_argument('-t', '--thumb-src', help='post or file to generate thumb from')
	parser.add_argument('-T', '--type', help='override file type detection')
	parser.add_argument('-z', '--timezone', help='timezone to assume EXIF dates are in (+-HHMM format)')
	parser.add_argument('-o', '--override-tags', action="store_true", help='override existing tag values (from exif, TAGS (and filename))')
	parser.add_argument('filename', nargs='+')
	args = parser.parse_args(argv)
	if args.thumb_src:
		args.regenerate_thumbnail = True

	client = Client()
	lock = Lock()

	if args.thumb_src:
		if len(args.filename) > 1:
			print("Only add one post with -t")
			exit(1)
		if not exists(args.thumb_src):
			m = client.postspec2md5(args.thumb_src)
			args.thumb_src = client.image_path(m)
		if not exists(args.thumb_src):
			print("Thumb source not found")
			exit(1)
	client.begin_transaction()
	q = Queue()
	bad_q = Queue()
	warn_q = Queue()
	for td in args.filename:
		q.put(td)
	in_progress = Manager().dict() # no set available
	def worker():
		while True:
			try:
				i = q.get(False)
			except Empty:
				break
			try:
				if isinstance(i, tuple):
					i, m = i
				else:
					if args.verbose:
						print(i)
					data = open(i, "rb").read()
					m = md5(data).hexdigest()
				with lock:
					if m in in_progress:
						# try again later, keep the md5
						# (don't just skip it, because tags may be different)
						q.put((i, m))
						continue
					in_progress[m] = True
				try:
					add_image(i, m, data, warn_q)
				finally:
					with lock:
						del in_progress[m]
			except Exception:
				print_exc()
				bad_q.put(i)
	# I would have used Pool, but it's completely broken if you ^C
	ps = [Process(target=worker) for _ in range(min(cpu_count(), len(args.filename)))]
	for p in ps:
		p.daemon = True
		p.start()
	for p in ps:
		p.join()
	client.end_transaction()
	def print_q(q, msg):
		if not q.empty():
			print()
			print(msg)
			while True:
				try:
					print("\t%s" % (q.get(False),))
				except Empty:
					break
	print_q(warn_q, "Files with warnings:")
	print_q(bad_q, "Failed files:")
