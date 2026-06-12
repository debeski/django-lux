# Dlux .dlb viewer — build & cross-compile.
#
#   make            # build for the current platform -> ./build/dlb-viewer
#   make all        # cross-compile every target below into ./build/
#   make run FILE=x # build and run, opening x.dlb
#   make vet        # go vet
#   make clean      # remove ./build
#
# No third-party modules and no CGo, so cross-compilation is just GOOS/GOARCH.

GO      ?= go
BIN     := dlb-viewer
BUILDDIR:= build
LDFLAGS := -s -w
GOFLAGS := -trimpath
export CGO_ENABLED := 0

# target name : GOOS/GOARCH
PLATFORMS := \
	$(BUILDDIR)/$(BIN)-linux-amd64:linux/amd64 \
	$(BUILDDIR)/$(BIN)-linux-arm64:linux/arm64 \
	$(BUILDDIR)/$(BIN)-darwin-amd64:darwin/amd64 \
	$(BUILDDIR)/$(BIN)-darwin-arm64:darwin/arm64 \
	$(BUILDDIR)/$(BIN)-windows-amd64.exe:windows/amd64

.PHONY: build all run vet clean

# Default: native build for whatever machine you're on.
build:
	@mkdir -p $(BUILDDIR)
	$(GO) build $(GOFLAGS) -ldflags '$(LDFLAGS)' -o $(BUILDDIR)/$(BIN) .
	@echo "built $(BUILDDIR)/$(BIN)"

# Cross-compile every platform listed above.
all:
	@mkdir -p $(BUILDDIR)
	@set -e; for entry in $(PLATFORMS); do \
		out=$${entry%%:*}; \
		plat=$${entry##*:}; \
		os=$${plat%%/*}; arch=$${plat##*/}; \
		echo "  $$os/$$arch -> $$out"; \
		GOOS=$$os GOARCH=$$arch $(GO) build $(GOFLAGS) -ldflags '$(LDFLAGS)' -o $$out .; \
	done
	@echo "done -> $(BUILDDIR)/"

run: build
	./$(BUILDDIR)/$(BIN) $(FILE)

vet:
	$(GO) vet ./...

clean:
	rm -rf $(BUILDDIR)
