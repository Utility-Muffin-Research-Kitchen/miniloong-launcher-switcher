#!/bin/sh
# Set the audio playback path to speaker on boot. Stock loong_service does this
# automatically but Jawaka bypasses it. Without this, the rk817 codec defaults
# to headphone output and the speaker is silent.

amixer -c 1 cset numid=13 2 >/dev/null 2>&1
