SHELL := /bin/bash

BUILD ?= build
SD_DIR := $(BUILD)/sd

# Launcher payload location. The workspace orchestrator assembles the payload
# (build Jawaka + gather Catastrophe/RetroArch/cores) and points BUNDLE_ROOT at
# it; standalone use defaults to this repo's build/package.
BUNDLE_ROOT ?= $(BUILD)/package
BUNDLE_DIR := $(BUNDLE_ROOT)/umrk-launcher

.PHONY: help sd-payload sd-payload-marked \
        adb-install-wrapper adb-uninstall-wrapper \
        adb-stage-sd-bundle adb-stage-sd-bundle-no-marker \
        adb-enable-marker adb-disable-marker adb-restart-loong adb-tail-logs \
        clean

help:
	@echo "miniloong-launcher-switcher — MLP1 stock launcher swap mechanism."
	@echo "Consumes an assembled launcher payload (BUNDLE_ROOT=$(BUNDLE_ROOT))."
	@echo ""
	@echo "  make sd-payload [BUNDLE_ROOT=<dir>]    generate the SD OTA install payload"
	@echo "  make sd-payload-marked                 ... with the activation marker"
	@echo "  make adb-stage-sd-bundle               stage payload to device + enable marker"
	@echo "  make adb-stage-sd-bundle-no-marker     stage without activating"
	@echo "  make adb-enable-marker | adb-disable-marker"
	@echo "  make adb-restart-loong | adb-tail-logs"
	@echo "  make adb-install-wrapper | adb-uninstall-wrapper"
	@echo ""
	@echo "Payload assembly lives in the workspace: 'make stage-jawaka' / 'make assemble-jawaka'."

# Generate the SD-root OTA install payload around an assembled launcher bundle.
sd-payload:
	@test -x "$(BUNDLE_DIR)/bin/loong_pangu" || { \
		echo "no launcher payload at $(BUNDLE_DIR)" >&2; \
		echo "assemble it first (workspace: make assemble-jawaka), or pass BUNDLE_ROOT=<dir>" >&2; \
		exit 1; }
	@rm -rf "$(SD_DIR)"
	python3 make_launcher_switcher_sd.py --force "$(SD_DIR)"
	@cp -R "$(BUNDLE_DIR)" "$(SD_DIR)/umrk-launcher"
	@if [ -d "$(BUNDLE_ROOT)/UMRK" ]; then cp -R "$(BUNDLE_ROOT)/UMRK" "$(SD_DIR)/UMRK"; fi
	@find "$(SD_DIR)" -maxdepth 5 -type f | sort

sd-payload-marked: sd-payload
	@touch "$(SD_DIR)/.umrk-launcher"
	@echo "Added marker: $(SD_DIR)/.umrk-launcher"

adb-stage-sd-bundle:
	BUNDLE_ROOT="$(BUNDLE_ROOT)" scripts/adb-stage-sd-bundle.sh --marker

adb-stage-sd-bundle-no-marker:
	BUNDLE_ROOT="$(BUNDLE_ROOT)" scripts/adb-stage-sd-bundle.sh --no-marker

adb-install-wrapper:
	scripts/adb-install-wrapper.sh

adb-uninstall-wrapper:
	scripts/adb-uninstall-wrapper.sh

adb-enable-marker:
	scripts/adb-set-marker.sh on

adb-disable-marker:
	scripts/adb-set-marker.sh off

adb-restart-loong:
	scripts/adb-restart-loong.sh

adb-tail-logs:
	scripts/adb-tail-logs.sh

clean:
	rm -rf "$(BUILD)"
