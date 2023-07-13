What is going on in Py_INCREF?
- I don't understand the handling of ob_refcnt_split at all. It says
  it does a "portable saturated add" and I have some intuition of
  how that could work (add the small bytes, if you get zero then bump
  the big bytes) but the actual logic appears to be utter nonsense
  to me; somehow I am badly misunderstanding this simple C code.
- FWIW I'm pretty sure, that via some magic the refcount is behaving
  like a normal int64, with some optimized 32-bit operations. I just
  can't seem to drill down to a reasonable level of detail.


Can I walk through function calls and verify how we clean up every allocated
value? That might be worth doing, but it will be pretty time consuming. Guo
kind of did this at the end of Lecture 3, but in a very quick way and
the Python 2 code wasn't as abstracted. Doing it in the current code will
require a bit more care.

How is `PyNumber_Add` defined? I can easily see its declaration in `abstract.h`,
but I can't figure out where the code actually lives; my current guess is that
it's code generated and all my search tools are too clever to look in generated
code.

It would be nice to figure out how `dir` works! Someone asked during Lecture
6 and Guo didn't know off the top of his head.

I'm fuzzy on what's going on with vectorcallfunc, which also appears to be the
focus of the `tp_call` implementation for normal `PyFunction_Type` functions.
Presumably there is a doc somewhere clearly explaining this.

I need to understand three things related to closures and GC better:
- What is the API CPython uses for cycle detection? How does it find pointers?
- What is tp_weaklistoffset and how do weak references work? How do they
  relate to GC, and why is it useful to have a reference to a maybe-GC'd thing?
- Where is the data for `__closure__` in function objects?

At some point I should revisit class logic, from __build_class__ on
up. I tried in Lecture 7 of Guo, but (a) the Python 2 code was pretty
different and (b) the code is very, very verbose. So I think I'm
going to have to do a dedicated sprint to understand this some other
time.
- Note that any true understanding has to account for both metaclasses and
  descriptors, since those are very much part of what happens. Since these are
  tricky to understand even in pure Python, I expect the C code will be quite
  challenging to read.
- It's probably a good idea to finish clox (the class and inheritance chapters)
  *before* I do a deep dive on Python's handling of this. The approaches are
  almost certainly at least somewhat similar but clox will be greatly simplified.
... Something I should make sure I can trace through eventually is the actual
C-level handling of metaclasses and descriptors, which are two of the trickier
topics in "advanced" python.


I definitely need to do a major push to fully understand generators, which are
much less self-explanatory than they were in Python2 because the lines between
old genrators, "simple" async awaitable types, and async generators are a bit
blurry - all three topics really need to be covered in detail in one pass in
order to understand this well. I'm fairly sure that RealPython resources have
some good discussion of this, and I bet I can also find topic-specific deep dives
in blog posts somewhere.

At some point I do need to read up on the `PREDICT` macro used in the computed-goto
logic and how that works. I believe there's a paper / article from the Lua community
about computed gotos that played a role in inspiring Python.

Someday - but maybe not so soon because it wouldn't help me learn Python
semantics per se - I should probably read the unicode implementation in some
detail... or alternative, just learn a decent Rust unicode library!


I do think that if I am ever time-rich, reading RustPython could prove illumnating
for some of these topics; I would guess that the code is much easier to follow.
CPython code quality is excellent, but (a) C is more verbose and you basically have
to strip a lot of type information, and (b) the macros, which indespensible, can
make it harder to skim code and inhibit code-navigation tools. It would probably
prove most useful if I were to cross-reference the two codebases rather than just
reading RustPython.
