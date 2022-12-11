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
  In addition to the modification-timestamp-based skippability check, JTCMake
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
timestamp of the input/output files of each rule, and if the output files are
there and newer than the input files, JTCMake skips the rule to save
computation cost.

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


"Up-to-date" Criteria
=====================

When ordered to perform "make" on a set of rules, JTCMake does not necessarily
execute all of them: it skips the rules that are considered to be "up-to-date".
There are two major mechanisms used to judge whether a rule is skippable.

1. **mtime comparison** - if an input file is newer than an output file, 
   the rule is considered to be not skippable.
   The newness of the files is judged based on their mtime
   (modification-timestamp) attribute provided by the file system.
2. **Memoization** - if any input value (file content or python variable) is
   different from the one recorded last time the rule was "made", the rule
   is considered to be not skippable.

For each input file, you can configure which criterion to apply.
Files which are handled by memoization are called **value files**.
In other words, JTCMake does not check the mtime of a file if it is set to be
a *value file*. Instead, its content is checked.

Input python objects are basically all memoized but you can configure for
each of them how to memoize them. For example, you can exclude certain inputs
from the memoization list.


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


Defining Rules
==============

This section explains how to define rules in a group tree.
For the sake of simplicity, rules will be defined in a "flat" tree (tree with a
depth of 1) of :class:`RulesGroup`.
General group trees will be covered in `Construction of Group Trees`_ .


.. testcode:: defining_rules

  from __future__ import annotations
  from pathlib import Path
  from jtcmake import RulesGroup, SELF

  g = RulesGroup("output")

  def method(f1: Path, f2: Path, texts: list[str]):
      f1.write_text(texts[0])
      f2.write_text(texts[1])

  g.add("foo", { "a": "foo-a.txt", "b": "foo-b.txt" }, method)(
      SELF.a, SELF.b, ["abc", "xyz"]
  )

  g.make()

  assert Path("output/foo-a.txt").read_text() == "abc"
  assert Path("output/foo-b.txt").read_text() == "xyz"

The 2nd argument for ``add`` is a dictionary containing the output files.
It's keys are the *basenames* of the files and the corresponding values are the
*path-prefixes* of the files (see `Group Tree Model`_ for these terms).

The 3rd argument is the method to be used to create the output files.
All the output files must be passed to the method as parameters.

Calling ``add`` does not immediately appends a rule to the group.
Instead it returns a temporary function ``rule_adder`` whose signature is the
same as the ``method``, which is in this case
``(f1: Path, f2: Path, texts: list[str]) -> NoneType``.
Calling ``rule_adder`` with the arguments which must be eventually passed to
``method`` finishes the regstration of the new rule.
The key point here is to use the special constant :class:`jtcmake.SELF` to
represent the node of the new rule. There are several notations using ``SELF``
to specify the output files.

.. list-table::
  :header-rows: 1

  * - File
    - Attribute
    - Indexing with the basename
    - Indexing with the index
    - Bare self
  * - ``output/foo-a.txt``
    - ``SELF.a``
    - ``SELF["a"]``
    - ``SELF[0]``
    - ``SELF``
  * - ``output/foo-b.txt``
    - ``SELF.b``
    - ``SELF["b"]``
    - ``SELF[1]``
    - 

Accessing Rule/File nodes
-------------------------

You can reference the rule node either by the attribute-access or indxing:

.. testcode:: defining_rules

  from jtcmake import Rule

  assert isinstance(g.foo, Rule)
  assert g.foo is g["foo"]

You can get the output file nodes of the rule as follows:

.. testcode:: defining_rules

  from jtcmake import IFile

  foo = g.foo

  assert isinstance(foo.a, IFile)
  assert isinstance(foo.b, IFile)
  assert foo.a == foo["a"] == foo[0]
  assert foo.b == foo["b"] == foo[1]

File nodes implements the ``pathlib.Path`` interface

.. testcode:: defining_rules

  assert isinstance(foo.a, Path)
  assert isinstance(foo.b, Path)
  assert foo.a.samefile("output/foo-a.txt")
  assert foo.b.samefile("output/foo-b.txt")

Simpified Notation of Output Files
----------------------------------

``output_files`` passed to ``add`` can be a list (or tuple) of base-paths
instead of a dict.

.. testcode:: defining_rules

  from __future__ import annotations
  from pathlib import Path
  from jtcmake import RulesGroup, SELF

  g = RulesGroup("output")

  def method(f1: Path, f2: Path, texts: list[str]):
      f1.write_text(texts[0])
      f2.write_text(texts[1])

  g.add("foo", ["foo-a.txt", "foo-b.txt"], method)(
      SELF[0], SELF[1], ["abc", "xyz"]
  )

  g.make()

  assert Path("output/foo-a.txt").read_text() == "abc"
  assert Path("output/foo-b.txt").read_text() == "xyz"

  assert g.foo["foo-a.txt"].samefile("output/foo-a.txt")
  assert g.foo["foo-b.txt"].samefile("output/foo-b.txt")

When given a list ``[x, y, ...]`` instead of a dict, ``add`` converts it to a
dict ``{ str(x): x, str(y): y, ... }``.

``output_files`` may be a str or PathLike when there is only one output file
for the rule (which is the most common case):

.. testcode::

  from pathlib import Path
  from jtcmake import RulesGroup, SELF

  g = RulesGroup("output")

  g.add("foo", "foo-a.txt", Path.write_text)(SELF, "abc")

  g.make()

  assert g.foo[0].read_text() == "abc"

``output_files`` may even be completely omitted when the rule has only one
output file and its basename is equal to to its path-base:

.. testcode::

  from pathlib import Path
  from jtcmake import RulesGroup, SELF

  g = RulesGroup("output")

  g.add("foo-a.txt", Path.write_text)(SELF, "abc")

  g.make()

  assert Path("output/foo-a.txt").read_text() == "abc"


Decorator-style Registration
----------------------------

It is common that we need to define a dedicated method for a rule.
In that case, the decorator-style rule definition helps make your code concise.

Calling ``add`` with ``method`` omitted returns a decorator function.
Applying it to a function appends a new rule whose method is the decorated
function. All the arguments of the decorated function must have default values:

.. testcode:: defining_rules

  from __future__ import annotations
  from pathlib import Path
  from jtcmake import RulesGroup, SELF

  g = RulesGroup("output")

  @g.add("foo", { "a": "foo-a.txt", "b": "foo-b.txt" })
  def method(f1: Path=SELF.a, f2: Path=SELF.b, texts: list[str]=["abc", "xyz"]):
      f1.write_text(texts[0])
      f2.write_text(texts[1])

  g.make()

  assert Path("output/foo-a.txt").read_text() == "abc"
  assert Path("output/foo-b.txt").read_text() == "xyz"


Dependency of Rules
-------------------

Supplying a rule's outputs to another rule is as easy as putting the output
file nodes of the former rule as the arguments of the method of the latter rule.

.. testcode::

  from pathlib import Path
  from jtcmake import RulesGroup, SELF

  def invert(src: Path, dst: Path):
      dst.write_text(src.read_text()[::-1])

  g = RulesGroup("output")

  g.add("foo", "foo.txt", Path.write_text)(SELF, "123")

  g.add("bar", "bar.txt", invert)(g.foo[0], SELF)

  g.make()

  assert Path("output/foo.txt").read_text() == "123"
  assert Path("output/bar.txt").read_text() == "321"

You can omit the indexing, in this case, ``foo[0]`` (or ``foo["foo.txt"]``),
and write ::

  g.add("bar", "bar.txt", invert)(g.foo, SELF)

to pass the first (0-th) output file of the source rule.


Original Files
--------------

Like the C source files in `Example: Build Script for a C language project`_ ,
we often have input files that are not output files of a rule.
Here, we will refer to such files as *original files*.

We can define original files by wrapping them by :class:`jtcmake.File` .

.. testcode::

  from pathlib import Path
  from jtcmake import RulesGroup, SELF, File

  # Prepare an original file
  Path("tmp-original.txt").write_text("123")

  def invert(src: Path, dst: Path):
      dst.write_text(src.read_text()[::-1])

  g = RulesGroup("output")

  g.add("foo.txt", invert)(File("tmp-original.txt"), SELF)

  g.make()

  assert Path("output/foo.txt").read_text() == "321"


SELFs and Files in Nested Arguments
-----------------------------------

When passed to the ``rule_adder`` temporary function, ``SELF`` and Files may be
placed in a compound structure of ``list``, ``tuple``, ``dict``, and ``set`` .
i.e. JTCMake digs into nested structures like ``[{"a": (1, SELF.a)}]`` to find
SELF and Files and replace them with appropriate Path objects and resolve
dependency between rules.

.. testcode::

  from __future__ import annotations
  from pathlib import Path
  from jtcmake import RulesGroup, SELF

  g = RulesGroup("output")

  def summarize(
      source_files: dict[str, Path],  # mapping (title => path)
      dst: Path  # write summary to this files
  ):
      with dst.open("w") as f:
          for key, path in source_files.items():
              f.write(f"{key}: {path.read_text()}\n")

  g.add("foo", Path.write_text)(SELF, "abc")
  g.add("bar", Path.write_text)(SELF, "xyz")
  g.add("summary.txt", summarize)({ "FOO": g.foo, "BAR": g.bar }, SELF)

  g.make()

  print(g["summary.txt"][0].read_text())

.. testoutput::
  :options: +NORMALIZE_WHITESPACE

  FOO: abc
  BAR: xyz


Note that ``list``, ``tuple``, ``dict``, and ``set`` are the only supported
container types. JTCMake does not look inside other containers types like
``collections.deque`` or dataclasses.

Value File
----------

As explained in `"Up-to-date" Criteria`, JTCMake performs content-based
skippability check for **value files** rather than the mtime-based check.

Owned (not original) files may be declared to be value files in two ways.
First is Wrapping the base-path by :class:`jtcmake.VFile` when specifying the
``output_files`` for :func:`jtcmake.RulesGroup.add`

.. testcode::

  import time
  from pathlib import Path
  from jtcmake import RulesGroup, SELF, VFile, File

  g = RulesGroup("output")

  @g.add("foo", { "a": "a.txt", "b": VFile("b.txt" ) })
  def make_foo(a: Path = SELF.a, b: Path = SELF.b):
      a.touch(); b.touch()

  @g.add("bar")
  def make_bar(slf: Path = SELF, a: Path = g.foo.a, b: Path = g.foo.b):
      print("make_bar")
      slf.touch()

  assert isinstance(g.foo.a, File)   # g.foo.a is a normal file
  assert isinstance(g.foo.b, VFile)  # g.foo.b is a value file

  g.make()

  time.sleep(0.1)

  print("touch a")
  g.foo.a.touch()
  g.make()  # bar will be "made" because now "a.txt" is newer than bar

  time.sleep(0.1)

  print("touch b")
  g.foo.b.touch()
  g.make()  # bar will be skipped


.. testoutput::
  :options: +NORMALIZE_WHITESPACE
  
  make_bar
  touch a
  make_bar
  touch b

Alternatively you can use the APIs like
:func:`addvf <jtcmake.RulesGroup.addvf>` and
:func:`initvf <jtcmake.StaticGroupBase.initvf>` instead of 
:func:`add <jtcmake.RulesGroup.add>` and
:func:`init <jtcmake.StaticGroupBase.init>`.

.. testcode::

  from pathlib import Path
  from jtcmake import RulesGroup, SELF, VFile, File

  g = RulesGroup("output")

  @g.addvf("foo", { "a": "a.txt", "b": "b.txt" })
  def make_foo(a: Path = SELF.a, b: Path = SELF.b):
      a.touch(); b.touch()

  # Both a.txt and b.txt are value files
  assert isinstance(g.foo.a, VFile)
  assert isinstance(g.foo.b, VFile)

Original value files may be defined using :class:`jtcmake.VFile` just like
normal files are defined by :class:`jtcmake.File`.


Group Node Classes
==================

There are four classes that represent a group node.
The reason why there are four but not one is solely the capability of
fine-graned static program analysis.
If you write your code with no support from IDEs or static type checkers,
UntypedGroup alone is sufficient. But if you are to write a long complex code
and still be productive, you should use the other three classes
(StaticGroupBase, GroupsGroup, and RulesGroup) with an IDE and static type
checkers.

Here is a summary of the classes.

.. list-table:: Summary of Group Classes (1)
  :widths: 2 2 1 1 3
  :header-rows: 1

  * - Class Name
    - Children
    - Container
    - Typing
    - Analogous to
  * - StaticGroupBase
    - Groups/Rules
    - static
    - Strongest
    - TypedDict/dataclasses
  * - GroupsGroup
    - Groups
    - dynamic
    - Strong
    - ``dict[str, Group]``
  * - RulesGroup
    - Rules
    - dynamic
    - Strong
    - ``dict[str, Rule]``
  * - UntypedGroup
    - Groups/Rules
    - dynamic
    - Weak
    - ``dict[str, Group | Rule]``


StaticGroupBase
---------------

*StaticGroupBase* is the base class for *static groups*.
You should always subclass it to create a custom static group.
When subclassing it, you must give the names and types of the child nodes
(groups and rules) via type annotations:

.. testcode:: sample_StaticGroupBase

    from jtcmake import StaticGroupBase, Rule, SELF
    import jtcmake as jtc

    class AnotherCustomStaticGroup(StaticGroupBase):
        grandchild: Rule

    class CustomStaticGroup(StaticGroupBase):
        rule: Rule
        ggroup: jtc.GroupsGroup
        rgroup: jtc.RulesGroup
        ugroup: jtc.UntypedGroup
        sgroup: AnotherCustomStaticGroup
    
These child nodes are automatically instanciated when the parent node is
instanciated:

.. testcode:: sample_StaticGroupBase
    
    root = CustomStaticGroup("output")

    """
    By the above call, an instance of CustomStaticGroup is created, which
    triggers the automatic instanciation of the three children ``ggroup``,
    ``rgroup``, ``ugroup``, and ``sgroup``.
    Instanciation of sgroup (AnotherCustomStaticGroup) in turn invokes the
    instanciation of its child ``sgroup.grandchild``.
    """

    # You can read the child nodes without explicitly creating them
    assert isinstance(root.rule, Rule)
    assert isinstance(root.ggroup, jtc.GroupsGroup)
    assert isinstance(root.rgroup, jtc.RulesGroup)
    assert isinstance(root.ugroup, jtc.UntypedGroup)
    assert isinstance(root.sgroup, AnotherCustomStaticGroup)
    assert isinstance(root.sgroup.grandchild, Rule)

At this point, the children are instanciated but not complete.
You have to *initialize* the child rule ``root.rule`` by attaching methods and
inputs using :func:``jtcmake.Rule.init``.

.. testcode:: sample_StaticGroupBase

    from pathlib import Path

    root.rule.init("rule.txt", Path.write_text)(SELF, "Hello")

The dynamic-container-like child groups ``root.ggroup``, ``root.rgroup``, and
``root.ugroup`` are now empty.
You need to append children to them as necessary::

    # Append child groups to ``root.ggroup``.
    root.ggroup.add_group(...)

    # Append child rules to ``root.rgroup``.
    root.rgroup.add(...)

    # Append child groups and rules to ``root.ugroup``.
    root.ugroup.add_group(...)
    root.ugroup.add(...)

See the later sections and the API reference of GroupsGroup, RulesGroup, and
UntypedGroup for more information.

Finally, you need to *initialize* ``root.sgroup`` just as you did with the root.
i.e. you need to initialize ``root.sgroup.grandchild``

.. testcode:: sample_StaticGroupBase

    import shutil

    root.sgroup.grandchild.init("foo.txt", shutil.copy)(root.rule, SELF)
 

Now the whole group tree is initialized and you can, for example, check the
file paths::

    # 0-th file of ``root.rule`` (the only file of the rule)
    print(root.rule[0])

    # 0-th file of ``root.sgroup.grandchild`` (the only file of the rule )
    print(root.sgroup.grandchild[0])

.. code-block:: text

    output/rule.txt
    ouptut/sgroup/foo.txt


.. hint:: The *init method pattern*

    In the above example, the initialization code for the group tree is written
    in the top level block, i.e

    .. code-block::

        from pathlib import Path
        from jtcmake import StaticGroupBase, Rule, SELF
        import jtcmake as jtc

        class CustomStaticGroup(StaticGroupBase):
            rule: Rule
            ggroup: jtc.GroupsGroup
            rgroup: jtc.RulesGroup
            ugroup: jtc.UntypedGroup
            sgroup: AnotherCustomStaticGroup
        
        class AnotherCustomStaticGroup(StaticGroupBase):
            grandchild: Rule

        root = CustomStaticGroup("output")

        # Child rule of self
        root.rule.init("rule.txt", Path.write_text)(SELF, "Hello")

        # Child groups of self
        # root.ggroup.add_group(...) ...

        # Grandchild rule of self
        root.sgroup.grandchild.init("foo.txt", shutil.copy)(root.rule, SELF)

    A "flat" initialization code like this is hard to maintain and reuse
    (especially when it grows).
    Instead, a more modularized "init method pattern" is recommended::

        from pathlib import Path
        from jtcmake import StaticGroupBase, Rule, SELF
        import jtcmake as jtc

        class CustomStaticGroup(StaticGroupBase):
            rule: Rule
            ggroup: jtc.GroupsGroup
            rgroup: jtc.RulesGroup
            ugroup: jtc.UntypedGroup
            sgroup: AnotherCustomStaticGroup

            def init(self):
                # Child rule of self
                self.rule.init("rule.txt", Path.write_text)(SELF, "Hello")

                # Child groups of self
                # self.ggroup.add_group(...) ...

                # Grandchildren of self
                self.sgroup.init(self.rule)

        
        class AnotherCustomStaticGroup(StaticGroupBase):
            grandchild: Rule

            def init(self, src_file: Path):
                self.grandchild.init("foo.txt", shutil.copy)(src_file, SELF)


        root = CustomStaticGroup("output")
        root.init()


.. hint:: Precise Type Annotation

  In the above example, generic type parameters for the type annotations of
  child nodes are omitted.
  However in practice, you can, and basically you should, provide ones to get
  better support from IDEs and type checkers::

      class CustomStaticGroup(StaticGroupBase):
          rule: Rule[Literal["rule.txt"]]
          ggroup: jtc.GroupsGroup[YetAnotherCustomStaticGroup]
          rgroup: jtc.RulesGroup
          ugroup: jtc.UntypedGroup
          sgroup: AnotherCustomStaticGroup

  Generic type parameters are ignored at runtime.

.. seealso::

  - :class:`jtcmake.StaticGroupBase`.
  - :func:`Rule.init <jtcmake.Rule.init>`
  - :func:`Rule.initvf <jtcmake.Rule.initvf>`


GroupsGroup
-----------

*GroupsGroup* may have children of groups only.
You should use this class instead of `StaticGroupBase`_ when the child groups'
names are dynamically determined at run time.

.. testcode::

    from pathlib import Path
    from jtcmake import GroupsGroup, StaticGroupBase, Rule, SELF

    N = 100

    class CustomGroup(StaticGroupBase):
        __globals__ = globals()
        child: Rule[str]

        def init(self):
            self.child.init("a.txt", Path.write_text)(SELF, "abc")

    root: GroupsGroup[CustomGroup] = GroupsGroup("output")
    root.set_default_child(CustomGroup)

    for i in range(N):
        root.add_group(f"group{i}").set_prefix(prefix=f"{i}-").init()

    assert len(root.groups) == N
    assert str(root.group50.child[0]) == "output/50-a.txt"

The type hint ``GroupsGroup[CustomGroup]`` is only for static type checking
and ignored at runtime.

.. seealso::

  - :class:`jtcmake.GroupsGroup`.
  - :func:`jtcmake.GroupsGroup.add_group`


RulesGroup
----------

*RulesGroup* may have children of rules only.
You should use this class instead of `StaticGroupBase`_ when the child rules'
names are dynamically determined at run time.

.. testcode::

    from pathlib import Path
    from jtcmake import RulesGroup, SELF

    N = 100

    root = RulesGroup("output")

    for i in range(N):
        root.add(f"rule{i}", "<R>.txt", Path.write_text)(SELF, "abc")

    assert len(root.rules) == N
    assert str(root.rule50[0]) == "output/rule50.txt"


.. seealso::

  - :class:`jtcmake.RulesGroup`.
  - :func:`jtcmake.RulesGroup.add`
  - :func:`jtcmake.RulesGroup.addvf`


UntypedGroup
------------

*UntypedGroup* can have arbitrary number of groups and rules as children.
This class is a dynamic container: you can add child groups/rules to an instance
of UntypedGroup like you can insert items to a dict.

.. note::
  As mentioned at the beginning of this chapter, UntypedGroup is not sutable
  for creating a deep tree containing a large number of rules because it is
  weakly type-annotated.  Some sample codes in this tutorial use UntypedGroup
  only to keep them visually concise.

.. testcode:: sample_UntypedGroup

  import shutil
  from pathlib import Path
  from jtcmake import UntypedGroup, SELF, Rule

  # Create a root node
  g = UntypedGroup("output")

  # Append a rule
  g.add("foo.txt", Path.write_text)(SELF, "abc")

  # Append a group. The added group is also an UntypedGroup.
  g.add_group("bar")

  # Append a rule to the child group
  g.bar.add("baz.txt", shutil.copy)(g["foo.txt"], SELF)

  assert isinstance(g["foo.txt"], Rule)
  assert isinstance(g.bar, UntypedGroup)
  assert isinstance(g.bar["baz.txt"], Rule)


.. seealso::

  - :class:`jtcmake.UntypedGroup`.
  - :func:`jtcmake.UntypedGroup.add_group`
  - :func:`jtcmake.UntypedGroup.add`
  - :func:`jtcmake.UntypedGroup.addvf`


*************
Miscellaneous
*************

Make
====

Parallel Execution
------------------


Visualization
=============



