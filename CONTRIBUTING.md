# Contributing

Thanks for helping. The project aims to stay small: one Python file, standard
library only, readable in one sitting.

## Adding sites to a list

Lists live in [`lists/`](lists). One hostname per line.

- Add the bare domain (`example.com`). `www.` is added automatically.
- Add other subdomains people actually visit (`m.example.com`) on their own lines.
- Keep lists to well-known sites. Huge imported blocklists belong in a custom
  list, not in the defaults.
- Do not add sites people commonly need for work (Slack, Gmail, GitHub) to a
  default list.

Run `make test` before opening a pull request; it checks that every list parses
cleanly.

## Changing the code

- `make test` runs the unit tests without root, inside a temporary directory.
- `sh tests/system-test.sh` runs a real 40 second block on your machine.
- Keep Python 3.7 compatibility and add no dependencies.
- A change may make a running block stricter, never weaker. There must be no
  code path that ends a block early.

## Reporting a bug

Please include the output of `selfctl doctor` and your distribution.
