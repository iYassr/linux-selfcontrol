# Security

`selfctl` runs as root while a block is active, so its security matters more
than its features.

## What it is designed to guarantee

- A user without root cannot use `selfctl` to do anything except start a
  block (after authenticating with sudo or polkit) and make a running block
  stricter.
- Input from the unprivileged side is validated again from scratch by the
  privileged side. Only plain hostnames reach `/etc/hosts`.
- The daemon only runs a root-owned copy of `selfctl` that other users cannot
  write to. `selfctl start` refuses to run otherwise.
- No network access, ever.

## What it is not

It is not protection against the owner of the machine. A person with root and
enough patience can remove a block (see "How hard is it to undo" in the
README). Reports of new ways to do that quickly are welcome as normal issues;
they are bugs, not vulnerabilities.

## Reporting a vulnerability

If you find a way for a local user to gain privileges, corrupt system files,
or block or unblock names without authentication, please report it privately
through GitHub's "Report a vulnerability" button on the
[Security tab](https://github.com/iYassr/linux-selfcontrol/security/advisories/new)
rather than in a public issue. You should get a reply within a week.
