#!/bin/sh
# Initialise the rk817 codec on boot. Stock loong_service does this
# automatically but the launcher swap bypasses it. Two things are required or
# the speaker stays silent:
#   1. Route playback to the speaker (Playback Path -> SPK). Without it the
#      codec defaults to headphone output.
#   2. Un-mute the DAC. The rk817 powers up with DAC Playback Volume at 0
#      (-95 dB). PulseAudio applies the user-facing volume in software and never
#      touches this hardware element, so it must be raised here once and left
#      near max. The driver caps the value at 252 (~-2 dB) even though the
#      control advertises a max of 255.

amixer -c 1 cset numid=13 2 >/dev/null 2>&1        # Playback Path -> SPK
amixer -c 1 cset numid=16 252,252 >/dev/null 2>&1  # DAC Playback Volume -> ~max
