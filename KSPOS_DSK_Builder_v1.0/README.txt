KSPOS DSK Builder v1.0
======================

Deze tool maakt een bootbare 720-KiB FAT12 KSPOS-DSK van:

  * een uitgepakte directory met KSPOS-bestanden; of
  * rechtstreeks van een ZIP met die bestanden.

Python 3 is voldoende; er zijn geen externe packages nodig.

Snelste gebruik
---------------

  python3 kspos_dsk_builder.py KSP1PLAY_v0.22.28_SHOVEL_KNIGHT_DiskContents.zip SHOVEL.DSK

Of vanuit een uitgepakte directory:

  python3 kspos_dsk_builder.py SHOVEL_DIRECTORY SHOVEL.DSK

Daarna bijvoorbeeld:

  openmsx -diska SHOVEL.DSK

De directory of ZIP moet KSPBOOT.BIN bevatten. AUTOEXEC.BAS, AUTOEXEC.BAT en
MSXDOS.SYS zijn niet nodig: de meegeleverde KSPOS-bootsector opent
KSPBOOT.BIN zelf via de DiskROM.

Belangrijk bij nieuwe player-versies
------------------------------------

De standaard meegeleverde bootsector hoort bij KSPOS/KSP1PLAY v0.22.28 en
controleert dat KSPBOOT.BIN exact bij die versie hoort.

Voor een latere versie gebruik je een bekende werkende DSK uit diezelfde build
als template:

  python3 kspos_dsk_builder.py NIEUWE_FILES NIEUW.DSK --template-dsk WERKENDE_VERSIE.DSK

De builder neemt dan de bootsector uit de template en controleert dat de
KSPBOOT.BIN in je input exact overeenkomt met die in de template.

Opties
------

  --force
      Bestaande output overschrijven.

  --template-dsk BESTAND.DSK
      Bootsector en KSPBOOT-referentie uit een passende bestaande DSK halen.

  --boot-sector SECTOR.BIN
      Zelf een raw bootsector van exact 512 bytes opgeven.

  --allow-mismatched-kspboot
      Veiligheidscontrole uitschakelen. Alleen gebruiken als je zeker weet dat
      de bootcode en KSPBOOT.BIN compatibel zijn.

  --include-hidden
      Dotfiles meenemen. .DS_Store en andere bekende OS-rommel blijven
      uitgesloten.

Beperkingen
-----------

  * Bestanden moeten geldige MSX-DOS 8.3-namen hebben.
  * Alle bestanden komen in de root van de disk; subdirectories worden niet
    ondersteund.
  * De disk is 720 KiB FAT12, 9 sectoren/track, 2 zijden.
