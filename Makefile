# Shortcuts for building and shipping the personal CLU image.
#
#   make build          build the image
#   make push           build + push to Docker Hub
#   make up             build + start/recreate the container with docker compose
#   make up-push        build + start the container + push to Docker Hub
#   make down           stop the container
#
#   make sync-upstream  merge the author's latest main into develop (never pushes)
#   make test           run the test suite in the image (about 25 minutes)
#   make test ARGS=tests/unit/test_fork_version.py   run only some tests
#
# Chain them:  make sync-upstream test
#
# Override on the command line:  make push TAG=v1   (default: latest)
# docker-compose.yaml must use the same image name; it uses :latest.

IMAGE ?= xezeliars/comic-utils-web
TAG   ?= latest
REF   := $(IMAGE):$(TAG)
ARGS  ?=

# From PowerShell/cmd, make runs recipes with cmd.exe, so the shell scripts go
# through the sh that ships with Git for Windows.
ifeq ($(OS),Windows_NT)
SH := "$(shell git --exec-path)/../../../bin/sh.exe"
else
SH := sh
endif

# Run from Git Bash, MSYS would rewrite the container paths below (/work).
export MSYS_NO_PATHCONV := 1

.PHONY: build push up up-push down sync-upstream test

build:
	docker build -t $(REF) .

push: build
	docker push $(REF)

# --pull never: use the image just built, never a remote one with the same name.
up: build
	docker compose up -d --pull never

up-push: up
	docker push $(REF)

down:
	docker compose down

sync-upstream:
	$(SH) scripts/sync-upstream.sh

test:
	docker run --rm -v "$(CURDIR):/work" -w /work --entrypoint sh $(REF) scripts/docker-pytest.sh $(ARGS)
