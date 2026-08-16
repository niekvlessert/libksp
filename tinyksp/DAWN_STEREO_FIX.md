# Dawn of Sorrow stereo correction

This source is TinyKSP 1.9.5 with one production change: the libvgm YMF278B
adapter now carries its native left and right outputs through Opl4Device and
KspVm instead of averaging them to mono and duplicating that mono sample into
both WAV/playback channels.

This is required for the Dawn of Sorrow SSEQ arrangements, which use independent
track pan positions and delayed stereo doubles. No KSP format change is made.

Known pre-existing issue: the bundled synthetic `yamaha_smoke` custom-PCM test
still fails in the original 1.9.5 libvgm path, although the Dawn MWK resources
load and render. That issue is separate from this stereo correction.
