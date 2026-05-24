SHELL := /bin/bash

BUILD ?= build
TOOLCHAIN_DIR ?= /Volumes/Storage/UMRK/mlp1-toolchain
TOOLCHAIN_IMAGE ?= ghcr.io/utility-muffin-research-kitchen/mlp1-toolchain:local
CATASTROPHE_DIR ?= /Volumes/Storage/UMRK/Catastrophe
JAWAKA_DIR ?= /Volumes/Storage/UMRK/Jawaka
RETROARCH_BUILDS_DIR ?= /Volumes/Storage/UMRK/retroarch-builds
CORES_SPRUCE_DIR ?= /Volumes/Storage/UMRK/Cores-spruce
MLP1_RETROARCH_BIN ?= $(RETROARCH_BUILDS_DIR)/output/mlp1/bin/retroarch
MLP1_CORES_DIR ?= $(CORES_SPRUCE_DIR)/output/mlp1/cores
MLP1_INFO_DIR ?= $(CORES_SPRUCE_DIR)/output/mlp1/info
MLP1_VERTICAL_CORE ?= genesis_plus_gx

POC_BIN := $(BUILD)/bin/loong_pangu
PACKAGE_ROOT := $(BUILD)/package
PACKAGE_DIR := $(PACKAGE_ROOT)/umrk-launcher
PLATFORM_PACKAGE_DIR := $(PACKAGE_ROOT)/UMRK/mlp1
SD_DIR := $(BUILD)/sd
JAWAKA_BUILD_DIR := $(JAWAKA_DIR)/build/mlp1

.PHONY: all image poc target-poc package jawaka-build retroarch-mlp1 cores-mlp1 jawaka-package jawaka-mlp1-vertical-slice sd-payload sd-payload-marked jawaka-sd-payload jawaka-sd-payload-marked adb-poc-test adb-install-wrapper adb-stage-sd-bundle adb-stage-sd-bundle-no-marker adb-stage-jawaka-sd-bundle adb-stage-jawaka-sd-bundle-no-marker adb-stage-jawaka-mlp1-vertical-slice adb-enable-marker adb-disable-marker adb-restart-loong adb-tail-logs adb-uninstall-wrapper clean

all: package sd-payload

image:
	@if ! docker image inspect "$(TOOLCHAIN_IMAGE)" >/dev/null 2>&1; then \
		echo "Building $(TOOLCHAIN_IMAGE) from $(TOOLCHAIN_DIR)"; \
		docker build -t "$(TOOLCHAIN_IMAGE)" "$(TOOLCHAIN_DIR)"; \
	fi

poc: image
	docker run --rm \
		-v "$(CURDIR)":/workspace \
		-w /workspace \
		"$(TOOLCHAIN_IMAGE)" \
		make target-poc

target-poc:
	@mkdir -p "$(BUILD)/bin"
	$(CC) -std=gnu11 -O2 -Wall -Wextra -Wno-unused-parameter \
		$$(pkg-config --cflags sdl2 SDL2_ttf) \
		-o "$(POC_BIN)" \
		src/poc_launcher.c \
		$$(pkg-config --libs sdl2 SDL2_ttf)
	$(READELF) -l "$(POC_BIN)" | grep 'Requesting program interpreter'
	$(READELF) -d "$(POC_BIN)" | grep 'Shared library'

package: poc
	@rm -rf "$(PACKAGE_ROOT)"
	@mkdir -p "$(PACKAGE_DIR)/bin" "$(PACKAGE_DIR)/res"
	@cp -f "$(POC_BIN)" "$(PACKAGE_DIR)/bin/loong_pangu"
	@if [ -f "$(CATASTROPHE_DIR)/res/font.ttf" ]; then cp -f "$(CATASTROPHE_DIR)/res/font.ttf" "$(PACKAGE_DIR)/res/font.ttf"; fi
	@printf 'UMRK launcher switcher POC bundle\n' > "$(PACKAGE_DIR)/README.txt"
	@find "$(PACKAGE_DIR)" -type f -print

jawaka-build:
	$(MAKE) -C "$(JAWAKA_DIR)" mlp1

retroarch-mlp1:
	"$(RETROARCH_BUILDS_DIR)/build-mlp1.sh"

cores-mlp1:
	"$(CORES_SPRUCE_DIR)/build-mlp1.sh" "$(MLP1_VERTICAL_CORE)"

jawaka-package: jawaka-build
	@rm -rf "$(PACKAGE_ROOT)"
	@mkdir -p "$(PACKAGE_DIR)/bin" "$(PACKAGE_DIR)/res" "$(PLATFORM_PACKAGE_DIR)"
	@cp -f "$(JAWAKA_BUILD_DIR)/bin/jawakad" "$(PACKAGE_DIR)/bin/loong_pangu"
	@cp -f "$(JAWAKA_BUILD_DIR)/bin/jawaka-launcher" "$(PACKAGE_DIR)/bin/jawaka-launcher"
	@cp -f "$(JAWAKA_BUILD_DIR)/bin/jawaka-menu" "$(PACKAGE_DIR)/bin/jawaka-menu"
	@chmod 755 "$(PACKAGE_DIR)/bin/"*
	@cp -Rf "$(JAWAKA_DIR)/res/themes" "$(PACKAGE_DIR)/res/"
	@cp -Rf "$(CATASTROPHE_DIR)/res/fonts" "$(PACKAGE_DIR)/res/"
	@cp -f "$(CATASTROPHE_DIR)/res/font.ttf" "$(PACKAGE_DIR)/res/font.ttf"
	@if [ -d "$(CATASTROPHE_DIR)/.cache/nextui-preview/assets" ]; then cp -Rf "$(CATASTROPHE_DIR)/.cache/nextui-preview/assets" "$(PACKAGE_DIR)/res/assets"; fi
	@cp -Rf "device/mlp1/." "$(PLATFORM_PACKAGE_DIR)/"
	@if [ -f "$(MLP1_RETROARCH_BIN)" ]; then \
		mkdir -p "$(PLATFORM_PACKAGE_DIR)/bin"; \
		cp -f "$(MLP1_RETROARCH_BIN)" "$(PLATFORM_PACKAGE_DIR)/bin/retroarch"; \
		chmod 755 "$(PLATFORM_PACKAGE_DIR)/bin/retroarch"; \
	else \
		echo "warning: MLP1 RetroArch not found at $(MLP1_RETROARCH_BIN); launches will fail clear until it is built."; \
	fi
	@if [ -d "$(MLP1_CORES_DIR)" ]; then \
		mkdir -p "$(PLATFORM_PACKAGE_DIR)/cores"; \
		find "$(MLP1_CORES_DIR)" -maxdepth 1 -type f -name '*_libretro.so' -exec cp -f {} "$(PLATFORM_PACKAGE_DIR)/cores/" \;; \
		chmod 755 "$(PLATFORM_PACKAGE_DIR)/cores/"*_libretro.so 2>/dev/null || true; \
	else \
		echo "warning: MLP1 cores not found at $(MLP1_CORES_DIR); launches will fail clear until cores are built."; \
	fi
	@if [ -d "$(MLP1_INFO_DIR)" ]; then \
		mkdir -p "$(PLATFORM_PACKAGE_DIR)/info"; \
		find "$(MLP1_INFO_DIR)" -maxdepth 1 -type f -name '*_libretro.info' -exec cp -f {} "$(PLATFORM_PACKAGE_DIR)/info/" \;; \
	fi
	@printf 'Jawaka MLP1 launcher bundle\n' > "$(PACKAGE_DIR)/README.txt"
	@find "$(PACKAGE_ROOT)" -type f -print | sort

jawaka-mlp1-vertical-slice: retroarch-mlp1 cores-mlp1 jawaka-sd-payload

sd-payload: package
	@rm -rf "$(SD_DIR)"
	python3 make_launcher_switcher_sd.py --force "$(SD_DIR)"
	@cp -R "$(PACKAGE_DIR)" "$(SD_DIR)/umrk-launcher"
	@find "$(SD_DIR)" -maxdepth 3 -type f -print | sort

sd-payload-marked: sd-payload
	@touch "$(SD_DIR)/.umrk-launcher"
	@echo "Added marker: $(SD_DIR)/.umrk-launcher"

jawaka-sd-payload: jawaka-package
	@rm -rf "$(SD_DIR)"
	python3 make_launcher_switcher_sd.py --force "$(SD_DIR)"
	@cp -R "$(PACKAGE_ROOT)/umrk-launcher" "$(SD_DIR)/umrk-launcher"
	@cp -R "$(PACKAGE_ROOT)/UMRK" "$(SD_DIR)/UMRK"
	@find "$(SD_DIR)" -maxdepth 5 -type f -print | sort

jawaka-sd-payload-marked: jawaka-sd-payload
	@touch "$(SD_DIR)/.umrk-launcher"
	@echo "Added marker: $(SD_DIR)/.umrk-launcher"

adb-poc-test: package
	scripts/adb-poc-test.sh

adb-install-wrapper:
	scripts/adb-install-wrapper.sh

adb-stage-sd-bundle: package
	scripts/adb-stage-sd-bundle.sh --marker

adb-stage-sd-bundle-no-marker: package
	scripts/adb-stage-sd-bundle.sh --no-marker

adb-stage-jawaka-sd-bundle: jawaka-package
	scripts/adb-stage-sd-bundle.sh --marker

adb-stage-jawaka-sd-bundle-no-marker: jawaka-package
	scripts/adb-stage-sd-bundle.sh --no-marker

adb-stage-jawaka-mlp1-vertical-slice: jawaka-mlp1-vertical-slice
	scripts/adb-stage-sd-bundle.sh --marker

adb-enable-marker:
	scripts/adb-set-marker.sh on

adb-disable-marker:
	scripts/adb-set-marker.sh off

adb-restart-loong:
	scripts/adb-restart-loong.sh

adb-tail-logs:
	scripts/adb-tail-logs.sh

adb-uninstall-wrapper:
	scripts/adb-uninstall-wrapper.sh

clean:
	rm -rf "$(BUILD)"
