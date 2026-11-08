# Shortcuts for building and shipping the personal CLU image.
#
#   make build     build the image
#   make push      build + push to Docker Hub
#   make up        build + start/recreate the container with docker compose
#   make up-push   build + start the container + push to Docker Hub
#
# Override on the command line:  make push TAG=v1   (default: latest)
# docker-compose.yaml must use the same image name; it uses :latest.

IMAGE ?= xezeliars/comic-utils-web
TAG   ?= latest
REF   := $(IMAGE):$(TAG)

.PHONY: build push up up-push

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
