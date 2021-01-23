Client library and application for the
[wellpapp](https://github.com/drougge/wellpapp) image tagging system.

## Setup

Requires PyGObject and introspection data for GTK 3. For better EXIF
parsing you also want introspection data for GExiv2. On Debian the packages
you want are gir1.2-gtk-3.0 and gir1.2-gexiv2-0.10.

You probably want to install using "`pip install 'wellpapp[all]'`".

Everything here uses .wellpapprc. This is read from ~, from all parents
of currentdir and finaly from currentdir. The last read version of an
option takes effect.

The following options should be specified:

	socket=path to (unix) socket of server
	image_base=path where you want symlinks to imported images
	thumb_base=path where you want thumbnails of imported images
	thumb_sizes=list of max dimensions for thumbnails

Example:

	socket=/wellpapp/socket
	image_base=/wellpapp/images
	thumb_base=/wellpapp/thumbs
	thumb_sizes=128 200

you can also user server + port instead of socket.

There are more options, see the add command for some of them (and the
source for the rest).

## Shell interface

This client provides a "wp" command with these sub commands:

### mktag
Creates a tag. First argument is tag name, second (optional) argument is
tag type.

### mkalias
Creates an alias. First argument is tag name, second is alias name.

### modtag
Modify a tag. First argument is tag name, second is new name, third is
optional new type.

### implies
Creates or removes an implication. First argument is set tag, second is
implied tag, and third is (optional) priority.

### add
Takes filenames. The filename "foo bar blutti.jpg" will recieve the tags
foo and bar (but not blutti), and all tags specified on the first line of
files named TAGS in all parent directories of the file.

Also tags with the lens used, if you have configured the lens to map to a tag.
First set lenstags to include the exif tag you need, then set all the
lens:exiftag:value=tagname pairs you want. Example:
lenstags=Exif.Pentax.LensType
lens:Exif.Pentax.LensType:6 9 0=lens:pentax_fa_20mm_f2.8

You can also set tag values from arbitrary exif tags by specified set_tags in
.wellpapprc. It's a space separated list of tag=exiftag pairs, and the tag is
set if that exiftag exists. Example:
set_tags=aperture=Exif.Photo.FNumber ISO=Exif.Photo.ISOSpeedRatings shutter=Exif.Photo.ExposureTime

add doesn't create tags, but complains if they don't exist.

### tag
Tag an (already imported) image. "tag post-spec tag [tag [...]]" or
"tag -r tag post-spec [post-spec [...]]".

### show
Show information about a post (md5/filename) or a tag (name).

### rmpost
Delete posts. Allows them to be referenced if you give -f.
"rmpost [-f] post-spec [post-spec [..]]"

### replace
Replace the file of a post. The replacement file must not have a post.
Thumbnails are moved, or regenerated with -t.
"replace [-t] post-spec new-file"

### order
Order tags in a post. First argument is the tag, the following arguments are
post-specs that will be ordered as specified. It's not possible to order posts
in a tag that has weak or implied posts. If you specifiy only a single
post-spec this is ordered first.

### mergetag
Merges two tags into one. Takes two tag names as arguments, the second one
will be merged into the first, and all names for it will be recreated as
aliases for the first. Refuses if any posts have both tags at different
strengths, or if anything implies the second tag.

### fsck
Try to determine if your tag data, images and thumbnails are as they should
be. Run it without options for a bit more help. The -s option is only
useful if you suspect a server bug, and it's very slow on larger
collections.

### findtag
Find tags. -a for matching anywhere (not just at the start), -f for fuzzy.

### rotate
Rotate posts. Can rotate 90, 180 or 270 degrees (clockwise) relative
current rotation. Rewrites thumbnails, doesn't touch original file.
First rotation, then post-spec[s].

### tagwindow
A graphical interface for tagging posts. Takes a list of post-specs as
arguments, and lets you tag the posts thus specified. Displays thumbnails
in the size specified first in thumb_sizes in your rc file.

Probably best launched either as "tagwindow *" in a directory with images,
or as an external editor from your image viewer of choice.

You can tab complete tags in the entry field, and drag and drop stuff in
the obvious ways where useful. (Dropping a tag on a thumbnail will tag only
that post, regardless of selection.)

### fusefs
Pseudo-filesystem where directories are searches.
Only available with python-fuse (install with [fuse] or [all] to get it).
See [FUSE.md](FUSE.md) for details.
