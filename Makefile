PREFIX ?= /usr/local

.PHONY: test install uninstall screenshots

test:
	python3 -B -m unittest discover -s tests -v

install:
	PREFIX=$(PREFIX) DESTDIR=$(DESTDIR) sh install.sh

uninstall:
	PREFIX=$(PREFIX) DESTDIR=$(DESTDIR) sh install.sh --uninstall

screenshots:
	python3 tools/screenshots.py
