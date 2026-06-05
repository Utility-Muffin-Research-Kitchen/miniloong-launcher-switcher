#!/bin/sh
# Initialise the rk817 codec on boot. Stock loong_service does this
# automatically but Leaf mode bypasses it. Three things are required or audio is
# wrong:
#   1. Route playback to the speaker (Playback Path -> SPK). Without it the
#      codec defaults to headphone output.
#   2. Pin the DAC to a fixed, sane level. The rk817 powers up with DAC Playback
#      Volume at 0 (-95 dB = silent), and its volume taper is extremely steep
#      (0-255 -> -95..-1 dB), so it is the dominant loudness control. We pin it
#      here and let the user-facing volume run through PulseAudio's *software*
#      sink volume (the launcher's volume buttons call `pactl set-sink-volume`),
#      which does NOT move this hardware element. 210 is the calibrated
#      "comfortably loud" ceiling for the speaker; 252 (driver max) is painfully
#      loud, ~167 is barely audible.
#   3. Keep the external speaker gate on while rk817 playback is active. Stock
#      loong_service/loong_power normally drive /sys/kernel/powerCtrl/spk_ctl;
#      in Leaf mode, direct ALSA/PulseAudio playback is silent unless this gate
#      is raised during the stream.

amixer -c 1 cset numid=13 2 >/dev/null 2>&1        # Playback Path -> SPK
amixer -c 1 cset numid=16 210,210 >/dev/null 2>&1  # DAC Playback Volume -> calibrated ceiling

SPK_CTL=/sys/kernel/powerCtrl/spk_ctl
PCM_STATUS=/proc/asound/card1/pcm0p/sub0/status
PIDFILE=/tmp/umrk-audio-spk-keeper.pid

if [ -w "$SPK_CTL" ] && [ -r "$PCM_STATUS" ]; then
    old_pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if [ -n "$old_pid" ] && [ -d "/proc/$old_pid" ]; then
        exit 0
    fi

    (
        while true; do
            if grep -q '^state: RUNNING' "$PCM_STATUS" 2>/dev/null; then
                echo 1 > "$SPK_CTL" 2>/dev/null || true
            fi
            sleep .2
        done
    ) >/dev/null 2>&1 &
    echo "$!" > "$PIDFILE" 2>/dev/null || true
fi
