; KSPMENU.asm - KSP1PLAY v0.47.0 reloadable menu/UI module at 8000h
;
; Assembles byte-for-byte to the canonical 2048-byte
; KSPMENU.BIN. Names below are descriptive names unless otherwise
; documented. The five-entry jump table at 8000h is the stable interface used by
; the embedded player core.
;
; ABI jump table:
;   8000h -> VDP/TEXT-mode setup used when entering the menu
;   8003h -> full browser draw/open path
;   8006h -> bounded single-row update path (A = package index)
;   8009h -> redraw visible browser rows
;   800Ch -> return/restore hook into the resident player UI
;
org	08000h

kspmenu_entry_vdp_setup:
	jp l800fh		;8000
	jp kspmenu_entry_open_browser		;8003
kspmenu_entry_update_row:
	jp l8066h		;8006
kspmenu_entry_redraw_list:
	jp menu_redraw_visible_list		;8009
	jp kspmenu_entry_restore_player_ui		;800c
l800fh:
	di			;800f
l8010h:
	ld a,006h		;8010
	ld c,000h		;8012
	call menu_write_vdp_register		;8014
	ld a,060h		;8017
	ld c,001h		;8019
	call menu_write_vdp_register		;801b
	ld a,03fh		;801e
	ld c,002h		;8020
	call menu_write_vdp_register		;8022
	ld a,(0c0d1h)		;8025
	and 00fh		;8028
	ld c,007h		;802a
	call menu_write_vdp_register		;802c
	ld a,(0ffe7h)		;802f
	or 002h		;8032
	ld c,008h		;8034
	call menu_write_vdp_register		;8036
	ld a,(0ffe8h)		;8039
	and 002h		;803c
	or 080h		;803e
	ld c,009h		;8040
	call menu_write_vdp_register		;8042
	xor a			;8045
	ld c,012h		;8046
	call menu_write_vdp_register		;8048
	xor a			;804b
	ld c,017h		;804c
	call menu_write_vdp_register		;804e
	ei			;8051
	ret			;8052
kspmenu_entry_restore_player_ui:
	jp 03df2h		;8053
kspmenu_entry_open_browser:
	call sub_81ffh		;8056
	call sub_812ah		;8059
	call sub_815eh		;805c
	call menu_redraw_visible_list		;805f
	call sub_817fh		;8062
	ret			;8065
l8066h:
	ld c,a			;8066
	ld a,(02efch)		;8067
	ld e,a			;806a
	ld a,c			;806b
	sub e			;806c
	ret c			;806d
	ld b,a			;806e
	call menu_visible_row_count		;806f
	cp b			;8072
	ret c			;8073
	ret z			;8074
	ld a,c			;8075
	call menu_prepare_centered_title		;8076
	ld a,(02efbh)		;8079
	cp c			;807c
	jp nz,l808ah		;807d
	ld a,03eh		;8080
	ld (02f1ch),a		;8082
	ld a,03ch		;8085
	ld (02f59h),a		;8087
l808ah:
	ld a,(01a26h)		;808a
	add a,003h		;808d
	add a,b			;808f
	ld b,00fh		;8090
	ld hl,02f1bh		;8092
	jp l8256h		;8095
menu_redraw_visible_list:
	ld a,(02efch)		;8098
	ld (l83ach),a		;809b
	ld a,(01a26h)		;809e
	add a,003h		;80a1
	ld (l83adh),a		;80a3
	call menu_visible_row_count		;80a6
	ld b,a			;80a9
l80aah:
	push bc			;80aa
	ld a,(l83ach)		;80ab
	ld c,a			;80ae
	ld a,(02efah)		;80af
	cp c			;80b2
	jp z,l80d1h		;80b3
	jp c,l80d1h		;80b6
	ld a,c			;80b9
	call menu_prepare_centered_title		;80ba
	ld a,(02efbh)		;80bd
	cp c			;80c0
	jp nz,l80d4h		;80c1
	ld a,03eh		;80c4
	ld (02f1ch),a		;80c6
	ld a,03ch		;80c9
	ld (02f59h),a		;80cb
	jp l80d4h		;80ce
l80d1h:
	call sub_81f1h		;80d1
l80d4h:
	ld a,(l83adh)		;80d4
	ld b,00fh		;80d7
	ld hl,02f1bh		;80d9
	call l8256h		;80dc
	ld a,(l83ach)		;80df
	inc a			;80e2
	ld (l83ach),a		;80e3
	ld a,(l83adh)		;80e6
	inc a			;80e9
	ld (l83adh),a		;80ea
	pop bc			;80ed
	djnz l80aah		;80ee
	ret			;80f0
menu_prepare_centered_title:
	call 041a2h		;80f1
	call sub_81f1h		;80f4
	ld hl,02f5ch		;80f7
	ld b,03ch		;80fa
	ld c,000h		;80fc
l80feh:
	ld a,(hl)			;80fe
	or a			;80ff
	jp z,l8107h		;8100
	inc hl			;8103
	inc c			;8104
	djnz l80feh		;8105
l8107h:
	ld a,040h		;8107
	sub c			;8109
	srl a		;810a
	ld e,a			;810c
	ld d,000h		;810d
	ld hl,02f1bh		;810f
	add hl,de			;8112
	ex de,hl			;8113
	ld hl,02f5ch		;8114
	ld b,c			;8117
l8118h:
	ld a,b			;8118
	or a			;8119
	ret z			;811a
	ld a,(hl)			;811b
	ld (de),a			;811c
	inc hl			;811d
	inc de			;811e
	djnz l8118h		;811f
	ret			;8121
menu_visible_row_count:
	ld a,(01a26h)		;8122
	ld c,a			;8125
	ld a,010h		;8126
	sub c			;8128
	ret			;8129
sub_812ah:
	ld a,(01a26h)		;812a
	add a,a			;812d
	add a,a			;812e
	add a,a			;812f
	call sub_822ch		;8130
	ld a,(01a26h)		;8133
	add a,002h		;8136
	add a,a			;8138
	add a,a			;8139
	add a,a			;813a
	call sub_822ch		;813b
	ld a,098h		;813e
	call sub_822ch		;8140
	ld a,0a8h		;8143
	call sub_822ch		;8145
	ld a,(01a26h)		;8148
	add a,a			;814b
	add a,a			;814c
	add a,a			;814d
	ld d,a			;814e
	ld e,0a8h		;814f
l8151h:
	ld a,d			;8151
	push de			;8152
	call sub_823bh		;8153
	pop de			;8156
	inc d			;8157
	ld a,d			;8158
	cp e			;8159
	jp c,l8151h		;815a
	ret			;815d
sub_815eh:
	call sub_81f1h		;815e
	ld hl,l8195h		;8161
	ld de,02f1eh		;8164
	call sub_81e8h		;8167
	ld hl,l81a4h		;816a
	ld de,02f34h		;816d
	call sub_81e8h		;8170
	ld a,(01a26h)		;8173
	inc a			;8176
	ld b,00fh		;8177
	ld hl,02f1bh		;8179
	jp l8256h		;817c
sub_817fh:
	call sub_81f1h		;817f
	ld hl,l81b2h		;8182
	ld de,02f1fh		;8185
	call sub_81e8h		;8188
	ld a,014h		;818b
	ld b,00fh		;818d
	ld hl,02f1bh		;818f
	jp l8256h		;8192
l8195h:
menu_title_text:
	dec l			;8195
	dec l			;8196
	ld a,04bh		;8197
	ld d,e			;8199
	ld d,b			;819a
	ld sp,06c50h		;819b
	ld h,c			;819e
	ld a,c			;819f
	inc a			;81a0
	dec l			;81a1
	dec l			;81a2
	nop			;81a3
l81a4h:
menu_select_game_text:
	ld d,e			;81a4
	ld b,l			;81a5
	ld c,h			;81a6
	ld b,l			;81a7
	ld b,e			;81a8
	ld d,h			;81a9
	jr nz,l81edh		;81aa
	jr nz,$+73		;81ac
	ld b,c			;81ae
	ld c,l			;81af
	ld b,l			;81b0
	nop			;81b1
l81b2h:
menu_controls_text:
	ld d,l			;81b2
	ld d,b			;81b3
	cpl			;81b4
	ld b,h			;81b5
	ld c,a			;81b6
	ld d,a			;81b7
	ld c,(hl)			;81b8
	jr nz,l820eh		;81b9
	ld b,l			;81bb
	ld c,h			;81bc
	ld b,l			;81bd
	ld b,e			;81be
	ld d,h			;81bf
	jr nz,l81e2h		;81c0
	ld c,h			;81c2
	ld b,l			;81c3
	ld b,(hl)			;81c4
	ld d,h			;81c5
	cpl			;81c6
	ld d,d			;81c7
	ld c,c			;81c8
	ld b,a			;81c9
	ld c,b			;81ca
	ld d,h			;81cb
	jr nz,l821eh		;81cc
	ld b,c			;81ce
	ld b,a			;81cf
	ld b,l			;81d0
	jr nz,$+34		;81d1
	ld b,l			;81d3
	ld c,(hl)			;81d4
	ld d,h			;81d5
	ld b,l			;81d6
	ld d,d			;81d7
	jr nz,$+81		;81d8
	ld d,b			;81da
	ld b,l			;81db
	ld c,(hl)			;81dc
	jr nz,sub_81ffh		;81dd
	ld b,l			;81df
	ld d,e			;81e0
	ld b,e			;81e1
l81e2h:
	jr nz,$+71		;81e2
	ld e,b			;81e4
	ld c,c			;81e5
	ld d,h			;81e6
	nop			;81e7
sub_81e8h:
	ld a,(hl)			;81e8
	or a			;81e9
	ret z			;81ea
	ld (de),a			;81eb
	inc hl			;81ec
l81edh:
	inc de			;81ed
	jp sub_81e8h		;81ee
sub_81f1h:
	ld hl,02f1bh		;81f1
	ld b,040h		;81f4
	ld a,020h		;81f6
l81f8h:
	ld (hl),a			;81f8
	inc hl			;81f9
	djnz l81f8h		;81fa
	xor a			;81fc
	ld (hl),a			;81fd
	ret			;81fe
sub_81ffh:
	ld a,(01a26h)		;81ff
	add a,a			;8202
	add a,a			;8203
	add a,a			;8204
	ld e,a			;8205
l8206h:
	ld a,e			;8206
	cp 0d4h		;8207
	ret nc			;8209
	push de			;820a
	call sub_821dh		;820b
l820eh:
	call sub_8342h		;820e
	xor a			;8211
	ld b,080h		;8212
l8214h:
	out (098h),a		;8214
	djnz l8214h		;8216
	pop de			;8218
	inc e			;8219
	jp l8206h		;821a
sub_821dh:
	ld l,a			;821d
l821eh:
	ld h,000h		;821e
	add hl,hl			;8220
	add hl,hl			;8221
	add hl,hl			;8222
	add hl,hl			;8223
	add hl,hl			;8224
	add hl,hl			;8225
	add hl,hl			;8226
	ld de,kspmenu_entry_vdp_setup		;8227
	add hl,de			;822a
	ret			;822b
sub_822ch:
	call sub_821dh		;822c
	call sub_8342h		;822f
	ld a,0ffh		;8232
	ld b,080h		;8234
l8236h:
	out (098h),a		;8236
	djnz l8236h		;8238
	ret			;823a
sub_823bh:
	push af			;823b
	call sub_821dh		;823c
	call sub_8342h		;823f
	ld a,0f0h		;8242
	out (098h),a		;8244
	pop af			;8246
	call sub_821dh		;8247
	ld de,0007fh		;824a
	add hl,de			;824d
	call sub_8342h		;824e
	ld a,00fh		;8251
	out (098h),a		;8253
	ret			;8255
l8256h:
	ld (l83aeh),a		;8256
	ld a,b			;8259
	and 00fh		;825a
	ld (l83afh),a		;825c
	ld de,l83b1h		;825f
	ld b,040h		;8262
l8264h:
	ld a,(hl)			;8264
	or a			;8265
	jp z,l827dh		;8266
	cp 020h		;8269
	jp c,l827dh		;826b
	cp 080h		;826e
	jp c,l8275h		;8270
	ld a,03fh		;8273
l8275h:
	ld (de),a			;8275
	inc hl			;8276
	inc de			;8277
	djnz l8264h		;8278
	jp l8283h		;827a
l827dh:
	ld a,020h		;827d
l827fh:
	ld (de),a			;827f
	inc de			;8280
	djnz l827fh		;8281
l8283h:
	xor a			;8283
	ld (l83b0h),a		;8284
l8287h:
	ld a,(l83aeh)		;8287
	ld h,a			;828a
	ld l,000h		;828b
	add hl,hl			;828d
	add hl,hl			;828e
	ld de,kspmenu_entry_vdp_setup		;828f
	add hl,de			;8292
	ld a,(l83b0h)		;8293
	or a			;8296
	jp z,l82a5h		;8297
	ld e,a			;829a
	ld d,000h		;829b
l829dh:
	ld bc,00080h		;829d
	add hl,bc			;82a0
	dec e			;82a1
	jp nz,l829dh		;82a2
l82a5h:
	call sub_8342h		;82a5
	ld hl,l83b1h		;82a8
	ld b,040h		;82ab
l82adh:
	push bc			;82ad
	ld a,(hl)			;82ae
	inc hl			;82af
	push hl			;82b0
	call sub_82d7h		;82b1
	ld a,(l83b0h)		;82b4
	cp 005h		;82b7
	jp nc,l82c2h		;82b9
	call sub_82fdh		;82bc
	jp l82c3h		;82bf
l82c2h:
	xor a			;82c2
l82c3h:
	pop hl			;82c3
	call sub_831ah		;82c4
	pop bc			;82c7
	djnz l82adh		;82c8
	ld a,(l83b0h)		;82ca
	inc a			;82cd
	ld (l83b0h),a		;82ce
	cp 008h		;82d1
	jp c,l8287h		;82d3
	ret			;82d6
sub_82d7h:
	cp 061h		;82d7
	jp c,l82e3h		;82d9
	cp 07bh		;82dc
	jp nc,l82e3h		;82de
	sub 020h		;82e1
l82e3h:
	cp 020h		;82e3
	jp c,l82edh		;82e5
	cp 060h		;82e8
	jp c,l82efh		;82ea
l82edh:
	ld a,03fh		;82ed
l82efh:
	sub 020h		;82ef
	ld e,a			;82f1
	ld d,000h		;82f2
	ld h,d			;82f4
	ld l,e			;82f5
	add hl,hl			;82f6
	add hl,de			;82f7
	ld de,083f1h		;82f8
	add hl,de			;82fb
	ret			;82fc
sub_82fdh:
	cp 002h		;82fd
	jp c,l8310h		;82ff
	cp 004h		;8302
	jp c,l830dh		;8304
	inc hl			;8307
	inc hl			;8308
	ld a,(hl)			;8309
	and 007h		;830a
	ret			;830c
l830dh:
	inc hl			;830d
	sub 002h		;830e
l8310h:
	or a			;8310
	ld a,(hl)			;8311
	ret nz			;8312
	rrca			;8313
	rrca			;8314
	rrca			;8315
	rrca			;8316
	and 007h		;8317
	ret			;8319
sub_831ah:
	and 007h		;831a
	rlca			;831c
	rlca			;831d
	rlca			;831e
	rlca			;831f
	rlca			;8320
	ld c,a			;8321
	ld a,(l83afh)		;8322
	ld b,a			;8325
	rlca			;8326
	rlca			;8327
	rlca			;8328
	rlca			;8329
	ld d,a			;832a
	call sub_8332h		;832b
	call sub_8332h		;832e
	ret			;8331
sub_8332h:
	xor a			;8332
	sla c		;8333
	jp nc,l8339h		;8335
	or d			;8338
l8339h:
	sla c		;8339
	jp nc,l833fh		;833b
	or b			;833e
l833fh:
	out (098h),a		;833f
	ret			;8341
sub_8342h:
	ld a,h			;8342
	rlca			;8343
	rlca			;8344
	and 003h		;8345
	out (099h),a		;8347
	ld a,08eh		;8349
	out (099h),a		;834b
	ld a,l			;834d
	out (099h),a		;834e
	ld a,h			;8350
	and 03fh		;8351
	or 040h		;8353
	out (099h),a		;8355
	ret			;8357
menu_write_vdp_register:
	push af			;8358
	push bc			;8359
	ld b,a			;835a
	ld a,c			;835b
	cp 000h		;835c
	jp nz,l8368h		;835e
	ld a,b			;8361
	ld (0f3dfh),a		;8362
	jp l83a1h		;8365
l8368h:
	cp 001h		;8368
	jp nz,l8374h		;836a
	ld a,b			;836d
	ld (0f3e0h),a		;836e
	jp l83a1h		;8371
l8374h:
	cp 002h		;8374
	jp nz,l8380h		;8376
	ld a,b			;8379
	ld (0f3e1h),a		;837a
	jp l83a1h		;837d
l8380h:
	cp 007h		;8380
	jp nz,l838ch		;8382
	ld a,b			;8385
	ld (0f3e6h),a		;8386
	jp l83a1h		;8389
l838ch:
	cp 008h		;838c
	jp nz,l8398h		;838e
	ld a,b			;8391
	ld (0ffe7h),a		;8392
	jp l83a1h		;8395
l8398h:
	cp 009h		;8398
	jp nz,l83a1h		;839a
	ld a,b			;839d
	ld (0ffe8h),a		;839e
l83a1h:
	ld a,b			;83a1
	out (099h),a		;83a2
	ld a,c			;83a4
	or 080h		;83a5
	out (099h),a		;83a7
	pop bc			;83a9
	pop af			;83aa
	ret			;83ab
l83ach:
	nop			;83ac
l83adh:
	nop			;83ad
l83aeh:
	nop			;83ae
l83afh:
	rrca			;83af
l83b0h:
	xor a			;83b0
l83b1h:
	ld (0dcfeh),a		;83b1
	ld (0dcffh),a		;83b4
	ld a,(01c8eh)		;83b7
	or a			;83ba
	jp nz,07242h		;83bb
	ld a,(01c8fh)		;83be
	or a			;83c1
	jp nz,07242h		;83c2
	ld a,(01caah)		;83c5
	or a			;83c8
	jp nz,07242h		;83c9
	ld a,(01cabh)		;83cc
	or a			;83cf
	jp nz,07242h		;83d0
	ld a,(01cadh)		;83d3
	or a			;83d6
	jp nz,07242h		;83d7
	ld a,(01cafh)		;83da
	or a			;83dd
	jp nz,07242h		;83de
	ld a,(01caeh)		;83e1
	cp 020h		;83e4
	jp nz,07242h		;83e6
	ld a,(01cach)		;83e9
	or a			;83ec
	jp z,07242h		;83ed
	ld (0709ch),a		;83f0
	ld hl,(02022h)		;83f3
	ld (bc),a			;83f6
	ld d,l			;83f7
	nop			;83f8
	nop			;83f9
	ld d,a			;83fa
	ld d,a			;83fb
	dec b			;83fc
	ld (hl),023h		;83fd
	ld b,051h		;83ff
	inc h			;8401
	dec b			;8402
	dec h			;8403
	dec h			;8404
	inc bc			;8405
	ld (00000h),hl		;8406
	ld (de),a			;8409
	ld (04201h),hl		;840a
	ld (00504h),hl		;840d
	dec h			;8410
	nop			;8411
	ld (bc),a			;8412
	ld (hl),d			;8413
	nop			;8414
	nop			;8415
	ld (bc),a			;8416
	inc b			;8417
	nop			;8418
	ld (hl),b			;8419
	nop			;841a
	nop			;841b
	nop			;841c
	ld (bc),a			;841d
	ld de,00424h		;841e
	ld (hl),l			;8421
	ld d,l			;8422
	rlca			;8423
	ld h,022h		;8424
	rlca			;8426
	ld h,c			;8427
	ld (hl),h			;8428
	rlca			;8429
	ld h,c			;842a
	ld (hl),c			;842b
	ld b,055h		;842c
	ld (hl),c			;842e
	ld bc,06174h		;842f
	ld b,034h		;8432
	ld (hl),l			;8434
	rlca			;8435
	ld (hl),c			;8436
	ld (07502h),hl		;8437
	ld (hl),l			;843a
	rlca			;843b
	ld (hl),l			;843c
	ld (hl),c			;843d
	ld b,002h		;843e
	ld (bc),a			;8440
	nop			;8441
	ld (bc),a			;8442
	ld (bc),a			;8443
	inc b			;8444
	ld (de),a			;8445
	ld b,d			;8446
	ld bc,00707h		;8447
	nop			;844a
	ld b,d			;844b
	ld (de),a			;844c
	inc b			;844d
	ld h,c			;844e
	jr nz,l8453h		;844f
	ld (hl),l			;8451
	ld (hl),h			;8452
l8453h:
	rlca			;8453
	dec h			;8454
	ld (hl),l			;8455
	dec b			;8456
	ld h,l			;8457
	ld h,l			;8458
	ld b,034h		;8459
	ld b,h			;845b
	inc bc			;845c
	ld h,l			;845d
	ld d,l			;845e
	ld b,074h		;845f
	ld h,h			;8461
	rlca			;8462
	ld (hl),h			;8463
	ld h,h			;8464
	inc b			;8465
	inc (hl)			;8466
	ld d,l			;8467
	inc bc			;8468
	ld d,l			;8469
	ld (hl),l			;846a
	dec b			;846b
	ld (hl),d			;846c
	ld (01107h),hl		;846d
	dec d			;8470
	ld (bc),a			;8471
	ld d,l			;8472
	ld h,l			;8473
	dec b			;8474
	ld b,h			;8475
	ld b,h			;8476
	rlca			;8477
	ld d,a			;8478
	ld (hl),l			;8479
	dec b			;847a
	ld d,a			;847b
	ld (hl),a			;847c
	dec b			;847d
	dec h			;847e
	ld d,l			;847f
	ld (bc),a			;8480
	ld h,l			;8481
	ld h,h			;8482
	inc b			;8483
	dec h			;8484
	ld d,a			;8485
	inc bc			;8486
	ld h,l			;8487
	ld h,l			;8488
	dec b			;8489
	inc (hl)			;848a
	ld hl,07206h		;848b
	ld (05502h),hl		;848e
	ld d,l			;8491
	rlca			;8492
	ld d,l			;8493
	ld d,l			;8494
	ld (bc),a			;8495
	ld d,l			;8496
	ld (hl),a			;8497
	dec b			;8498
	ld d,l			;8499
	dec h			;849a
	dec b			;849b
	ld d,l			;849c
	ld (07102h),hl		;849d
	inc h			;84a0
	rlca			;84a1
	ld (00322h),a		;84a2
	ld b,h			;84a5
	ld hl,06201h		;84a6
	ld (02506h),hl		;84a9
	nop			;84ac
	nop			;84ad
	nop			;84ae
	nop			;84af
	rlca			;84b0
	call sub_87eeh		;84b1
	call 046b7h		;84b4
	call 02e39h		;84b7
	ld a,001h		;84ba
	ld b,017h		;84bc
	ld c,022h		;84be
	ld hl,l8573h		;84c0
	call 02dc0h		;84c3
	ld a,003h		;84c6
	ld b,005h		;84c8
	ld c,020h		;84ca
	ld hl,l8594h		;84cc
	call 02dc0h		;84cf
	ld a,005h		;84d2
	ld (l8572h),a		;84d4
	ld a,(0c318h)		;84d7
	bit 0,a		;84da
	call nz,sub_852ah		;84dc
	ld a,(0c318h)		;84df
	bit 1,a		;84e2
	call nz,sub_8532h		;84e4
	ld a,(0c318h)		;84e7
	bit 2,a		;84ea
	call nz,sub_853ah		;84ec
	ld a,(0c318h)		;84ef
	bit 3,a		;84f2
	call nz,sub_8542h		;84f4
	ld a,(0c318h)		;84f7
	bit 4,a		;84fa
	call nz,sub_854ah		;84fc
	ld a,(0c318h)		;84ff
	bit 5,a		;8502
	call nz,sub_8552h		;8504
	ld a,(0c318h)		;8507
	bit 6,a		;850a
	call nz,sub_855ah		;850c
	ld a,014h		;850f
	ld b,01ch		;8511
	ld c,017h		;8513
	ld hl,085ach		;8515
	call 02dc0h		;8518
	call 02b76h		;851b
l851eh:
	ei			;851e
	halt			;851f
	di			;8520
	call 02b98h		;8521
	cp 002h		;8524
	jp nz,l851eh		;8526
	ret			;8529
sub_852ah:
	ld hl,l85c4h		;852a
	ld c,028h		;852d
	jp l8562h		;852f
sub_8532h:
	ld hl,l85c8h		;8532
	ld c,028h		;8535
	jp l8562h		;8537
sub_853ah:
	ld hl,l85cch		;853a
	ld c,028h		;853d
	jp l8562h		;853f
sub_8542h:
	ld hl,l85d1h		;8542
	ld c,028h		;8545
	jp l8562h		;8547
sub_854ah:
	ld hl,l85dah		;854a
	ld c,028h		;854d
	jp l8562h		;854f
sub_8552h:
	ld hl,l85f6h		;8552
	ld c,028h		;8555
	jp l8562h		;8557
sub_855ah:
	ld hl,l8608h		;855a
	ld c,028h		;855d
	jp l8562h		;855f
l8562h:
	ld a,(l8572h)		;8562
	ld b,008h		;8565
	call 02dc0h		;8567
	ld a,(l8572h)		;856a
	inc a			;856d
	ld (l8572h),a		;856e
	ret			;8571
l8572h:
	nop			;8572
l8573h:
hardware_title_text:
	dec l			;8573
	dec l			;8574
	ld a,04bh		;8575
	ld d,e			;8577
	ld d,b			;8578
	ld sp,04c50h		;8579
	ld b,c			;857c
	ld e,c			;857d
	inc a			;857e
	dec l			;857f
	dec l			;8580
	jr nz,l85c7h		;8581
	ld h,l			;8583
	ld (hl),h			;8584
	ld h,l			;8585
	ld h,e			;8586
	ld (hl),h			;8587
	ld h,l			;8588
	ld h,h			;8589
	jr nz,l85d4h		;858a
	ld h,c			;858c
	ld (hl),d			;858d
	ld h,h			;858e
	ld (hl),a			;858f
	ld h,c			;8590
	ld (hl),d			;8591
	ld h,l			;8592
	nop			;8593
l8594h:
hardware_devices_text:
	ld b,h			;8594
	ld h,l			;8595
	ld (hl),h			;8596
	ld h,l			;8597
	ld h,e			;8598
	ld (hl),h			;8599
	ld h,l			;859a
	ld h,h			;859b
	jr nz,l85ffh		;859c
	ld (hl),l			;859e
	ld h,h			;859f
	ld l,c			;85a0
	ld l,a			;85a1
	jr nz,l8608h		;85a2
	ld h,l			;85a4
	halt			;85a5
	ld l,c			;85a6
	ld h,e			;85a7
	ld h,l			;85a8
	ld (hl),e			;85a9
	ld a,(05000h)		;85aa
	ld (hl),d			;85ad
	ld h,l			;85ae
	ld (hl),e			;85af
	ld (hl),e			;85b0
	jr nz,l85f8h		;85b1
	ld c,(hl)			;85b3
	ld d,h			;85b4
	ld b,l			;85b5
	ld d,d			;85b6
	jr nz,$+118		;85b7
	ld l,a			;85b9
	jr nz,$+101		;85ba
	ld l,a			;85bc
	ld l,(hl)			;85bd
	ld (hl),h			;85be
	ld l,c			;85bf
	ld l,(hl)			;85c0
	ld (hl),l			;85c1
	ld h,l			;85c2
	nop			;85c3
l85c4h:
	ld d,b			;85c4
	ld d,e			;85c5
	ld b,a			;85c6
l85c7h:
	nop			;85c7
l85c8h:
	ld d,e			;85c8
	ld b,e			;85c9
	ld b,e			;85ca
	nop			;85cb
l85cch:
hardware_sccplus_text:
	ld d,e			;85cc
	ld b,e			;85cd
	ld b,e			;85ce
	dec hl			;85cf
	nop			;85d0
l85d1h:
hardware_dual_scc_text:
	ld b,h			;85d1
	ld (hl),l			;85d2
	ld h,c			;85d3
l85d4h:
	ld l,h			;85d4
	jr nz,l862ah		;85d5
	ld b,e			;85d7
	ld b,e			;85d8
	nop			;85d9
l85dah:
hardware_fmpac_text:
	ld b,(hl)			;85da
	ld c,l			;85db
	dec l			;85dc
	ld d,b			;85dd
	ld b,c			;85de
	ld b,e			;85df
	jr nz,l8611h		;85e0
	jr nz,l8631h		;85e2
	ld d,e			;85e4
	ld e,b			;85e5
	dec l			;85e6
	ld c,l			;85e7
	ld d,l			;85e8
	ld d,e			;85e9
	ld c,c			;85ea
	ld b,e			;85eb
	jr nz,l8616h		;85ec
	ld e,c			;85ee
	ld c,l			;85ef
	ld (03134h),a		;85f0
	inc sp			;85f3
	add hl,hl			;85f4
	nop			;85f5
l85f6h:
hardware_msxaudio_text:
	ld c,l			;85f6
	ld d,e			;85f7
l85f8h:
	ld e,b			;85f8
	dec l			;85f9
	ld b,c			;85fa
	ld d,l			;85fb
	ld b,h			;85fc
	ld c,c			;85fd
	ld c,a			;85fe
l85ffh:
	jr nz,$+49		;85ff
	jr nz,$+91		;8601
	jr c,l863eh		;8603
	dec (hl)			;8605
	jr nc,l8608h		;8606
l8608h:
hardware_moonsound_text:
	ld c,l			;8608
	ld l,a			;8609
	ld l,a			;860a
	ld l,(hl)			;860b
	ld d,e			;860c
	ld l,a			;860d
	ld (hl),l			;860e
	ld l,(hl)			;860f
	ld h,h			;8610
l8611h:
	jr nz,l8642h		;8611
	jr nz,l8664h		;8613
	ld d,b			;8615
l8616h:
	ld c,h			;8616
	inc (hl)			;8617
	xor b			;8618
	inc e			;8619
	ld (0709ah),hl		;861a
	ld hl,(0709ah)		;861d
	xor a			;8620
	ld de,01d80h		;8621
	ld bc,00020h		;8624
	call 0022eh		;8627
l862ah:
	or a			;862a
	jp nz,07242h		;862b
	ld hl,01d80h		;862e
l8631h:
	ld a,(hl)			;8631
	cp 049h		;8632
	jp nz,0722eh		;8634
	inc hl			;8637
	ld a,(hl)			;8638
	cp 04dh		;8639
	jp nz,0722eh		;863b
l863eh:
	inc hl			;863e
	ld a,(hl)			;863f
	cp 047h		;8640
l8642h:
	jp nz,0722eh		;8642
	inc hl			;8645
	ld a,(hl)			;8646
	cp 035h		;8647
	jp nz,0722eh		;8649
	ld a,(01d86h)		;864c
	or a			;864f
	jp nz,0722eh		;8650
	ld a,(01d8ah)		;8653
	or a			;8656
	jp nz,0722eh		;8657
	ld a,(01d8bh)		;865a
	or a			;865d
	jp nz,0722eh		;865e
	ld hl,(01d8ch)		;8661
l8664h:
	ld de,01ac0h		;8664
	or a			;8667
	sbc hl,de		;8668
	jp nz,0722eh		;866a
	ld a,(01d8eh)		;866d
	or a			;8670
	jp nz,0722eh		;8671
	ld a,(01d8fh)		;8674
	or a			;8677
	jp nz,0722eh		;8678
	ld hl,(01d88h)		;867b
	xor a			;867e
	ld de,kspmenu_entry_vdp_setup		;867f
	ld bc,01ac0h		;8682
	call 0022eh		;8685
	or a			;8688
	jp nz,0722eh		;8689
	ld hl,kspmenu_entry_vdp_setup		;868c
	ld a,(hl)			;868f
	cp 049h		;8690
	jp nz,0722eh		;8692
	inc hl			;8695
	ld a,(hl)			;8696
	cp 035h		;8697
	jp nz,0722eh		;8699
	inc hl			;869c
	ld a,(hl)			;869d
	cp 056h		;869e
	jp nz,0722eh		;86a0
	inc hl			;86a3
	ld a,(hl)			;86a4
	cp 031h		;86a5
	jp nz,0722eh		;86a7
	ld a,(08004h)		;86aa
	cp 080h		;86ad
	jp nz,0722eh		;86af
	ld a,(08005h)		;86b2
	or a			;86b5
	jp nz,0722eh		;86b6
	ld a,(kspmenu_entry_update_row)		;86b9
	cp 06ah		;86bc
	jp nz,0722eh		;86be
	ld a,(kspmenu_entry_update_row+1)		;86c1
	or a			;86c4
	jp nz,0722eh		;86c5
	ld a,(kspmenu_entry_update_row+2)		;86c8
	cp 040h		;86cb
	jp nz,0722eh		;86cd
	ld a,(kspmenu_entry_redraw_list)		;86d0
	or a			;86d3
	jp nz,0722eh		;86d4
	ld a,(kspmenu_entry_redraw_list+1)		;86d7
	cp 010h		;86da
	jp nz,0722eh		;86dc
	ld a,(kspmenu_entry_redraw_list+2)		;86df
	or a			;86e2
	jp nz,0722eh		;86e3
	ld a,(0dcfeh)		;86e6
	or a			;86e9
	jp nz,0721fh		;86ea
	call 07248h		;86ed
	call 07263h		;86f0
	call 07290h		;86f3
	ld a,(0dcfeh)		;86f6
	inc a			;86f9
	ld (0dcfeh),a		;86fa
	cp 004h		;86fd
	jp z,07242h		;86ff
	ld hl,(0709ah)		;8702
	ld de,00020h		;8705
	add hl,de			;8708
	ld (0709ah),hl		;8709
	ld a,(0709ch)		;870c
	dec a			;870f
	ld (0709ch),a		;8710
	jp nz,07149h		;8713
	call 072e7h		;8716
	jp 02d31h		;8719
	call 018bah		;871c
	ld hl,kspmenu_entry_vdp_setup		;871f
	ld a,001h		;8722
	call 018dbh		;8724
	ld bc,06a00h		;8727
	xor a			;872a
	out (098h),a		;872b
	dec bc			;872d
	ld a,b			;872e
	or c			;872f
	jp nz,07256h		;8730
	call 018cch		;8733
	ret			;8736
	call 018bah		;8737
	ld hl,0ea00h		;873a
	ld a,001h		;873d
	call 018dbh		;873f
	ld hl,09a90h		;8742
	ld b,010h		;8745
l8747h:
	ld a,(hl)			;8747
	and 007h		;8748
	rlca			;874a
	rlca			;874b
	rlca			;874c
	rlca			;874d
	ld d,a			;874e
	inc hl			;874f
	ld e,(hl)			;8750
	inc hl			;8751
	ld a,(hl)			;8752
	and 007h		;8753
	or d			;8755
	out (098h),a		;8756
	ld a,e			;8758
	and 007h		;8759
	out (098h),a		;875b
	inc hl			;875d
	djnz l8747h		;875e
	call 018cch		;8760
	ret			;8763
	ld hl,kspmenu_entry_vdp_setup		;8764
	ld a,(0dcfeh)		;8767
	bit 0,a		;876a
	jp z,0729fh		;876c
	ld de,00040h		;876f
	add hl,de			;8772
	bit 1,a		;8773
	jp z,072a8h		;8775
	ld de,03500h		;8778
	add hl,de			;877b
	ld (070a0h),hl		;877c
	ld hl,l8010h		;877f
	ld (0709dh),hl		;8782
	ld a,06ah		;8785
	ld (0709fh),a		;8787
	call 018bah		;878a
	ld hl,(070a0h)		;878d
	ld a,001h		;8790
	call 018dbh		;8792
	ld hl,(0709dh)		;8795
	ld b,040h		;8798
l879ah:
	ld a,(hl)			;879a
	out (098h),a		;879b
	inc hl			;879d
	djnz l879ah		;879e
	ld (0709dh),hl		;87a0
	call 018cch		;87a3
	ld hl,(070a0h)		;87a6
	ld de,00080h		;87a9
	add hl,de			;87ac
	ld (070a0h),hl		;87ad
	ld a,(0709fh)		;87b0
	dec a			;87b3
	ld (0709fh),a		;87b4
	jp nz,072b6h		;87b7
	ret			;87ba
	call 018bah		;87bb
	ld hl,0789ah		;87be
	xor a			;87c1
	call 018dbh		;87c2
	ld hl,07312h		;87c5
	ld a,(0dcfeh)		;87c8
	or a			;87cb
	jp z,072feh		;87cc
	ld hl,0730ah		;87cf
	ld b,008h		;87d2
l87d4h:
	ld a,(hl)			;87d4
	out (098h),a		;87d5
	inc hl			;87d7
	djnz l87d4h		;87d8
	call 018cch		;87da
	ret			;87dd
images_label_text:
	ld c,c			;87de
	jr nz,$+75		;87df
	ld c,l			;87e1
	ld b,c			;87e2
	ld b,a			;87e3
	ld b,l			;87e4
	ld d,e			;87e5
	jr nz,$+34		;87e6
	jr nz,$+34		;87e8
	jr nz,$+34		;87ea
	jr nz,$+34		;87ec
sub_87eeh:
	call 03dc0h		;87ee
	xor a			;87f1
	ld (0f3eah),a		;87f2
	ld (0f3ebh),a		;87f5
	ret			;87f8
	nop			;87f9
	nop			;87fa
	nop			;87fb
	nop			;87fc
	nop			;87fd
	nop			;87fe
	nop			;87ff
