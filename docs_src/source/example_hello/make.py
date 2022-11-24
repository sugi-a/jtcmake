from pathlib import Path
from jtcmake import UntypedGroup, SELF

g = UntypedGroup("output", logfile="tmp-log.html")
g.add("hello.txt", Path.write_text)(SELF, "Hello!")

g.clean()
Path("tmp-log.html").unlink(missing_ok=True)

g.make()

