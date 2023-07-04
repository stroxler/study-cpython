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


