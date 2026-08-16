# TinyKSP 1.9.4 release notes

- Corrects custom MWK 12-bit and 16-bit sample length handling.
- MWK payload sizes are byte counts, but YMF278B loop/end positions are decoded
  sample counts. TinyKSP 1.9.3 incorrectly used the byte count as the playback
  length for non-8-bit custom waves.
- Retains all 1.9.3 OPL4 pitch, PCM-format, timing, FMPAC and KSP 1.05 fixes.
