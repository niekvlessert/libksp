; recon_host_image.asm - stored RECON runtime image
;
; The readable runtime source is runtime/RECON_RUNTIME.asm (runtime ORG C400h).
; build.py assembles it and generates the exact host byte image included here.

recon_overlay_image:
include "../generated/RECON_RUNTIME_IMAGE.inc"
