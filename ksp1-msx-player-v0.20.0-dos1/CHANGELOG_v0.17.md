# KSP1PLAY 0.17

## Added

- dual normal-SCC hardware flag support;
- optional SCC-B primary-slot command-line argument;
- relocatable ABI callbacks for selecting SCC A, selecting SCC B and restoring
  mapper RAM;
- reset/mute of both SCC devices on track changes, errors and exit;
- distinct validation error for identical dual-SCC slots;
- generic dynamic-gateway operand relocation based on KSP engine metadata.

## Removed

- complete Fray split-page profile;
- Fray-specific interrupt and address patches;
- fixed Parodius dynamic-gateway call-site patches;
- all title/game-name-dependent runtime behavior.

## Refactored

- dynamic pages now use the ABI-1 HL page index and package-declared gateway;
- live sparse replacement honors `replace_start` generically;
- dual-SCC callbacks preserve normal engine registers;
- hardware-profile validation accepts dual normal SCC but rejects dual SCC+;
- reduced resident code sufficiently that v0.17 is smaller than v0.16.
