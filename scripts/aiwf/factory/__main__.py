"""`python -m aiwf.factory [run|doctor]`; `run` (the default) is what the LaunchDaemon starts."""

import sys

from aiwf.factory import doctor, m0


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "run"
    if cmd == "doctor":
        return doctor.main()
    if cmd == "run":
        return m0.main()
    print("usage: python -m aiwf.factory [run|doctor]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
