# AiiDA docker stacks

### Build images locally

To build the images, run `docker buildx bake -f build.json -f docker-bake.hcl --load` (tested with *docker buildx* version v0.8.2).

The build system will attempt to detect the local architecture and automatically build images for it (tested with amd64 and arm64).
All commands `build`, `tests`, and `up` will use the locally detected platform and use a version tag based on the state of the local git repository.
However, you can also specify a custom platform with the `--platform`, example: `docker buildx bake -f build.json -f docker-bake.hcl --set *.platform=linux/amd64 --load`.

### Trigger a build on ghcr.io and dockerhub

Only the PR open to the organization repository will trigger a build on ghcr.io.
Push to dockerhub is triggered when making a release on github.
