Run as any fuse filesystem. Needs the wellpapp python client lib and
fuse-python (at least version 1.0.0 if you use python 3). On python 3
all paths (both your actual files and search paths in this FS) need to
be valid utf-8.

Directories are searches.

Provides .thumblocal so viewers that use it don't have to generate
thumbnails.

You can separate search terms with spaces or as subdirs. Note that all
parent searches for directory separated searches are performed, which can
be slow. Searches are however limited to 10000 results by default, so it's
not that bad.

You can sort searches by specifying O:sort-spec (either a tag name (sorting
by the value of that tag) or the special word group which sorts by the
group ordering of the first tag in the search). This prefixes image names
with a sequence number that your viewer can hopefully sort by. Use
O:-sort-spec to reverse the sort order.

You can also specify R:first:last to show only a range of results. This is
mostly useful for sorted searches, but works on any search. What you end up
with without sorting is stable as long as nothing in tagged, but otherwise
undefined. This is still useful to override the default limit of 10000
results.

Specifying C: (for "clean") will give your results as symlinks with no
suffix (just the post ID).

Searches are cached for 30 seconds, to keep the slowness down a bit.

A more serious source of slownes in actual use is waiting for your disk to
seek when your image viewer stats all the files in a result set. Even in
the ideal case you'll get at least two seeks for every file (unless cached
of course), one for the symlink and one for the file. In practice it's
more. This can now be avoiding by keeping a cache for all files in the
filesystem, read at startup. (Not much to be done about waiting for
thumbnails, but any decent viewer will do that without blocking.)

I recommend you use such a cache. Generate it with db_make_cache.py from
pyclient, and db_add.py will keep it up to date automatically. The
filsystem uses a cache if available on startup.

Posts are returned as symlinks (to something in image_base) without a
cache, and as normal files with a cache. You can reference a bare post ID
(without suffix) to always get a symlink.

If you give -o raw2jpeg you get extracted JPEGs with the same base name as
the RAW files. (This requires a cache file.)

You can also give -o default_search="some search expression" to have some
base expression that you base all your searches on. Specifying a tag in the
default_search explicitly ignores it from the default search, and
specifying N: ("no default") ignores the whole default search. My use for
this is having a (word valuetype) tag "replaced" for when I make a new
version of something, and having default_search=-!replaced (! so I can set
it weakly if I still want to see the replaced post).
