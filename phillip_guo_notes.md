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
