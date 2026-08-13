"""Entry point for `python -m simulation`.

Kept to the dispatch alone so the CLI itself stays importable and testable -
`simulation.cli.main(["--list"])` is a function call, not a subprocess.
"""

import sys

from simulation.cli import main

sys.exit(main())
