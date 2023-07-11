# Notes from Phillip Guo's Python lectures

The Phillip Guo lectures on CPython can be found 
[on youtube](https://www.youtube.com/playlist?list=PLzV58Zm8FuBL6OAv1Yu6AwXZrnsFbbR0S).

This is a 10-hour dive into the CPython interpreter code downstream of the
compiler, focused on how Python implements interesting parts of the runtime. It
was a seminar for students, so it's focused on key ideas and how they are
expressed in the CPython interpreter.

The lectures are a bit old, from around 2015 and they focus on Python2. My
notes will be covering the same topics, but with the CPython codebase circa
2023 (Python main is currently between the 3.11 and 3.12 releases).


## Lecture 1: Setting up

There's not much to detail here... download CPython, then run
```
./configure
make
```
to get a from-source build.

You can verify that it works by running
```
./python.exe
```


## Lecture 2: Opcodes and the main interpreter loop

### How to play with example code

I started an example Python source to play with in `guo_code/lecture_02_a.py`.

With my helpers, you can try out running the examples by running
```
./run-python.sh guo_code/lecture_02_a.py
```
and you can view the bytecode by running
```
./view_bytecode.py guo_code/lecture_02_a.py
```
or just
```
./run-python.sh -m dis guo_code/lecture_02_a.py
```

You can interactively poke at the result of compiling (which includes
more than just bytecode) by running
```
c = compile('guo_notes/lecture_02_a.py', 'test.py', 'exec')
```
in an interactive session.


### The results of `compile`

Again, you can compile example code with:
```
c = compile(open('guo_code/lecture_02_a.py', 'r').read(), 'test.py', 'exec')
```
Sadly I'm not yet sure how to make ipython (or an alternative) work
with a from-source compile, but you can poke at this with either
`help(c)` or `dir(c)`.

The results of compile is a "code object". It contains:
- name related metadata for the chunk:
  - co_filename: the pretty filename for this function. For us, it's 'test.py'
  - co_names: seems to store components of the filepath
  - co_name: the function name; for a toplevel this is '<module>'
  - co_qualname: a qualified name of this function, relative to the
    top-level (so it accounts for nested classes / functions / etc)
- the bytecode and related stuff
  - co_code: the actual bytecode, as raw bytes
  - co_consts: constants. Always includes `None`.
  - co_varnames: Local names (includes both params and locals defined in body)
  - co_freevars: Captured variables, from in closure.
  - co_cellvars: Locals captured by any nested closure.
  - co_flags: not sure what this is yet
- positional information used to view bytecode / show runtime info
  - co_firstlineno: initial line of the funciton (1 for a toplevel)
  - co_positions(): iterator, I believe of (relative?) location info per byte of bytecode
  - co_lines(): iterator of lines
  - co_varnames: argument names. For a toplevel this is just `()`
- execution-related metadata
  - co_argcount: total number of args
  - co_posonlyargcount: number of positional-only args
  - co_kwonlyargcount: number of keyword-only args
  - co_exceptiontable: related to exception handling, we'll get to this
  - co_stacksize: maximum size the data stack can attain on any control flow
  - co_nlocals: number of locals (static; we might not initialize all of them)


If you want to understand how the raw binary format relates to `dis` output,
you can see the bytes in a human-readable form with:
```
[int(b) for b in c.co_code]
```

### Where the C code for bytecode handling lives

Where to find code:
- The opcodes are defined, for C code, in `opcodes.h` but this
  is generated from `Lib/opcode.py` which is the source of truth.
- The main interpreter loop still lives `ceval.c`
  - There's a bunch of nested PyEval_EvalWhatever functions and macros, some of
    which are defined in `pycore_ceval.h`
  - They seem to eventually hit `_PyEval_EvalFrameDefault`, which
    lives in `ceval.c`;
- The main interpreter loop is now defined in `Python/bytecodes.c`
  which is where "the big eval loop" lives, but that code isn't
  actually runnable...
  - Instead, you have to look at `generated_cases.c.h`, which gets
    included into `ceval.c`s `_PyEval_EvalFrameDefault`.
- All the macros have been extracted into `ceval_macros.h`

The opcode handlers are mostly not too hard to skim, but some of the
switch logic is very confusing, there are macros that do things like
add two labels together. Hopefully the CPython Internals book will
eventually explain this well; back in Python 2 the loop was much
more straightforward but I think it's been optimized.


### Notes on `EvalFrameDefault`

Inputs
- `PyThreadState *tstate`
  - after aliasing via `pytypedefs.h`, `PyThreadState` is defined as a struct
    `_ts` (used to deal with the recursive type) in `pystate.h`
  - It has lots more stuff accessed through it, e.g. the `_PyCFrame`.
- `_PyInterpreterFrame *frame`
  - This type is defined in `pycore_frame.h`, it contains:
    - f_executable: the actual bytecode, which is generally accessed
      by way of `_PyFrame_GetCode` as a `PyCodeObject*`
      - The `PyCodeObject` type is defined in `code.h` (it's a little hard
        to skim, the definition is in a macro so it can be reused in
        deepfreeze).
      - When we look at a `__code__`, this is the Python representation of a
        `PyCodeObject`; the data is roughly the same. The actual bytes are
        in `char co_code_adaptive[(SIZE)]`, an array of bytes.
    - `_Py_CODEUNIT *prev_instr`, which is the code unit prior to the
      next instruction that should be run (it's not actually the previous
      instruction because in some settings we can jump and it will point
      at an instruction never run)
      - the instruction value is a struct of two bytes, one for the code and
        one for any arg (opcodes that need more than one byte for the arg can
        extend it using EXTENDED_ARG, a dedicated opcode, to add up to 3 extra
        bytes)
    - `f_funcobj`, `f_global`, `f_builtins`, `f_locals`; all of these are runtime
      data you could potentially introspect. Many of them appear to be
      only valid some of the time from the standpoint of C code.
    - `PyObject* localsplus[1]`; the `[1]` here probably a lie, I *think* this
      is really a PyObject** that points to the locals (which can be
      positionally accessed by the 


Logic, at a *very* high level
- The heart of the eval loop is the combination of the included
  `generated_cases.c.h` and the computed-gotos handled by `DISPATCH`,
  which looks at `next_instr` and figures out a label to go to.
- You can see what the code does in a simpler way if you avoid
  `USE_COMPUTED_GOTOS`.

### Some more miscellaneous things I noticed

Top-level code doesn't use locals - the names have to be in the globals
table, and as a result top-levels won't make much use of `LOAD_FAST`; they'll
use `LOAD_NAME` instead.

Much as in `clox`, the code object for closures that might be created become
constants in functions - including top-level functions.

It also appears to me (based on dis for `lecture_02_b.py`) that default args
get turned into a tuple by the compiler when constructing a function from
code and from data defined in the calling context.

Specifically, I'm looking at this snippet:
```
  1           2 LOAD_CONST               3 ((5,))
              4 LOAD_CONST               1 (<code object f at 0x104f37ad0, file "guo_code/lecture_02_b.py", line 1>)
              6 MAKE_FUNCTION
```


## Notes from Lecture 3

(Lecture at https://www.youtube.com/watch?v=dJD9mLPCkuc&list=PLzV58Zm8FuBL6OAv1Yu6AwXZrnsFbbR0S&index=3)

### What about this lecture is out of date?

- The code locations have changed, as discussed above
- The `EvalFrameDefault` code no longer evaluates a frame, today it loops
  and evaluates all frames in one python green thread. As a result a number of
  things are no longer true:
  - It no longer returns an object in most cases; the only actual returns
    these days are in 2 spots related to hard exit / uncaught errors:
	- in the top-frame case of exception handling at `exit_unwind`
	- in the INTERPRETER_EXIT opcode
  - It no longer sets locals from the frame at initialization, instead
    it has to do that via a macro at certain labels (in particular when resuming)
- The `DISPATCH` macro and friends have replaced the older next-opcode logic

### Python Tutor

You can paste code into https://pythontutor.com/render.html to trace
execution.

In additon to the example code from the class, I also thought it was
cool to try a generator and see how it gets displayed:
```py
x = 10

def example_iter():
    for x in range(2):
        yield x
        
        
def bar():
    for x in example_iter():
        print(x)
```
        
        
Unfortunately it wasn't quite as obvious from the visualization what the
runtime representation actually is for generators, but Lecture 9 will at least
partially cover this.


### A quick skim of the core `_PyEval_EvalFrameDefault` function

Looking at `ceval.c`s `_PyEval_EvalFrameDefault` in greater detail (ignoring the
many lines of error handling).

The name is a little misleading; it doesn't just evaluate one stack frame, because
its implementation is sort of tail recursive (where intermediate data is pushed
onto the heap).

It runs an infinite loop over opcodes, where:
- if we need to call another function, we'll set up the frame in-place and then
  `goto start_frame`, generally via a call to `DISPATCH_INLINED`
- if we hit an exit condition like `return`, we'll clean up the current frame and
  then `goto resume_frame`.

Some of the relevant variables here:
- `opcode` and `optarg` are the currently-being-processed code and argument
- `PyObject **stack_pointer` is a cached value of the frame's datastack, and it
  points to the next *available* slot on the stack (so the top of the stack is
  at `-1`

Key labels:
- All `start_frame` really does is check for stack overflow via `_Py_EnterRecursivePy`.
  Then control flow passes beyond `resume_frame`.
- `resume_frame` only does a couple things:
  - set the `stack_pointer` as `_PyFrame_GetStackPointer`
  - set `next_instr = frame->prev_instr + 1`
  - call `DISPATCH()`, which jumps to the next instruction
- `handle_eval_breaker`, which is a label we occasionally jump to from handling opcodes
  in oder to handle all cooperative concurrency features as well as some internal
  things like GC. All it really does is
  - call `_Py_HandlePending`
  - return to the eval loop via `DISPATCH`
- The actual raw eval loop (which is only a true "loop" if `!USE_COMPUTED_GOTOS`)
  lives underneath `handle_eval_breaker`. It is labeled as `dispatch_opcode` in the
  case where we aren't using computed gotos.
  - It is mostly just the contents of `generated_cases.c.h`, which is generated
    from `bytecodes.c`. But there's a tiny bit of fall-through logic inlined directly
	here for
    - instrumented lines (I'm unsure what this is, likely related to some combination
	  of tracing, debugging, or profiling). It invokes `_Py_call_instrumentation_line`
	  on the current frame which seems like what a debugger would want.
	- unknown opcodes, which always creates an error
- Various `error` and `exception` related labels
  - unbound locals and pop failures have special-cased error handlers with extra logic
  - all of the error handlers eventually jump or fall through to `error`, which does some
    frame handling and calls `monitor_raise`
  - after `error` we fall through to the `exception_unwind` label, which I believe
    handles the actual logic of bubbling up exceptions.
	- It winds up calling `get_exception_handler`, which is presumably where catch happens
	- I *think* this logic is all at a per-block level rather than per-frame
  - after `exception_unwind` we fall through to `exit_unwind`, which I think is when we've
    given up on the current frame and bubble the exception up to the parent
    when we've exited all blocks.
	- it also handles the possibility that we're at the very top-level frame in which
	  case we actually `return NULL`
  - finally, if we have more frames it will fall through to `resume_with_error` which
    calls `SET_LOCALS_FROM_FRAME` to reset frame-specific ceval variables and then jumps
	right back to `exit`; this is how unwinding happens!

... Note: the labels I just went through cover *all* of the `_PyEval_EvalFrameDefault`
logic other than initialization; the bracket after `resume_with_error` is the end of that
function.
 
 
### Diving into C code for some code-related objects

**`PyCodeObject`**

Defined in `code.h`

The `_PyCode_DEF` macro defines a code object. This gets bound to the
`PyCodeObject` type, which is a subtype of `PyObject` and is the
C-level representation of the compiled bytecode objects that we see
when we look at `__code__` in the interpreter.

Not everything here is obvious; there's executor and cache related
code I don't yet understand, and some stuff that may be related to
`.pyc` file versioning.  But most of the data corresponds in obvious
ways to the exposed Python apis.

The raw bytecode is inside the code as co_code_adaptive

**`_PyCFame`**

This is the C representation of the fame stack; it contains the extra
linked-list boilerplate to wrap a `_PyInterpreterFrame` and a pointer
to the previous `_PyCFrame`. It does not have Python bindings.

**`PyInterPreterFrame`**

Defined in `pycore_frame.h`.

This value, which is a `PyObject` subtype, contains:
- The code object at `f_executable`
- The previous stack frame `*previous`... I'm not sure yet why
  we needed `_PyCFrame` or whether the previous frames are actually
  the same in both these views.
- Pointers to the environment lookups (globals, builtins, locals)
  at `f_{whatever}`
- The stack pointer for the data stack.
- The instruction pointer, and a `return_offset` pointer used
  in some cases to get the instruction pointer right when resuming after
  a return or yield.
- An alternate representation of the frame, in a `PyFrameObject*
  *frame_obj` field

**`PyFrameObject`**

Also defined in `pycore_frame`

This is yet another representation of the frame stack. I need to read
`Objects/frame_layout.md` to really understand why we have all these different
representations!

It contains:
- another frame pointer `f_back`
- a pointer to the fame data as a `_PyInterpreterFame* f_frame` (I think
  they each point to one another.
- Line number data, and some stuff related to fast locals / tracing
- A `PyObject *_f_frame_data[1]` array of objects; not yet sure what this is.


### Function calling

The opcode for calling a function these days is `CALL_FUNCTION_EX` rather
than `CALL_FUNCTION`. What does this do?

- It puts the args into a tuple if they weren't already
- It has special cases for instrumented calls which we can probably ignore for now
- In the vanilla case, the function is a `PyFunction_Type`, then we'll create a new
  frame and call `DISPATCH_INLINED`, which winds up:
  - initializing the new frame and pushing it onto the stack, with much of the work
    (including copying locals) actually implemented in
	`_PyEvalFramePushAndInit_Ex` (which in turn relies on `_PyEvalFramePushAndInit`
  - calling `goto start_frame` to resume the loop in the new frame
- There's a fall-through to *calling* the `PyObjectCall` function, which
  - Winds up handling errors on non-callable functions
  - Otherwise, winds up executing a C-level function pointer associated with
    `Py_TYPE(callable)->tp_call`, effectively the `__call__` method (at the C-API
	level) for this object.
	- This could execute native code (e.g. a PyObject representing a wrapped C func)
	- Or it might wind up executing a normal `__call__` method in Python; in this
	  case I *think* we're going to wind up in a new C-level stack frame of
	  `_PyEval_EvalFrameDefault` (in other words we do recurse on callable object
	  calls, just not on "vanilla" function calls).
	  
	  
There are a lot of details around making sure everything gets cleaned up
correctly on return. I'm not ready to dive into that yet.

### A note from Phillip's bit about the stack of conceptual things

Bytecode is raw bytecode.

A Code object combines bytecode with extra semantic info, especially names
and constant values.

A function wraps a code object with environment information, such as builtins,
globals, and possibly closed-over data.


A frame combines a function with dynamic data from a single execution, in
particular locals / data stack / instruction pointer info.


### Miscellaneous notes on some actual opcode evaluation

You'll note that we have to increment / decrement refcounts whenever we push / pop from
the stack; the refcount needs to include the value stack as a valid reference.

What does a function object actually have? It has access to all kinds of environment data.
In the case of a static function, this will include things like `f.__builtins__` which is
a dict of the built-in names and `f.__globals__` which is the global environment for `f`
(which in practice is probably the environment of the module `f` was defined in).

If the function actually closes over anything it will also have a tuple of "cells" at
`f.__closure__` (`__closure__` is `None` for top-level static functions). Each entry will be
a `cell` type with the closed-over value as `cell_contents` in the Python API.


## Notes on Lecture 4 (the PyObject data model)

See https://www.youtube.com/watch?v=naZTXNBbcLc&list=PLzV58Zm8FuBL6OAv1Yu6AwXZrnsFbbR0S&index=4.


### What has changed since the lecture?

There is no `intobject.c` anymore, nor a `PyIntObject` type. I'm not yet sure where that code
migrated to.

Instead, look for `PyLongObject` and `longobject.c`. The actual `add` operation is fairly complex
because longs are arbitrary-size integers; there are hacks to avoid this on smaller integers but
I don't know the interpreter well enough to find that code yet. It's also trickier to find the
actual definition of the struct for `PyLongObject` because it's been moved into
`longintrepr.h` and is aliased in `pytypedefs.h`.

You can read the docs on the Python-level API for `PyObject` at:
https://docs.python.org/3/reference/datamodel.html


### The core code for the lecture

The code for this lives in
- `Include/object.h`, which defines
  - various macros, including the
    - PyObjct_HEAD macro that gets inlined into child type structs + initializers
  - The `_object` struct, which gets aliased to `PyObject` in `pytypedefs.h`
  - Forward decorations for the *many* functions that operate on `PyObject`
- `Include/cpython/object.h` (it's *so* weird that there are two `object.h` files!!) defines:
  - Some basic string-related code (remember from clox that strings are very special; the
    interpreter uses them heavily internally so they have to be hardcoded at a low level)
  - The `_typeobject` struct, which gets aliased to `PyTypeObject` in `pytypedefs.h`
  - In order to support ^, the various api structs to support type objects (e.g. `PyNumberMethods`,
    `PySequenceMethods`
- `Objects/object.c` which is where the implementations live. Some of the chunks of functions:
  - ref incrementing / decrementing
  - new and init functions
  
  
Other code that you'll reach if you dig into this:
- `pyport.h`, which defines macros like `PyAPI_FUNC`, `PyAPI_DATA`

The actual `PyObject` structure is fairly simple, it has:
- Optionally some `_PyObject_HEAD_EXTRA` data that allows a debug build to have
  mark-and-swee GC to debug refcounting problems. Normally this is empty.
- A refcount, whose implementation as split 32-bit integers I unfortunately
  can't currently understand.
- A `PyTypeObject * ob_type` field where all of the type-specific information lives

Most implementations will put more object-specific data after the type but that is
type-dependent, the `_object` struct itself does not mandate any data. `PyObject` itself
is not instantiatable at all from Python (you could make one in C, but it's never used
normally!).

There's also `PyVarObject` which has the same header but includes an `ob_size`. I'm not
yet sure what it's used for; my guess is that it allows some built-in container variable-size
objects like `str` to have an optimized representation(?).

The `PyTypeObject` type (aka `_typeobject` in `object.c`) is a subtype of `PyObject`

After preprocessing, the actual definition of `PyObject` is just
```C
struct _object {
	PY_UINT32_T ob_refcnt_split[2];   // refcount, in 32-bit parts
    PyTypeObject *ob_type;            // the associated type object
};
```


### Inspecting objects

In the python interpreter, you can introspect a lot of the object API using `dir` and
`__dunder__` methods / attributes.

For an example of a specific `__add__` implementation, you can look at `floatobject.c.h`

You can inspect refcounts with `from sys import getrefcount; getrefcount(o)`.
  
### Adding ints

This has gotten harder to follow since the lecture was given; these days the operations
are hardcoded into a `static const binaryfunc binary_ops[]` in `ceval.c`, and then dummied
out in the `bytecodes.c` logic. The `BINARY_OP` opcode will dispatch on that array.

The definition of `binaryfunc` is:
```
typedef PyObject * (*binaryfunc)(PyObject *, PyObject *);
```
and the `+` op becomes `PyNumber_Add`, which is declared in `abstract.h`.

The actual definition is a little hard to find, but it's in `Objects/abstract.c`. It
isn't too involved, although there's some indirection to use the function pointers
defined in `PyNumberMethods` and to share logic with other binary ops that use a
similar lookup mechanism.
  

## Lecture 5: The type model (focusing on sequences as an example: tuples and strings)

See https://www.youtube.com/watch?v=ngkl95AMl5M&list=PLzV58Zm8FuBL6OAv1Yu6AwXZrnsFbbR0S&index=5

### What's changed?

The lecture is mostly about `stringobject` which no longer exists, so today you
have to decide whether to look at `

### The Tuple Type

Two types have their `PyTypeObject`s declared in `Include/tupleobject.h`:
- `PyTuple_Type`, the type for tuples themselves
- `PyTupleIter_Type`, the C representation of the result of iterating a tuple

There are also a handful of basic tuple-related functions.

A weird thing about tupleobject is that it passes through the generated code at
`clinic/tupleobject.c.h` and there's actually a separate `cpython/Include/tupleobject.h`
where the actual `PyTupleObject` type is defined.

All the actual magic lives in `tupleobject.c`, where the functions are defined and then
many of them are wrapped up in the type objects. The implementations are potentially pretty
interesting but the most important part of the module are the definitions
```
static PySequenceMethods tuple_as_sequence = {
    (lenfunc)tuplelength,                       /* sq_length */
    (binaryfunc)tupleconcat,                    /* sq_concat */
    (ssizeargfunc)tuplerepeat,                  /* sq_repeat */
    (ssizeargfunc)tupleitem,                    /* sq_item */
    0,                                          /* sq_slice */
    0,                                          /* sq_ass_item */
    0,                                          /* sq_ass_slice */
    (objobjproc)tuplecontains,                  /* sq_contains */
};

PyTypeObject PyTuple_Type = {
    PyVarObject_HEAD_INIT(&PyType_Type, 0)
    "tuple",
    sizeof(PyTupleObject) - sizeof(PyObject *),
    sizeof(PyObject *),
    (destructor)tupledealloc,                   /* tp_dealloc */
    0,                                          /* tp_vectorcall_offset */
    ...
    &tuple_as_sequence,                         /* tp_as_sequence */
	...
}
```

This really illustrates the heart of how object types are built up: special protocols
are their own structs that types which implement them should define (other types can just
use `0` or `NULL` there) and the sequence API is a nice example since it's smaller than,
e.g., the number API.

Then the type itself is a bunch of function pointers for the "flat" functions plus
potentially some of these structs of protocol-specific functions.


### The `str` type

The string type lives in `unicodeobject.h` and `unicodeobject.c`. I could probably learn
a *lot* about unicode from reading this in detail, but that's for another time. I'll
focus on `bytes` instead for now.

At somepoint I will definitely need to learn about string interning,
which appears to happen only for unicode strings (I don't see
interning-related logic in the `bytes` implementation).

It appears to me that unicode objects are implemented in terms of a
`PyAsciiObject` that is basically an old-school string, with some
extra metadata in structural subtypes but I can't understand the
relationship between PyCompactUnicodeObject and PyUnicodeObject at a
first skim.

### The `bytes` type

The data types for `PyBytes_Type` and `PyBytesIter_Type` live in `Include/bytesobject.h`.

The actual raw data for `PyBytesObject` lives in `Include/cpython/bytesobject.h`

The private implementation is code-generated in `clinic/bytesobject.c.h`. The generated
implementations seem to mostly wrap nicely-typed functions, most of whom have a
`*._impl` name format, defined in `bytesobject.c`

A nice function to zoom in on is `bytes_richcompare`. You can also learn a lot by tracing
execution down from `COMPARE_OP`:
- `inst(COMPARE_OP, ...) ...` in `bytecodes.c`
- (ignoring adaptive code hooks) `PyObject_RichCompare` in `object.c`
- `do_richcompare` in `object.c`
- the `tp_richcompare` lookup inside that function
- ... which, when comparing bytes objects, would call `bytes_richcompare`

It's not a terrible idea to then go up and also check the specialization code in
`_Py_Specialize_CompareOp`, which special-cases same-type comparisons on a few built-in
types including float, long, and unicode.

**Concatenation**

The concatenation implementation lives at `bytes_concat`, and it becomes part of the
`bytes_as_sequence` code.

How it works abstractly:

Note that this means the eval loop has to handle falling back to `sq_concat` if the
`BINARY_OP1` lookup in the implementation of`PyNumber_Add` lookup fails. That's exactly
what you'll see if you look at the `PyNumber_Add` implementation in `abstract.c`! I believe
this is what happens if you try to concat `bytes` with `+`.

How it actually works, for `str`:

The "hot" cases are once again improved by specialization; if you look at 
`_Py_Specialize_BinaryOp` in `specialize.c` you'll see that it actually handles
`str` (but not `bytes`) concatenation in a hardcoded hook that dispatches
to `BINARY_OP_ADD_UNICODE`). As far as I can tell `bytes` aren't specialized though,
so I think they go through the normal fallback logic in `abstract.c`.


### Note: what's going on with all the `clinic` and `Include/cpython` stuff?

The pattern of using `Include/sometypeobject.h` for type definitions but
`Include/cpython/sometypeobject.h` for the actual data seems to be tied to
an effort to define a `Py_LIMITED_API` compile flag that hides many implementation
details.

The second `cpython` header gets included in the normal header if that flag is *not*
set; otherwise those headers are hidden and are only used by the generated code
in `clinic/sometypeobject.c.h`.

I can probably read up on this `Py_LIMITED_API` pattern (the rationale, patterns, etc).
It makes the code harder to skim at first but if you know what to expect it's not
*so* hard to navigate.

Some of what's going on is explained in
`Doc/howto/clinic.rst`.


## Lecture 6: Code Objects, Functions, Closures


See https://www.youtube.com/watch?v=ix6MTSemdUU&list=PLzV58Zm8FuBL6OAv1Yu6AwXZrnsFbbR0S&index=6


This lecture can be viewed as primarily about the "lifetime" of functions
and related data.

### Code objects, created at compile time

A code object is created when we compile a module; it becomes part of the module
constants. But no function object exists yet.

Recall that code objects are defined by `PyCodeObject` in `code.h` and know the
static information needed to run a function, but do not include environment data.

We already discussed this in some detail above so I won't repeat too much here.

### Function objects, created at declaration time

A function is actually created by a `def` form.

The resulting data doesn't look the same as it used to when this lecture was given;
the various `func_.*` attributes from that lecture are now dunder attributes:
- `f.__globals__` is a pointer to the global environment (module-level where the
  func was defined)
- `f.__builtins__` is similar, but builtins aren't in globals so they
  need a separate lookup.
- `f.__defaults__` stores the default arguments for the function
- `f.__closure__` has handles on nonlocals (closed-over values), each of which
  is a `cell` class whose `cell_contents` points at the actual data. This attribute
  will be `None` for static functions.
- `f.__code__` is of course the code object, with all the static information.
- `f.__annotations__` has the type annotations, as a dict.
- `f.__module__` has the name of the parent module
- `f.__type_params__` has PEP 695-style type annotations as a tuple; each entry
  will be a `typing.TypeVar`.
- `f.__doc__` has a docstring, if any
  
  
### Closures

All function objects are structured "like" a closure, they have a handle
on their environment.

There are three things that are really specific to closures, by which I mean
functions that actually escape their defining scope:
- In the code object of the *creator*, `__code__.co_cellvars` will indicate
  which locals escape into a nested function. (Note that it's possible for multiple
  layers of indirection to be needed if there are many layers of function nesting).
  - This is likely needed for lifetime management in some cases; for example in
    `clox` (which has a different, lua-based impl) the outer function has to know
	when to move data to a "cell" after a local disappears from the call stack.
- In the code object of the *closure*, `__code__.co_freevars` will indicate the
  names of all captured variables. Each one should show up in `co_cellvars` of the
  parent.
- In the closure object (the function), the `__closure__` attribute will be
  a tuple with the actual `cell`s with handles on captures, rather than
  `None` as in a static function.


I'm pretty sure that the closure cell's C representation is `PyCellObject`,
as defined in
- `Include/cpython/cellobject.h`... all it really is is a pointer to the
  actual object.
- `Objects/cellobjects.c` where the logic lives. There's not much
  here besides getting contents, minimal things like repr/compare, and
  managing the refcounts.
  
Actually because it's so minimal, the `PyCellObject` code is a kind of nice
way to get a micro-intro to the `PyTypeObject` API.

### The C representation of Functions / Closures

The function type is defined in
- `Include/cpython/funcobject.h` which has the actual `PyFuncObject` type,
  public function headers, and the declaration but not definition of
  `PyFunction_Type`.
- `funcobject.c` which implements all the helpers and has the actual
  `PyTypeObject` declarations.
  
The code is a little more complex than we want to cover end-to-end
right now because it includes specialized `PyTypeObject`s for class
methods and static methods, but if you focus just the base function
type and object structs you can see what we care about.

`PyFunctionObject` has attributes that correspond to all the dunder methods,
although their names match the old Python2 code:
- `func_doc`, `func_dict`, `func_typeparams`, `func_module`
  `func_annotations`, `func_closure` are all pretty obvious
- I'm not sure what `func_weakreflist` is yet, I need to read more about
  weak references (added this to my to-do notes!).
- There's some other stuff that's more advanced than worth covering here;
  `func_version` can be used by the specialization framework and
  `vectorcall` presumably allows some form of vectorization optimization;
  I'm not sure where it's used but you can check out the signature in
  `object.h`.
  - Both of these didn't exist when the lecture was given.
  
The `PyFunction_Type` implementation isn't actually all that interesting,
other than it's `call` appears to be focused on vector calls only; I'm
not really sure how this works yet (normal calls are special-cased in
the interpreter so you presumably wouldn't hit the `tp_call` anyway).

I made a note in my looming questions doc that this would be good to
investigate more someday.

**The old `function_call` function vs new logic + vectorcall**

In the lecture, Guo talks about how the `tp_call` function points to
`function_call`, which allocates a new frame and calls the pyeval loop.

This is no longer true; as I discuss below these days the loop crosses
function calls, so the frame is allocated in the same loop and we just
jump to `start_frame` label.

As a result, the `tp_call` is now repurposed to vectorcall, which I
don't know anything about yet.

**garbage collection**

Some day I do need to understand the GC code. I realize that a lot
of CPython is really about refcount handling and that the code looks
"almost" like using smart pointers.

But what confuses me is that it's not obvious how CPython knows how
to navigate all the pointers when doing cycle detection; in `clox`
the key thing 

### Creating functions

The bytecode operation to build a function is `MAKE_FUNCTION`, which
constructs a `PyFunctionObject` via `PyFunction_New(codeobj, GLOBALS())`.
Most of the logic is actually in `PyFunction_NewWithQualName`:
- increment the reference on globals
- grab the `__name__` out of globals ot use for `__module__`
- grab `builtins` from `globals` and `tstate`
  - note the ugly popping-out-of-nowhere of `tstate` via `_PyThreadState_GET()`
- Make a new struct `op` via `PyObject_GC_New` (I find this name weird
  since `op` sounds like `opcode` but I think it means "object
  pointer")
- save globals and builtins in the func object, along with some other
  things


### Frames

This lecture didn't really discuss frames, but I want to back bounce to
Lecture 3 again: recall that a frame includes pointers `f_funcobj` for the
function object and also a handful of pointers like `f_globals` that seem
to be duplicated with functions.

You can see how this works by looking at one of the `CALL` opcodes. When
we make a call, we will
- verify that the thing we call is a normal function with `PyFunction_Check`
- get the function, and then pass it to a frame constructor:
  `_PyInterpreterFrame *new_frame = _PyFrame_PushUnchecked(tstate, func, argcount)`

This function (defined in `pycore_frame.sh`) will in turn do a bit of
lowlevel datastack work and then call `_PyFrame_Initialize`, which will
copy most of the function data pointers into the frame.

Note that the fields borrowed from func are all commented as
"Borrowed reference. Only valid if not on C stack". I'm not actually
certain what this means in practice (I'm assuming it means the frame being
a stack-allocated C value, but that doesn't really clear it up for
me), but it's worth noting that we *don't* increase refcounts for the frame
so I think we could get dangling pointers if a frame were able to outlive its
function.

The locals are always initialized to `NULL`; populating them is inlined
into the eval loop code rather than during the initialization functions.


### Random note: `__dict__` is implemented as `PyMemberDef`

This was in answer to a student's question. I should eventually write
more detailed notes on how `__dict__` / `dir()` work.


# Lecture 7: Iterators and looping

See https://www.youtube.com/watch?v=8-KfIsDbxVY&list=PLzV58Zm8FuBL6OAv1Yu6AwXZrnsFbbR0S&index=7


The iterator API is defined at two layers, in C and in Python.

In C, the iterator API basically consists of:
- a `tp_iter` that might return an iterator object for a given object. The iterator
  *can* be yourself, but in many cases it's something else (for example tuples and
  bytes each have separate iterator types).
- a `tp_iternext` that an iterator type should implement. This should either produce
  a `PyObject*` or "throw" an exception at the C API level.
  
The Python API is similar:
- you can have an `__iter__` method (invokable with `iter(obj)`) that produces an
  iterator; you could just return `self` if the type is already an iterator, or
  you could use a generator with `yield`, or you could return some other object.
- an iterator object should implement `__next__` (invokable with `next(obj)` to
  get the next item, or raise a `StopIteration` when done
  
  
### Let's look a bit at the list type

Lists are defined in:
- `Include/listobject.h` which declares list functions and the list type objects
  `PyList_Type`, `PyListIter_Type`, and `PyListRevIter_Type`.
- `Include/cpython/listobject.h` which defines the actual `PyListObject`; the
   underlying representation is just
   - `PyObject_VAR_HEAD` (refcount, type, and the size)
   - `PyObject **ob_item` (the actual contents)
   - `Py_ssize_t allocated` to account for the fact that this is a "vector" type,
     a dynamically-resizable array.
- `Objects/listobject.c` which has all the implementations plus the definition of
  the type objects.
- The actual raw data type for `_PyListIterObject` is in a different module,
  `pycore_list.h`.
  
  
The heart of the list itself is really the `list_resize` operator, which
works pretty similarly to, e.g., the resizeable arrays in `clox`.

The `BUILD_LIST` bytecode could be interesting to look at eventually if you
want to understand how lists are actually created at runtime via literals.

If we look at the `PyTypeObject PyList_Type { ... }` block, we'll see that it
defines `tp_iter` to be `list_iter`. If we actually look at this, we see that
it creates a `PyListIterObject` of `PyListIter_Type` type.

If we look at the actual `PyListIter_Type`, we'll see that it has a `tp_iter` of
`PyObject_SelfIter`, which is the C-API helper for an iterator being iterable,
and a `tp_iternext` of `listiter_next`. And the underlying data (defined in
`pycore_list.h`) is pretty much what you'd expect: a pointer to the
underlying list plus a `Py_ssize_t it_index`. The wrapper is really just needed
so that the iterator index (which is per-iterator state) can be separated
from the underlying list.

The `listiter_next` function then implements the next in terms of that data;
pretty much just call getitem (by way of the C level `PyList_GET_ITEM`) if
possible and otherwise return NULL (which I'm guessing the runtime code then
turns into a StopIteration).


There's also a `list__reversed__impl` that produces the `PyListRevIter_Type`. I
don't think this is so critical to dig into right now.


### Okay, what does the bytecode that uses these APIs look like?

Consider this code:
```py
x = ['a', 'b', 'c']

for e in x:
    pass
```

This will compile into the following bytecode:
```
  0           0 RESUME                   0

  1           2 BUILD_LIST               0
              4 LOAD_CONST               0 (('a', 'b', 'c'))
              6 LIST_EXTEND              1
              8 STORE_NAME               0 (x)

  3          10 LOAD_NAME                0 (x)
             12 GET_ITER
        >>   14 FOR_ITER                 3 (to 24)
             18 STORE_NAME               1 (e)

  4          20 JUMP_BACKWARD            5 (to 14)

  3     >>   24 END_FOR
             26 RETURN_CONST             1 (None)
```

The interesting parts of this are:
- `LOAD_NAME 0 (x)` pushes the list `x` onto the stack
- `GET_ITER` grabs the iterator for `x`
- `FOR_ITER` creates a code block (we haven't seen this yet)
  that runs until `END_FOR`
  - Every time we hit `FOR_ITER`, we'll put the output of `iternext`
    onto the top of the stack.
  - The intermediate code runs repeatedly until we hit a `StopIteration`...
  - ...We `STORE_NAME` the top of the stack into `e`; that's all because of `pass`
  - We then `JUMP_BACKWARD`; this line won't be hit after a stop iteration
- After the `END_FOR` we are done (return `None`)


### How does the bytecode evaluator work?

**GET_ITER**

This pretty much just calls `PYOBJECT_GETITER` and sets it to `PyObject_GetIter`.

The code in `bytecodes.c` is a little wierd because of code generation, but if
you look at `generated_cases.c.h` you can see that the declarations and stack
push are generated.

The underlying `PyObject_GetIer` code lives in `abstract.c`, and it tries to
call `tp_iter` if possible, falling back to a "sequence iterator" if possible.

The seq iterator logic (which isn't used for lists) is defined in
`iterobject.c` which has a generic, non-specialized iterator for
sequence types (user-space classes that implement `__seq__` will get this
for free).

The code for the generic sequence version is more interesting than the list
version because, even though it's more or less the same, it doesn't have
a size to use so it has to "catch" (in C code) `IndexError` or `StopIteration`
coming from the underlying sequence and return `NULL`.

**FOR_ITER**

Once again there's a lot of generated code so it's good to cross-reference
`bytecodes.c` with `generated_cases.c.h`.

Ignoring specialization, what this does is kind of what' you'd expect:
- Peek at the top of the stack to set `iter` (don't pop it!)
- Try calling `tp_iternext` on it
- Handle various error conditions
  - In particular, if `tstate` indicates a `PyExc_StopIteration` then
    handle it as if no error.
  - Note: the built-in iterators don't actually use `StopIteration`, they
    just return NULL. The `StopIteration` check is only there because
	Python-defined iterators need it, but there's overhead we wouldn't
	want to pay on builtins.
- Depending on whether we found a value:
  - If yes, put it on the stack (`STACK_GROW(1); stack_pointer[-1] - next`)
  - If no, then finish...
    - `STACK_SHRINK(1)` and `Py_DECREF(iter)` cleans up the stack
	- Some inline cache stuff I don't understand yet
	- `JUMPBY(oparg + 1); DISPATCH()` exits the loop

**JUMP_BACKWARD**

This is pretty much what you'd expect, it mainly just calls
`JUMPBY(1 - oparg)`. There are two extra goodies though:
- Some specialization hooks; I guess specialization is looping-aware(?)
- A call to `CHECK_EVAL_BREAKER` which means we're creating an opportunity
  for the GC to run, or to switch to another green thread.

### Misc notes

There used to be an extra has-iterator check and list was special
cased more. That logic no longer exists, lists will actually have their
iterator accessed by way of `tp_iter`.

The flags do still exist in `object.h` and involve bit-shifted `1UL` values,
for example `Py_TPFLAGS_TYPE_SUBCLASS`.
- You still set flags by bitwise-oring them,
  e.g. `Py_TPFLAGS_TYPE_SUBCLASS | Py_TPFLAGS_BYTES_SUBCLASS`.
- And you still access flags by bitwise-anding the flags with the flag
  you want, e.g. `long is_bytes = flags | Py_TPFLAGS_BYTES_SUBCLASS`


We'll see the bridge between user-defined classes with `__seq__`,
`__iter__`, and/or `__next__` and the `tp_iter` / `tp_iternext` C
APIs soon when we cover user-defined classes.


## Lecture 8: User-defined classes

See https://www.youtube.com/watch?v=Wbu2wMCcTKo&list=PLzV58Zm8FuBL6OAv1Yu6AwXZrnsFbbR0S&index=8

### A range-like example

Inspired by the previous iterator lecture, let's consider a pure-Python
counter iterator:
```py
class IterateForever:
    def __init__(self, x_arg):
        self.x = x_arg

    def __next__(self):
        return self.x

iterate_forever = IterateForever(42)class IterateForever:
```

How does this all work?

It could be useful to visualize the execution at
https://pythontutor.com/render.html#mode=display.

Now let's look at the for just the class:
```
  0           0 RESUME                   0
  1           2 PUSH_NULL
              4 LOAD_BUILD_CLASS
              6 LOAD_CONST               0 (<code object IterateForever at 0x101613590, file "guo_code/lecture_08_a.py", line 1>)
              8 MAKE_FUNCTION
             10 LOAD_CONST               1 ('IterateForever')
             12 CALL                     2
             20 STORE_NAME               0 (IterateForever)

  8          22 PUSH_NULL
             24 LOAD_NAME                0 (IterateForever)
             26 LOAD_CONST               2 (42)
             28 CALL                     1
             36 STORE_NAME               1 (iterate_forever)
             38 RETURN_CONST             3 (None)

Disassembly of <code object IterateForever at 0x101613590, file "guo_code/lecture_08_a.py", line 1>:
  1           0 RESUME                   0
              2 LOAD_NAME                0 (__name__)
              4 STORE_NAME               1 (__module__)
              6 LOAD_CONST               0 ('IterateForever')
              8 STORE_NAME               2 (__qualname__)

  2          10 LOAD_CONST               1 (<code object __init__ at 0x101613ad0, file "guo_code/lecture_08_a.py", line 2>)
             12 MAKE_FUNCTION
             14 STORE_NAME               3 (__init__)

  5          16 LOAD_CONST               2 (<code object __next__ at 0x1015474b0, file "guo_code/lecture_08_a.py", line 5>)
             18 MAKE_FUNCTION
             20 STORE_NAME               4 (__next__)
             22 RETURN_CONST             3 (None)

Disassembly of <code object __init__ at 0x101613ad0, file "guo_code/lecture_08_a.py", line 2>:
  2           0 RESUME                   0

  3           2 LOAD_FAST_LOAD_FAST     16 (x_arg, self)
              4 STORE_ATTR               0 (x)
             14 RETURN_CONST             0 (None)

Disassembly of <code object __next__ at 0x1015474b0, file "guo_code/lecture_08_a.py", line 5>:
  5           0 RESUME                   0

  6           2 LOAD_FAST                0 (self)
              4 LOAD_ATTR                0 (x)
             24 RETURN_VALUE
```

Most of this is just the same kinds of function code we've seen before
with a few new opcodes not tied to this lecture like
- `SWAP`, which just flips stack entries
- `LOAD_FAST_LOAD_FAST` which just combines two `LOAD_FAST`s
- `POP_JUMP_IF_FALSE` which is straightforward
- `RAISE_VARARGS 1` which raises an error of the type at the
  top of the stack (note the `LOAD_GLOBAL StopIteration` above it)

The key new OOP opcodes we want to focus on are:
- The code for the top-level (`code object CustomRange at 0x101796c40`)
- The new `LOAD_BUILD_CLASS`opcode
- The code for the methods, mainly the bit about `self`
- The new `LOAD_ATTR` opcode
- The new `STORE_ATTR` opcode

The class construction, which goes beyond one opcode, is of particular interest.

### Creating a class: how the bytecode works

Observe that the class body has compiled code:
```
Disassembly of <code object IterateForever at 0x101613590, file "guo_code/lecture_08_a.py", line 1>:
  1           0 RESUME                   0
              2 LOAD_NAME                0 (__name__)
              4 STORE_NAME               1 (__module__)
              6 LOAD_CONST               0 ('IterateForever')
              8 STORE_NAME               2 (__qualname__)

  2          10 LOAD_CONST               1 (<code object __init__ at 0x101613ad0, file "guo_code/lecture_08_a.py", line 2>)
             12 MAKE_FUNCTION
             14 STORE_NAME               3 (__init__)

  5          16 LOAD_CONST               2 (<code object __next__ at 0x1015474b0, file "guo_code/lecture_08_a.py", line 5>)
             18 MAKE_FUNCTION
             20 STORE_NAME               4 (__next__)
             22 RETURN_CONST             3 (None)
```

This code can define any locals it wants; they wind up being
interpreted by the `__new__` function of the metaclass (which by
default is `type`). In many typical examples, it will do nothing
but define functions, which become methods of the class.

How is this called from the module top-level?
```
  1           2 PUSH_NULL
              4 LOAD_BUILD_CLASS
              6 LOAD_CONST               0 (<code object IterateForever at 0x101613590, file "guo_code/lecture_08_a.py", line 1>)
              8 MAKE_FUNCTION
             10 LOAD_CONST               1 ('IterateForever')
             12 CALL                     2
             20 STORE_NAME               0 (IterateForever)
```

The `LOAD_BUILD_CLASS` opcode is really just loading `builtins.__build_class__`,
which you can poke at from Python:
```
>>> __build_class__
<built-in function __build_class__>
```

Then, it
- pushes the code object for the classI
- calls `MAKE_FUNCTION` to create a `PyFunctionObject` for the top-level
- pushes the class name
- executes a `CALL` with 2 args; the args are the class body function and the name

This means we're effectively running `__build_class__(top_level, 'IterateForever')`

I beleive the `PUSH_NULL` is because the call can potentially take kwargs for
inheritance; we aren't using that here.

### Creating a class: what is the `__build_class__` function?

The `__build_class__` function is defined in `Python/bltinmodules.c`, which defines
builtins; the implementation lives at `builtin___build_class__` and it is bound
to the module in the `PyMethodDef` near the bottom.

What it does (with a ton of error handling) is:
- Check that the function passed is callable
- Extract the class name (args[1])
- Extract base class names (other args; this is a varargs function)
- Figure out the metaclass
  - Calculate it if kwargs were passed; this is pretty involved, and
    eventually calls `_PyType_CalculateMetaclass`
  - Otherwise, use `PyType_Type` (i.e. `builtins.type`) as the metaclass
- Do some stuff to build a namespace `ns` in which to evaluate our
  function. I'm not sure how this works yet, but I'm pretty sure that
  it's basically how the locals get back out.
- Check for `__prepare__`; not sure what this does
- Do some magic that I can't yet understand...
  - Evaluate `func` with the namespace `ns`; I'm not yet sure how it all
    works but basically this will extract the dict of locals.
  - Call `meta` on the `ns`, which actually constructs the class, as `cls`
  - Do some sanity checks that I don't really understand yet
  - If all goes well, return the `cls`
  
There's still quite a lot I don't understand, but these notes are a decent start
for a deep-dive.

### Poking a little at the code kicked off by `__build_class__`

The type object code lives in
- `Internal/pyrcore_typeobject.h` for the core header declarations.
- `Objects/typeobject.c` (which also generates the clinic header at
  `typeobject.c.h` based on comments) for the definitions.
  
I got a little lost trying to skim this code, it's *huge* but this
is where all the slot construction happens.

`PyClassObject` is defined in `classobject.h` and `classobject.c`,
and the ultimate output is going to be one of these.

... Okay to be honest at this point I'm pretty lost on everything, the
OOP code is vastly more complex and verbose than other things we've
looked at so far...

But one other big takeaway is that eventually function calls will
fall through to `_PyObject_Call`, which looks up `tp_call`, and
the class objects that result from `__build_class__` calls are
callable, with a `tp_call` that ultimately calls the metaclass
`__new__` and then `__init__`.

Infortunately the lecture is mostly not helpful in navigating this;
more than previous lectures it has been outdated, `PyInstance_New`
no longer even exists and the code is too verbose for me to easily
back into what replaced it.

Even back then the code was complex - this is the only lecture where
Guo spends a good chunk of the lecture lost heh. One thing to keep in
mind when skimming the C code is that the logic is still object
oriented: if you invoke a method on an object, you don't actually need
to pass the object becasue the method already has a handle for `self`.
This was part of how he got confused.

## Lecture 9: Generators

See https://www.youtube.com/watch?v=wwjqMIlOuOo&list=PLzV58Zm8FuBL6OAv1Yu6AwXZrnsFbbR0S&index=9

### An example

Consider the following code:
```py
def generator():
    yield 'a'
    yield 'b'

for x in generator():
    print(x)
```

This compiles to
```
  0           0 RESUME                   0

  1           2 LOAD_CONST               0 (<code object generator at 0x104cc34b0, file "guo_code/lecture_09.py", line 1>)
              4 MAKE_FUNCTION
              6 STORE_NAME               0 (generator)

  5           8 PUSH_NULL
             10 LOAD_NAME                0 (generator)
             12 CALL                     0
             20 GET_ITER
        >>   22 FOR_ITER                11 (to 48)
             26 STORE_NAME               1 (x)

  6          28 PUSH_NULL
             30 LOAD_NAME                2 (print)
             32 LOAD_NAME                1 (x)
             34 CALL                     1
             42 POP_TOP
             44 JUMP_BACKWARD           13 (to 22)

  5     >>   48 END_FOR
             50 RETURN_CONST             1 (None)

Disassembly of <code object generator at 0x10561b4b0, file "guo_code/lecture_09.py", line 1>:
  1           0 RETURN_GENERATOR
              2 POP_TOP
              4 RESUME                   0

  2           6 LOAD_CONST               1 ('a')
              8 YIELD_VALUE              1
             10 RESUME                   1
             12 POP_TOP

  3          14 LOAD_CONST               2 ('b')
             16 YIELD_VALUE              1
             18 RESUME                   1
             20 POP_TOP
             22 RETURN_CONST             0 (None)
        >>   24 CALL_INTRINSIC_1         3 (INTRINSIC_STOPITERATION_ERROR)
             26 RERAISE                  1
ExceptionTable:
  4 to 22 -> 24 [0] lasti
```

The module-level code here should look familiar:
- We call `generator` which is just a normal function call from the caller point of view
- We call `GET_ITER` to convert the result to an iterator
- We do a `FOR_ITER` loop that pushes each `next` result on the stack, looping back
  until we get a `NULL` result in the C code and jump to the `END_FOR`.
  
  
So our interest is entirely in the semantics of the generator itself. Let's actually
si
```
def generator():
    for s in "some big string":
        yield s
```
which compiles to
```
  1           0 RETURN_GENERATOR
              2 POP_TOP
              4 RESUME                   0

  2           6 LOAD_CONST               1 ('a')
              8 YIELD_VALUE              1
             10 RESUME                   1
             12 POP_TOP

  3          14 LOAD_CONST               2 ('b')
             16 YIELD_VALUE              1
             18 RESUME                   1
             20 POP_TOP
             22 RETURN_CONST             0 (None)
        >>   24 CALL_INTRINSIC_1         3 (INTRINSIC_STOPITERATION_ERROR)
             26 RERAISE                  1
```

The bytecodes we need ot understand here are
- `RESUME`, which we've never actually looked at before although we've seen it at the start
  of module top-levels. Here we have a `RESUME` at the top and also after each yield.
- `YIELD_VALUE` which yields the top of the stack
- The use of `POP_TOP` ... we'll skip that for now, it's related to coroutines where
  the caller could inject data; we're popping an implicit `NONE` after each `RESUME`.
- The `CALL_INTRINSIC_1` and `RERAISE`, which are injecting the equivalent of
  an implicit `raise StopIteration`
  
  
**RESUME**

This opcode's actions:
- Do a few sanity checks on the frame
- Includes some instrumentation hooks that I don't need to understand yet
- In most cases jumps to `handle_eval_breaker` giving us a chance to swap contexts
  or do GC, etc
- dispatches to the next instruction

Note that the fact that RESUME is called on module top-levels means all these hooks
also exist on import.


**YIELD_VALUE**

This opcode:
- Grabs the top of the stack as the yield return value
- grabs a `PyGenObject *gen` from `_PyFrame_GetGenerator(frame)`
  - sets the state to suspended
  - resets the stack pointer back one (so that the yielded value is no longer
    on the stack when we resume)
  - Does some more munging on both `gen` and `tstate`
  - Calls `_Py_LeaveRecursiveCallPy(tstate)`
  - Assigns the current `frame` to `gen_frame`
  - Reassigns `frame` and `cframe.current_frame` to `frame->previous`
  - Eliminates `gen_frame->previous`
  - Calls `_PyFrame_StackPush(frame, retval`
  - Calls `goto resume_frame`
  
What this effectively means is:
- The frame's parent when we `yield` is always whoever is iterating over our
  generator (we'll presumably see later when we look at the implementation of
  `RETURN_GENERATOR` and the `tp_iter` of that how this is accomplished)
- When we reassign `frame` and `gen_frame` we make both frames available, which
  allows us to
  - strip `retval` from the current `gen_frame` frame
  - push `retval` to the parent `frame` which winds up accomplishing
    what we'll need to populate the `FOR_ITER` stack push
  - strip off the parent frame from `gen_frame` (because the next time we
    call next on this iterator we might be somewhere else!)
	
	
**RETURN_GENERATOR**

This opcode implementation:

- Accesses the current function from the frame, and creates a `PyGenObject`:
  `PyGenObject *gen = (PyGenObject *)_Py_MakeCoro(func);`
- Makes sure we've stored a lot of information in the current frame (which we
  are about to abandon) so that when we resume we can get it back, and then
  copies the frame into the `gen` object's `gi_iframe` field (because the
  current `frame` is associated with the interpreter loop and is about to get
  reassigned)
- Does some stuff I don't yet understand related to frame `frame->frame_obj`
- Calls `_Py_LeaveRecursiveCallPy(tstate)`
- Pops the current frame, and resets the frame to the previous frame (this
  jumps back to the caller), pushing the `gen` object onto the stack.
  
  
**PyGenObject**


The code for this lives in a few files:
- The most used declarations are in `pycore_genobject.h`
- The `PyGenObject` instance struct is defined, and the type object for it
  is declared, in `Include/cpython/genobject.h` along with most of the
  API functions.
- The implementations of the functions and the type object live in
  `genobject.c`

The struct itself is a slightly more complex macro that uses prefix concatenation
(via the `##` macro operator) to set a `gi_` prefix on all the fields.


The `PyGen_Type` declaration in `genobject.c` is the best place to understand
much of this logic, cross-referencing it against the bytecode implementations for
`RETURN_GENERATOR`, `FOR_ITER`, `YIELD`, and `RESUME`:
- It's a self-iterator type (`PyObject_SelfITER`)
- The next `tp_iternext` points to `gen_iternext`, which proxies to
  `gen_send_ex2` for most of the logic. This `gen_send_ex2` is where you can
  see most of the magic.
  
This logic will require a bit of wading through; it's complicated by the
presence of async; for historical reasons old-style generators, normal async
awaitables / futures, and async generators are all somewhat muddled.

I'll probably do well to study async logic (which Guo's lectures don't cover
since Python2 didn't have async) before doing a full in-depth study of
generators, since the ideas are similar but
- async is more powerful, I think, since the event loop can switch in more
  arbitrary ways than with generators
- async is also more important to understand well as a python expert these
  days
  
More modern resources probably cover this well; the Real Python blog post
has a very quick intro here:
https://realpython.com/cpython-source-code-guide/#a-review-of-the-generator-type
  
Another thing to eventually learn is the handling of `yield from`, which didn't
exist in Python2 either.

**Bonus: two-way generator coroutines**

Note that the bytecode for two-way generator logic looks identical to normal
"iterator-style" generator bytecode. The only difference is that you can use the
result of `yield` instead of just popping it. In the *caller* you'll call the
`send` function, which is bound in the `PyMethodDef` to `gen_send`.

The implementation of `gen_send` relies on `gen_send_ex` which in turn relies
on the same `gen_send_ex2` that we use in `gen_iternext`; the main difference
is that we pass a non-null `arg` in the send case.


There's also `throw` and `gen_throw`, which allows a caller to inject an exception
into a generator frame.
