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
    - f_funcobj, f_global, f_builtins, f_locals; all of these are runtime
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
