.. testcleanup:: *

   import shutil, sys
   try:
     sys.stderr.write("cleaning up output/\n")
     shutil.rmtree("output")
   except:
     pass
  

#################
JTCMake Tutorial
#################

JTCMake is a general purpose incremental build framework.

It shares the essence with Makefile:

* Users define a set of rules to produce files
* JTCMake analyzes the dependency of the rules and executes them in an
  appropriate order, skipping ones whose outputs already exist and are
  up-to-date

Furthermore, JTCMake has strong features such as

Content-based Skippability Check
  In addition to the modification-time-based skippability check, JTCMake
  can be configured to check if a rule is skippable based on the input files'
  content modification.

Expressiveness and Portability
  you can leverage Python's expressiveness to write rules with complex logic
  and the code ships with different platforms including Windows.

Structured rule management
  JTCMake manages rules in a well structured manner, which enables intuitive
  handling of a large number of files spanning deep directory trees.

Fine-grained static typing
  The API design has been tuned to fit into the Python ecosystem around static
  typing.
  Major operations on rules and files on your code would be aided by your
  IDE and validated by static type checkers
  (Pyright/Pylance is recommended but Mypy should work too).

  Combined with the *structured rule management*, this feature enables you to
  write a large and complex program safely and efficiently.

Peripheral Equipment
  Convenient tools such as a dependency graph visualizer and node selectors
  are provided.


************
Installation
************

.. code-block:: text

   $ pip install jtcmake


Additionally, Graphviz executables need to be in PATH when you use the
:func:`jtcmake.print_graphviz` function.


********
Overview
********

Typical workflow using JTCMake consists of two steps:

1. Create a *group tree* and define *rules* as nodes in the tree
2. Call ``make()`` on a sub-tree (or the root) to execute the rules


Example: Writing to a file
===========================

Our first example task is to write "Hello!" into ``output/hello.txt``.
For this task, we would write a Makefile below:

.. code-block:: Makefile

  outputs/hello.txt:
      mkdir -p $$(dirname $@)  # make directory for hello.txt
      echo "Hello!" > $@       # write to hello.txt

and then call ``$ make``. Its JTCMake counterpart looks like:

.. testcode:: hello
  
  from pathlib import Path
  from jtcmake import UntypedGroup, SELF

  # 1. Define a group tree
  # Create the root node
  g = UntypedGroup("output")

  # Define a rule node
  g.add("hello.txt", Path.write_text)(SELF, "Hello!")

  # 2. Make the whole tree
  g.make()

  assert Path("output/hello.txt").read_text() == "Hello!"

Note you don't need to make the directory by yourself.
You will see the following log after running ``g.make()``

------

.. raw:: html

  <html><head><meta charset="utf-8"><title>log</title></head><body><pre><span style="color: rgb(0, 0, 0);background-color: rgb(255, 255, 255);">Make </span><span style="color: rgb(0, 204, 0);background-color: rgb(255, 255, 255);">hello</span><span style="color: rgb(0, 0, 0);background-color: rgb(255, 255, 255);">
  </span><span style="color: rgb(0, 128, 255);background-color: rgb(255, 255, 255);">  write_text</span><span style="color: rgb(0, 0, 0);background-color: rgb(255, 255, 255);">(
  </span><span style="color: rgb(255, 128, 0);background-color: rgb(255, 255, 255);">    path</span><span style="color: rgb(0, 0, 0);background-color: rgb(255, 255, 255);"> = </span><a href="output/hello.txt"><span style="color: rgb(0, 0, 0);background-color: rgb(255, 255, 255);">PosixPath(&#x27;output/hello.txt&#x27;)</span></a><span style="color: rgb(0, 0, 0);background-color: rgb(255, 255, 255);">,
  </span><span style="color: rgb(255, 128, 0);background-color: rgb(255, 255, 255);">    text</span><span style="color: rgb(0, 0, 0);background-color: rgb(255, 255, 255);"> = &#x27;Hello!&#x27;,
    )
  </span></pre></body></html><html><head><meta charset="utf-8"><title>log</title></head><body><pre><span style="color: rgb(0, 0, 0);background-color: rgb(255, 255, 255);">Done </span><span style="color: rgb(0, 204, 0);background-color: rgb(255, 255, 255);">hello</span><span style="color: rgb(0, 0, 0);background-color: rgb(255, 255, 255);">
  </span></pre></body></html>

------

On Jupyter Notebook and Jupyter Lab, Paths are printed as HTML links so you
can quickly review the files.

This example task is so simple that you actually don't need a "framework"
and instead you would just write::

  Path("output/hello.txt").write_text("Hello!")

JTCMake helps when your task involves many files to be output.


Example: Build Script for a C language project
==============================================

Let's take a look at a more complex task: building a C language project.

.. note::

  This example is for demonstration purposes only. There are well established
  tools dedicated to that purpose, which may be practically preferable.


Let's say our project has source files in the following layout:

.. literalinclude:: ./example_c_build/_tmp-tree-all.txt

We have two libraries "liba" and "libb" whose sources are in ``./src/liba``
and ``src/libb``, respectively.
We also have five executables to be generated whose *main* functions are
written in ``./tools/tool1.c``, ..., ``./tools/tool5.c``, respectively.

The requirements for our build script (``./make.py``) are:

* It needs to generate the executables (``tool1``, ``tool2``, ...) in
  ``./out/tools``.
* It also needs to generate the two static libraries ``liba.a`` and ``libb.a``
  in ``./out/libs``.
* Other intermediate outputs such as .o files must be put under ``./out`` as
  well.
* Each executable depends on the two libraries. So we need to link liba and
  libb into the executables.

Here is our ``./make.py``:

.. literalinclude:: ./example_c_build/make.py
  :linenos:

We can make all by ``$ python make.py``, which turns ``./out`` to be

.. literalinclude:: ./example_c_build/_tmp-tree-out.txt

Alternatively, we can make a subset of rules by, for example,
``$ python make.py liba``, which generates *liba* and its dependencies only.

.. literalinclude:: ./example_c_build/_tmp-tree-liba.txt


Re-run
------

Just like Makefile, JTCMake by default checks the existence and modification
time of the input/output files of each rule, and if the output files are there
and newer than the input files, JTCMake skips the rule to save computation cost.

Additionally, JTCMake supports content-based check of execution necessesity.
In the above code, we use that feature (by :class:`jtcmake.VFile`,
:func:`jtcmake.Rule.initvf`, and so on) so re-running the script
with the source files unchanged results in no-op.


Summary
=======

JTCMake performs incremental build in a define-and-run manner.
Subsequent sections will describe the concepts and usage of JTCMake in detail.


****************
Group Tree Model
****************

Rule
====


Group Tree
==========


***************************
Construction of Group Trees
***************************

Group Node Classes
==================

StaticGroupBase
---------------

GroupsGroup
-----------

RulesGroup
----------

UntypedGroup
------------


***********
Memoization
***********


*************
Miscellaneous
*************
