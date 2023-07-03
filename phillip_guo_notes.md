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
c = compile('guo_notes/lecture_02_a.py', 'test.py', 'exec')
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

### A few things I learned from poking around while watching lecture 2

I think varargs / splatted keyword args may be handled by something other
than the `co_.*` fields of code objects, because as far as I could tell
there was no field that would tell you how to handle that.

Top-level code doesn't use locals - the names have to be in the globals
table, and as a result top-levels won't make much use of `LOAD_FAST`; they'll
use `LOAD_NAME` instead.

I'm not really sure why, but top-levels also don't seem to make much use
of `co_consts`. This is a bit of a mystery to me at this point.


