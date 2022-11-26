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

1. Create a *group tree* and define *rules* as the nodes in the group tree
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
  :file: example_hello/tmp-log.html

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
  build tools dedicated to that purpose, which may be practically preferable.


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

Running ``$ python make.py`` will make all, which turns ``./out`` to be

.. literalinclude:: ./example_c_build/_tmp-tree-out.txt

Alternatively, we can make a subset of rules by, for example,
``$ python make.py liba``, which generates *liba* and its dependencies only.

.. literalinclude:: ./example_c_build/_tmp-tree-liba.txt

Visualization
-------------

It is possible to visualize the group tree structure and rule dependencies.
For example, ::

  import jtcmake
  jtcmake.print_graphviz(g.tools.tool1, "graph.svg")

creates the picture below in which all the dependencies of ``tool1`` and their
structure are illustrated.

.. image:: ./example_c_build/_tmp-graph-tool1.svg

Dry-run
-------

Like most build tools, JTCMake can print which rules would be executed instead
of actually executing them.
It is as easy as running ``make()`` with ``dry_run=True``. ::

  g.liba.make(dry_run=True)

Outputs will be

.. literalinclude:: example_c_build/_tmp-log.txt

Skipping Completed Rules
------------------------

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


*************
Core Concepts
*************

This chapter describes some major concepts of JTCMake.
The actual APIs are explained in the `Construction of Group Trees`_ chapter.

Rules and Dependency
====================

Rules are the the smallest unit of work. A rule consists of a *method* that
takes some inputs (*input files* and other kind of Python objects like integers)
and produces files (*output files*).

.. image:: _static/rule_in_out.svg

Dependency between two rules is judged based on the input/output files:
when an output file of rule *A* is an input to rule *B*, *B* is considered to
depend on *A*.

Dependencies between a set of rules can be described using a dependency graph.
JTCMake imposes a restriction on dependency graphs that they must be asyclic.


Group Tree Model
================

JTCMake maintains the definition of rules in a tree called *group tree*,
instead of storing them in a flat data structure.
Group trees may contain three kinds of nodes:

.. list-table:: Group Tree Nodes
  :header-rows: 1

  * - Kind
    - Role
    - Properties
    - Children
  * - Group
    - cluster of rules.
    - | ``basename``
      | ``path-prefix``
    - arbitrary number of groups and rules
  * - Rule
    - a rule (unit of task).
    - ``basename``
    - 1 or more files
  * - File
    - an output file of a rule
    - | ``basename``
      | ``path-base``
    - 

.. image:: ./figure_group_tree/tmp-group-tree.svg
  :width: 1200

Every node in the tree can be specified using its (fully qualified) *name* which
is the *basenames* of all its ancesters and itself concatenated.
For example, the name of the leftmost rule in the above figure is
``<ROOT>.foo.a`` and its second child's name is ``<ROOT>.foo.a.f2``.

Similarly, the (fully qualified) *path* of any file node is given by joining
*path-prefixes* of its ancester groups and the *path-base* of itself.
For example, the six files in the above figure have names and paths as follows.

.. literalinclude:: ./figure_group_tree/tmp-files.txt

Managing rules this way serves two benefits:

**Namespacing**

  Putting relevant rules or sets of rules into the same logical block lowers
  the cognitive load on the programmer and promote modularization of the code.

**Path Mapping**

  By designing the group nodes to represent the actual directories or, in
  general, common prefixes of the file paths, the whole group tree naturally and
  intuitively corresponds to the whole directory tree.
  It again reduces the cognitive load to comprehend the tasks and their outputs. 


***************************
Construction of Group Trees
***************************

As described in the `Overview`_ chapter, our first step in the JTCMake workflow
is to create a group tree that holds the definition of rules inside.

Group Node Classes
==================

There are four classes that represent a group node.
Here is a summary of the classes.

.. list-table:: Group Tree Nodes
  :widths: 2 2 1 1 3
  :header-rows: 1

  * - Class Name
    - Children
    - Dynamic
    - Typing
    - Analogous to
  * - UntypedGroup
    - Groups/Rules
    - Yes
    - Weak
    - ``dict[str, Group | Rule]``
  * - GroupsGroup
    - Groups
    - Yes
    - Strong
    - ``dict[str, Group]``
  * - RulesGroup
    - Rules
    - Yes
    - Strong
    - ``dict[str, Rule]``
  * - StaticGroupBase
    - Groups/Rules
    - No
    - Strongest
    - TypedDict/dataclass

UntypedGroup
------------

See also :class:`jtcmake.UntypedGroup`.

*UntypedGroup* can have arbitrary number of groups and rules as children.
This class a dynamic container: you can add child groups/rules to an instance
of UntypedGroup like you can insert items to a dict.

It's weakly type-annotated. For example, getting a non-static attribute like 
``some_untyped_group.a`` is annotated to return Any, so type checkers don't
know whether it is supposed to be a child group/rule with the basename "a"
or an ``AttributeError``.
In most cases, you should be able to satisfy your requirements using the other
three classes, and, in those cases, you should do so.


StaticGroupBase
---------------

See also :class:`jtcmake.StaticGroupBase`.

*StaticGroupBase* is the base class for *static groups*.
You should always subclass it to create a custom static group.
When subclassing it, you must give the names and types of the child nodes
(groups and rules) using type annotations::

    from jtcmake import StaticGroupBase, GroupsGroup, Rule

    class CustomStaticGroup(StaticGroupBase):
        foo: Rule
        bar: GroupsGroup
        baz: AnotherCustomStaticGroup
    
    class AnotherCustomStaticGroup(StaticGroupBase):
        qux: Rule

These child nodes are automatically instanciated when the parent node is
instanciated::
    
    root = CustomStaticGroup()
    """
    By the above call, an instance of CustomStaticGroup is created, which
    triggers the automatic instanciation of the three children foo, bar and baz.
    Instanciation of baz (AnotherCustomStaticGroup) in turn invokes the
    instanciation of its child qux.
    """

    # You can read the child nodes even though you didn't create them explicitly
    assert isinstance(root.foo, Rule)
    assert isinstance(root.bar, GroupsGroup)
    assert isinstance(root.baz, AnotherCustomStaticGroup)
    assert isinstance(root.baz.qux, Rule)


GroupsGroup
-----------

See also :class:`jtcmake.GroupsGroup`.


RulesGroup
----------

See also :class:`jtcmake.RulesGroup`.



***********
Memoization
***********


*************
Miscellaneous
*************

Make
====

Parallel Execution
------------------


Visualization
=============



